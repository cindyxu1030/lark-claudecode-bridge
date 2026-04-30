"""
斜杠命令解析与处理。
返回要发送给用户的回复文本。
"""

import asyncio
import getpass
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from typing import Optional, Tuple

from bot_config import AGENT_HUB_ROOT, CODEX_CLI, CODEX_HOME, DEFAULT_CWD
from agent_hub import (
    append_handoff,
    append_task,
    bind_chat,
    build_brief,
    ensure_hub,
    get_chat_binding,
    init_project,
    list_projects,
    sync_brief,
)
from session_store import SessionStore, scan_cli_sessions, generate_summary, _get_api_token, _write_custom_title

SKILLS_DIRS = [
    os.path.expanduser("~/.codex/skills"),
    os.path.expanduser("~/.agents/skills"),
]


VALID_MODES = {
    "default": "每次工具调用需确认",
    "acceptEdits": "自动接受文件编辑，其余需确认",
    "plan": "只规划不执行工具",
    "bypassPermissions": "全部自动执行（无确认）",
    "dontAsk": "全部自动执行（静默）",
}

MODE_ALIASES = {
    "bypass": "bypassPermissions",
    "accept": "acceptEdits",
    "auto": "bypassPermissions",
}

MODEL_ALIASES = {
    "fast": "gpt-5.4-mini",
    "mini": "gpt-5.4-mini",
    "default": "gpt-5.4",
    "frontier": "gpt-5.5",
}

HELP_TEXT = """\
📖 **可用命令**

**Bot 管理：**
`/help` — 显示此帮助
`/stop` — 停止当前正在运行的任务
`/new` 或 `/clear` — 开始新 session
`/resume` — 查看历史 sessions / `/resume [序号]` 恢复
`/model [名称]` — 切换模型（default / mini / frontier 或完整 ID）
`/mode [模式]` — 切换权限模式（default / plan / acceptEdits / bypassPermissions）
`/status` — 显示当前 session 信息
`/cd [路径]` — 切换工具执行的工作目录
`/ls [路径]` — 查看当前工作目录下的文件/目录
`/workspace` 或 `/ws` — 保存/切换群组工作空间

**Agent Hub：**
`/project` — 查看/创建/绑定项目
`/brief` — 汇总当前项目共享记忆
`/handoff [内容]` — 追加交接记录
`/task [内容]` — 追加项目任务
`/sync` — 生成 PROJECT_BRIEF.md

**查看能力：**
`/skills` — 列出已安装的 Codex/Agent Skills
`/mcp` — 列出已配置的 MCP Servers
`/usage` — 查看 Codex 登录状态


**Codex 指令（直接转发给 Codex 执行）：**
`/commit` — 提交代码
其他 `/xxx` — 自动转发给 Codex 处理

**MCP 工具：** 已配置的 MCP servers 自动可用，直接对话即可调用。

**发送任意普通消息即可与 Codex 对话。**\
"""


def parse_command(text: str) -> Optional[Tuple[str, str]]:
    """
    尝试解析斜杠命令。
    返回 (command, args) 或 None（不是命令）。
    """
    text = text.strip()
    if not text.startswith("/"):
        return None
    parts = text[1:].split(None, 1)
    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    return cmd, args


# Bot 自身处理的命令，其余 /xxx 转发给 Codex
BOT_COMMANDS = {
    "help", "h", "new", "clear", "resume", "model", "mode", "status", "cd", "ls",
    "workspace", "ws", "project", "brief", "handoff", "task", "sync",
    "skills", "mcp", "usage", "stop",
}


async def _build_session_list(user_id: str, chat_id: str, store: SessionStore, cli_all: list[dict] | None = None) -> list[dict]:
    """构建合并、去重、排序后的 session 列表（不含当前 session）。
    /resume 列表展示和 /resume N 选择都用这一个函数，保证索引一致。"""
    cur_sid = (await store.get_current_raw(user_id, chat_id)).get("session_id")

    if cli_all is None:
        cli_all = scan_cli_sessions(30)
    cli_preview_map = {s["session_id"]: s for s in cli_all}

    feishu_sessions = [
        {**s, "source": "feishu"} for s in await store.list_sessions(user_id, chat_id)
    ]
    for s in feishu_sessions:
        cli_info = cli_preview_map.get(s["session_id"])
        if cli_info and cli_info.get("preview"):
            s["preview"] = cli_info["preview"]

    feishu_ids = {s["session_id"] for s in feishu_sessions}
    cli_sessions = [
        s for s in cli_all
        if s["session_id"] not in feishu_ids and len(s.get("preview", "")) > 5
    ]
    all_sessions = feishu_sessions + cli_sessions

    seen = set()
    if cur_sid:
        seen.add(cur_sid)
    deduped = []
    for s in all_sessions:
        sid = s["session_id"]
        if sid not in seen:
            seen.add(sid)
            deduped.append(s)

    deduped.sort(key=lambda s: s.get("started_at", ""), reverse=True)
    return deduped[:15]


async def _format_session_list(user_id: str, chat_id: str, store: SessionStore) -> str:
    """生成历史 sessions 列表（去重 + 手机友好格式），含当前 session"""
    from session_store import _clean_preview

    cur = await store.get_current_raw(user_id, chat_id)
    cur_sid = cur.get("session_id")

    cli_all = scan_cli_sessions(30)
    cli_preview_map = {s["session_id"]: s for s in cli_all}

    all_sessions = await _build_session_list(user_id, chat_id, store, cli_all=cli_all)

    def _fmt_time(raw: str) -> str:
        t = raw[:16].replace("T", " ")
        if len(t) >= 16:
            t = t[5:16].replace("-", "/")
        return t

    # 收集所有需要展示的 session_id
    all_sids = []
    if cur_sid:
        all_sids.append(cur_sid)
    for s in all_sessions:
        all_sids.append(s["session_id"])

    # 懒加载：为缺失摘要的 session 生成（限制 5 个，避免太慢）
    summaries = {}
    missing = []
    for sid in all_sids:
        cached = store.get_summary(user_id, sid)
        if cached:
            summaries[sid] = cached
        else:
            missing.append(sid)

    if missing:
        token = _get_api_token()
        if token:
            # 并行生成摘要，不逐个阻塞
            tasks = [asyncio.to_thread(generate_summary, sid, token) for sid in missing[:5]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            new_summaries = {}
            for sid, result in zip(missing[:5], results):
                if isinstance(result, str) and result:
                    new_summaries[sid] = result
                    summaries[sid] = result
                    _write_custom_title(sid, result)
            if new_summaries:
                await store.batch_set_summaries(user_id, new_summaries)

    lines = []

    def _strip_md(text: str) -> str:
        """去除 markdown 格式 + 压成单行纯文本"""
        # 换行 → 空格，压成单行
        text = " ".join(text.split())
        # heading 标记
        while text.startswith("#"):
            text = text.lstrip("#").lstrip()
        # bold / italic
        text = text.replace("**", "").replace("__", "")
        # backtick
        text = text.replace("`", "")
        # XML 残留标签名（如 <tool_call>）
        text = text.replace("<", "").replace(">", "")
        return text.strip()

    def _desc(sid: str, preview_raw: str) -> str:
        """用 summary 优先，没有就用 preview，拼成简短描述"""
        s = summaries.get(sid, "")
        if s:
            s = _strip_md(s)
            return s if len(s) <= 40 else s[:37] + "..."
        p = _clean_preview(preview_raw or "")
        if not p:
            return "（无预览）"
        p = _strip_md(p)
        return p if len(p) <= 40 else p[:37] + "..."

    # 当前 session
    if cur_sid:
        cli_info = cli_preview_map.get(cur_sid)
        preview = (cli_info.get("preview") if cli_info and cli_info.get("preview")
                   else cur.get("preview") or "")
        started = _fmt_time(cur.get("started_at", ""))
        lines.append(f"当前  {_desc(cur_sid, preview)} ({started})  #{cur_sid[:8]}")

    if not cur_sid and not all_sessions:
        return "暂无历史 sessions。"

    for i, s in enumerate(all_sessions, 1):
        sid = s["session_id"]
        preview = s.get("preview", "")
        started = _fmt_time(s.get("started_at", ""))
        lines.append(f"{i}. {_desc(sid, preview)} ({started})  #{sid[:8]}")

    if all_sessions:
        lines.append("")
        lines.append("回复 /resume 序号 恢复")
    return "\n".join(lines)


def _list_skills() -> str:
    """扫描本机 Codex/agent skills 目录，列出可用 skills"""
    skills = []
    for base_dir in SKILLS_DIRS:
        if not os.path.isdir(base_dir):
            continue
        for root, dirs, files in os.walk(base_dir):
            if "SKILL.md" not in files:
                continue
            name = os.path.basename(root)
            fpath = os.path.join(root, "SKILL.md")
            desc = ""
            try:
                with open(fpath, encoding="utf-8") as f:
                    in_frontmatter = False
                    for line in f:
                        line = line.strip()
                        if line == "---" and not in_frontmatter:
                            in_frontmatter = True
                            continue
                        if line == "---" and in_frontmatter:
                            break
                        if in_frontmatter and line.startswith("description:"):
                            desc = line[len("description:"):].strip().strip('"')
            except OSError:
                pass
            skills.append((name, desc))

    if not skills:
        return "暂无已安装的 skills。"

    skills.sort(key=lambda x: x[0])
    lines = ["🛠 **可用 Skills**\n"]
    for name, desc in skills:
        desc_str = f" — {desc}" if desc else ""
        lines.append(f"• `{name}`{desc_str}")
    return "\n".join(lines)


def _get_usage() -> str:
    """Show Codex auth status; Codex CLI does not expose subscription usage headers."""
    try:
        result = subprocess.run(
            [CODEX_CLI, "login", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "CODEX_HOME": os.path.expanduser(CODEX_HOME)},
        )
    except Exception as e:
        return f"❌ 获取 Codex 登录状态失败：{e}"
    output = (result.stdout or result.stderr).strip()
    return "📊 **Codex 状态**\n\n" + (output or "已登录状态未知。")



def _list_mcp() -> str:
    """调用 codex mcp list 获取已配置的 MCP servers"""
    try:
        result = subprocess.run(
            [CODEX_CLI, "mcp", "list"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "CODEX_HOME": os.path.expanduser(CODEX_HOME)},
        )
        output = result.stdout.strip()
    except Exception as e:
        return f"❌ 获取 MCP 列表失败：{e}"

    if not output:
        return "暂无已配置的 MCP servers。\n\n用 `codex mcp` 在终端管理。"

    return f"🔌 **已配置的 MCP Servers**\n\n{output}"


async def _list_directory(user_id: str, chat_id: str, store: SessionStore, args: str) -> str:
    cur = await store.get_current_raw(user_id, chat_id)
    base_dir = cur.get("cwd", DEFAULT_CWD)
    raw_target = args.strip()

    if not raw_target:
        target = base_dir
        display_target = "."
    elif os.path.isabs(raw_target):
        target = os.path.expanduser(raw_target)
        display_target = target
    else:
        target = os.path.abspath(os.path.join(base_dir, os.path.expanduser(raw_target)))
        display_target = raw_target

    if not os.path.exists(target):
        return f"❌ 路径不存在：`{display_target}`\n当前工作目录：`{base_dir}`"

    if not os.path.isdir(target):
        return f"❌ 目标不是目录：`{display_target}`"

    try:
        entries = []
        with os.scandir(target) as it:
            for entry in it:
                suffix = "/" if entry.is_dir() else ""
                entries.append((not entry.is_dir(), entry.name.lower(), f"`{entry.name}{suffix}`"))
    except OSError as e:
        return f"❌ 读取目录失败：{e}"

    entries.sort()
    preview = [item[2] for item in entries[:50]]
    hidden_count = max(0, len(entries) - len(preview))

    lines = [
        "📁 **目录内容**",
        f"请求路径：`{display_target}`",
        f"绝对路径：`{target}`",
    ]
    if not preview:
        lines.append("（空目录）")
        return "\n".join(lines)

    lines.append("")
    lines.extend(preview)
    if hidden_count:
        lines.append("")
        lines.append(f"…… 还有 {hidden_count} 项未显示")
    return "\n".join(lines)


async def _format_workspace_list(user_id: str, chat_id: str, store: SessionStore) -> str:
    cur = await store.get_current_raw(user_id, chat_id)
    current_name = cur.get("workspace", "")
    current_cwd = cur.get("cwd", "~")
    workspaces = store.list_workspaces(user_id)

    lines = ["🗂 **工作空间**"]
    lines.append(f"当前绑定：`{current_name}`" if current_name else "当前绑定：（未命名）")
    lines.append(f"当前目录：`{current_cwd}`")

    if workspaces:
        lines.append("")
        lines.append("已保存：")
        for name, path in workspaces.items():
            marker = " ← 当前群组" if name == current_name else ""
            lines.append(f"• `{name}` → `{path}`{marker}")
    else:
        lines.append("")
        lines.append("还没有已保存的工作空间。")

    lines.append("")
    lines.append("用法：")
    lines.append("`/ws save 名称 [路径]` 保存工作空间")
    lines.append("`/ws use 名称` 绑定当前群组到该工作空间")
    lines.append("`/ws set 路径` 直接设置当前群组目录")
    lines.append("`/ws remove 名称` 删除已保存的工作空间")
    return "\n".join(lines)


async def _handle_workspace_command(
    args: str,
    user_id: str,
    chat_id: str,
    store: SessionStore,
) -> str:
    if not args:
        return await _format_workspace_list(user_id, chat_id, store)

    try:
        parts = shlex.split(args)
    except ValueError as e:
        return f"❌ 参数解析失败：{e}"

    if not parts:
        return await _format_workspace_list(user_id, chat_id, store)

    action = parts[0].lower()

    if action in {"list", "ls"}:
        return await _format_workspace_list(user_id, chat_id, store)

    if action in {"save", "add"}:
        if len(parts) < 2:
            return "⚠️ 用法：`/ws save 名称 [路径]`"
        name = parts[1]
        path = (await store.get_current_raw(user_id, chat_id)).get("cwd", DEFAULT_CWD)
        if len(parts) >= 3:
            path = os.path.expanduser(parts[2])
        if not os.path.isdir(path):
            return f"❌ 路径不存在：`{path}`"
        await store.save_workspace(user_id, name, path)
        return f"✅ 已保存工作空间 `{name}` → `{path}`"

    if action == "use":
        if len(parts) != 2:
            return "⚠️ 用法：`/ws use 名称`"
        name = parts[1]
        path = await store.bind_workspace(user_id, chat_id, name)
        if not path:
            return f"❌ 未找到工作空间：`{name}`，先用 `/ws save {name} 路径` 保存。"
        return (
            f"✅ 当前群组已绑定工作空间 `{name}`\n"
            f"工作目录：`{path}`\n"
            "如需清空旧上下文，可继续发送 `/new`。"
        )

    if action == "set":
        if len(parts) != 2:
            return "⚠️ 用法：`/ws set 路径`"
        path = os.path.expanduser(parts[1])
        if not os.path.isdir(path):
            return f"❌ 路径不存在：`{path}`"
        old_name = (await store.get_current_raw(user_id, chat_id)).get("workspace", "")
        await store.set_cwd(user_id, chat_id, path)
        suffix = "，并解除原工作空间绑定" if old_name else ""
        return f"✅ 当前群组工作目录已切换为 `{path}`{suffix}"

    if action in {"remove", "delete", "rm"}:
        if len(parts) != 2:
            return "⚠️ 用法：`/ws remove 名称`"
        name = parts[1]
        if not await store.delete_workspace(user_id, name):
            return f"❌ 未找到工作空间：`{name}`"
        return f"✅ 已删除工作空间 `{name}`"

    return (
        f"❌ 未知子命令：`{action}`\n"
        "可用：`list`、`save`、`use`、`set`、`remove`"
    )


async def _current_project_path(user_id: str, chat_id: str, store: SessionStore) -> str:
    cur = await store.get_current_raw(user_id, chat_id)
    cwd = os.path.expanduser(cur.get("cwd", DEFAULT_CWD))
    required = ("PROJECT_CONTEXT.md", "TASKS.md", "DECISIONS.md", "HANDOFF.md")
    if os.path.isdir(cwd) and any(os.path.exists(os.path.join(cwd, name)) for name in required):
        return cwd
    return ""


async def _format_project_status(user_id: str, chat_id: str, store: SessionStore) -> str:
    ensure_hub()
    cur = await store.get_current_raw(user_id, chat_id)
    binding = get_chat_binding(chat_id)
    projects = list_projects()
    lines = ["🧭 **Agent Hub 项目**"]
    lines.append(f"当前工作目录：`{cur.get('cwd', DEFAULT_CWD)}`")
    if binding:
        lines.append(f"Lark 群绑定：`{binding.get('project')}` → `{binding.get('path')}`")
    else:
        lines.append("Lark 群绑定：（未绑定）")

    if projects:
        lines.append("")
        lines.append("已发现项目：")
        for name, path in projects[:30]:
            lines.append(f"• `{name}` → `{path}`")
    else:
        lines.append("")
        lines.append("还没有项目记忆文件。")

    lines.append("")
    lines.append("用法：")
    lines.append("`/project new 名称` 创建项目并绑定当前聊天")
    lines.append("`/project use 名称或路径` 绑定当前聊天到项目")
    lines.append("`/brief` 查看共享记忆摘要")
    lines.append("`/handoff 内容` 追加交接")
    lines.append("`/task 内容` 追加任务")
    lines.append("`/sync` 生成 PROJECT_BRIEF.md")
    return "\n".join(lines)


async def _handle_project_command(args: str, user_id: str, chat_id: str, store: SessionStore) -> str:
    ensure_hub()
    if not args:
        return await _format_project_status(user_id, chat_id, store)

    try:
        parts = shlex.split(args)
    except ValueError as e:
        return f"❌ 参数解析失败：{e}"

    if not parts:
        return await _format_project_status(user_id, chat_id, store)

    action = parts[0].lower()
    if action in {"list", "ls", "status"}:
        return await _format_project_status(user_id, chat_id, store)

    if action in {"new", "create", "use", "init"}:
        if len(parts) < 2:
            return "⚠️ 用法：`/project new 名称` 或 `/project use 名称或路径`"
        raw_name = parts[1]
        display_name = raw_name if not os.path.isabs(os.path.expanduser(raw_name)) else os.path.basename(raw_name.rstrip("/"))
        path = init_project(raw_name, display_name=display_name)
        workspace_name = path.name
        await store.save_workspace(user_id, workspace_name, str(path))
        await store.bind_workspace(user_id, chat_id, workspace_name)
        bind_chat(chat_id, workspace_name, str(path))
        return (
            f"✅ 当前聊天已绑定到项目 `{workspace_name}`\n"
            f"项目目录：`{path}`\n"
            "已创建/确认共享记忆文件：`AGENTS.md`、`CLAUDE.md`、`PROJECT_CONTEXT.md`、`TASKS.md`、`DECISIONS.md`、`HANDOFF.md`\n"
            "建议下一步：发送 `/brief` 检查项目记忆，或直接让 Codex/Claude 开始工作。"
        )

    return (
        f"❌ 未知子命令：`{action}`\n"
        "可用：`list`、`new`、`use`、`init`"
    )


async def _handle_brief_command(user_id: str, chat_id: str, store: SessionStore) -> str:
    path = await _current_project_path(user_id, chat_id, store)
    if not path:
        return "❌ 当前聊天还没有绑定 Agent Hub 项目。先用 `/project use 项目名`。"
    return build_brief(path)


async def _handle_handoff_command(args: str, user_id: str, chat_id: str, store: SessionStore) -> str:
    path = await _current_project_path(user_id, chat_id, store)
    if not path:
        return "❌ 当前聊天还没有绑定 Agent Hub 项目。先用 `/project use 项目名`。"
    if not args.strip():
        handoff_path = os.path.join(path, "HANDOFF.md")
        try:
            with open(handoff_path, encoding="utf-8") as f:
                text = f.read().strip()
        except OSError as e:
            return f"❌ 读取 HANDOFF.md 失败：{e}"
        return text[-3500:] if text else "HANDOFF.md 为空。"
    append_handoff(path, args, actor="Lark")
    return f"✅ 已追加交接记录到 `{os.path.join(path, 'HANDOFF.md')}`"


async def _handle_task_command(args: str, user_id: str, chat_id: str, store: SessionStore) -> str:
    path = await _current_project_path(user_id, chat_id, store)
    if not path:
        return "❌ 当前聊天还没有绑定 Agent Hub 项目。先用 `/project use 项目名`。"
    if not args.strip():
        tasks_path = os.path.join(path, "TASKS.md")
        try:
            with open(tasks_path, encoding="utf-8") as f:
                text = f.read().strip()
        except OSError as e:
            return f"❌ 读取 TASKS.md 失败：{e}"
        return text[-3500:] if text else "TASKS.md 为空。"
    append_task(path, args)
    return f"✅ 已追加任务到 `{os.path.join(path, 'TASKS.md')}`"


async def _handle_sync_command(user_id: str, chat_id: str, store: SessionStore) -> str:
    path = await _current_project_path(user_id, chat_id, store)
    if not path:
        return "❌ 当前聊天还没有绑定 Agent Hub 项目。先用 `/project use 项目名`。"
    brief_path = sync_brief(path)
    return (
        "✅ 已同步项目摘要\n"
        f"项目摘要：`{brief_path}`\n"
        f"Hub 副本：`{os.path.join(AGENT_HUB_ROOT, 'latest-briefs', os.path.basename(path) + '.md')}`"
    )


async def handle_command(
    cmd: str,
    args: str,
    user_id: str,
    chat_id: str,
    store: SessionStore,
) -> Optional[str]:
    """处理命令，返回回复文本。返回 None 表示不是 bot 命令，应转发给 Codex。"""

    if cmd not in BOT_COMMANDS:
        return None  # 不认识的 /xxx → 转发给 Codex（如 /commit 等指令）

    if cmd == "ws":
        cmd = "workspace"

    if cmd in ("help", "h"):
        return HELP_TEXT

    elif cmd in ("new", "clear"):
        # /new [mode] — 开新 session，可选指定模式
        new_mode = None
        if args:
            alias = MODE_ALIASES.get(args.lower(), args)
            if alias in VALID_MODES:
                new_mode = alias

        old_title = await store.new_session(user_id, chat_id)
        if new_mode:
            await store.set_permission_mode(user_id, chat_id, new_mode)

        cur = await store.get_current(user_id, chat_id)
        parts = []
        if old_title:
            parts.append(f"✅ 已开始新 session。\n上个会话：「{old_title}」")
        else:
            parts.append("✅ 已开始新 session。")
        parts.append(f"当前模式：**{cur.permission_mode}**")
        return {
            "text": "\n".join(parts),
            "buttons": [
                {"text": "📋 规划", "value": {"action": "set_mode", "mode": "plan", "cid": chat_id}},
                {"text": "✏️ 接受编辑", "value": {"action": "set_mode", "mode": "acceptEdits", "cid": chat_id}},
                {"text": "🚀 全自动", "value": {"action": "set_mode", "mode": "bypassPermissions", "cid": chat_id}},
                {"text": "🔒 需确认", "value": {"action": "set_mode", "mode": "default", "cid": chat_id}},
            ],
        }

    elif cmd == "resume":
        if not args:
            return await _format_session_list(user_id, chat_id, store)
        # 如果是数字序号，先在合并列表中找到对应 session_id
        try:
            idx = int(args) - 1
            all_sessions = await _build_session_list(user_id, chat_id, store)
            if 0 <= idx < len(all_sessions):
                args = all_sessions[idx]["session_id"]
            else:
                return f"❌ 序号 {int(args)} 超出范围（共 {len(all_sessions)} 条）。"
        except ValueError:
            pass  # 直接用 session ID 字符串
        session_id, old_title = await store.resume_session(user_id, chat_id, args)
        if not session_id:
            return f"❌ 未找到 session：`{args}`，用 `/resume` 查看列表。"
        reply = f"✅ 已恢复 session `{session_id[:8]}...`，继续对话吧。"
        if old_title:
            reply += f"\n上个会话：「{old_title}」"
        return reply

    elif cmd == "model":
        if not args:
            cur = await store.get_current(user_id, chat_id)
            return f"当前模型：`{cur.model}`\n可用：default / mini / frontier 或完整模型 ID"
        model = MODEL_ALIASES.get(args.lower(), args)
        await store.set_model(user_id, chat_id, model)
        return f"✅ 已切换模型为 `{model}`"

    elif cmd == "status":
        cur = await store.get_current_raw(user_id, chat_id)
        sid = cur.get("session_id") or "（新 session）"
        model = cur.get("model", "未知")
        cwd = cur.get("cwd", "~")
        workspace = cur.get("workspace") or "（未绑定）"
        started = cur.get("started_at", "")[:16].replace("T", " ")
        mode = cur.get("permission_mode") or "bypassPermissions"
        return (
            f"📊 **当前 Session 状态**\n"
            f"Session ID: `{sid}`\n"
            f"模型: `{model}`\n"
            f"权限模式: `{mode}`\n"
            f"工作空间: `{workspace}`\n"
            f"工作目录: `{cwd}`\n"
            f"开始时间: {started}"
        )

    elif cmd == "mode":
        if not args:
            cur = await store.get_current(user_id, chat_id)
            current_mode = cur.permission_mode
            lines = [f"当前模式：**{current_mode}** — {VALID_MODES.get(current_mode, '')}\n"]
            lines.append("**可选模式：**")
            for mode, desc in VALID_MODES.items():
                marker = " ← 当前" if mode == current_mode else ""
                lines.append(f"• `{mode}` — {desc}{marker}")
            lines.append("\n用 `/mode [模式名]` 切换。")
            return "\n".join(lines)
        mode = MODE_ALIASES.get(args.lower(), args)
        if mode not in VALID_MODES:
            return f"❌ 未知模式：`{args}`\n可选：{', '.join(f'`{m}`' for m in VALID_MODES)}"
        await store.set_permission_mode(user_id, chat_id, mode)
        return f"✅ 已切换为 **{mode}** — {VALID_MODES[mode]}"

    elif cmd == "cd":
        if not args:
            return "⚠️ 用法：`/cd [路径]`"
        path = os.path.expanduser(args)
        if not os.path.isdir(path):
            return f"❌ 路径不存在：`{path}`"
        old_name = (await store.get_current_raw(user_id, chat_id)).get("workspace", "")
        await store.set_cwd(user_id, chat_id, path)
        suffix = "，并解除原工作空间绑定" if old_name else ""
        return f"✅ 工作目录已切换为 `{path}`{suffix}"

    elif cmd == "ls":
        return await _list_directory(user_id, chat_id, store, args)

    elif cmd == "workspace":
        return await _handle_workspace_command(args, user_id, chat_id, store)

    elif cmd == "project":
        return await _handle_project_command(args, user_id, chat_id, store)

    elif cmd == "brief":
        return await _handle_brief_command(user_id, chat_id, store)

    elif cmd == "handoff":
        return await _handle_handoff_command(args, user_id, chat_id, store)

    elif cmd == "task":
        return await _handle_task_command(args, user_id, chat_id, store)

    elif cmd == "sync":
        return await _handle_sync_command(user_id, chat_id, store)

    elif cmd == "skills":
        return _list_skills()

    elif cmd == "mcp":
        return _list_mcp()

    elif cmd == "usage":
        return _get_usage()

    elif cmd == "stop":
        return "⏹ /stop 命令在消息队列外处理，如果看到这条说明当前没有运行中的任务。"

    else:
        return None  # fallback: 转发给 Codex
