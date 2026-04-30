import os
import sys

import pytest

os.environ.setdefault("FEISHU_APP_ID", "test_app_id")
os.environ.setdefault("FEISHU_APP_SECRET", "test_app_secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import session_store as session_store_module
import agent_hub as agent_hub_module
import commands as commands_module
from commands import handle_command
from session_store import SessionStore


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "state"
    sessions_dir.mkdir()
    monkeypatch.setattr(session_store_module, "SESSIONS_DIR", str(sessions_dir))
    monkeypatch.setattr(session_store_module, "SESSIONS_FILE", str(sessions_dir / "sessions.json"))
    monkeypatch.setattr(agent_hub_module, "PROJECTS_ROOT", str(tmp_path / "projects"))
    monkeypatch.setattr(agent_hub_module, "AGENT_HUB_ROOT", str(tmp_path / "projects" / "_agent-hub"))
    monkeypatch.setattr(commands_module, "AGENT_HUB_ROOT", str(tmp_path / "projects" / "_agent-hub"))
    return SessionStore()


@pytest.mark.asyncio
async def test_workspace_binding_isolated_per_group(isolated_store, tmp_path):
    user_id = "user_123"
    group_a = "group_a"
    group_b = "group_b"
    project1 = tmp_path / "project1"
    project2 = tmp_path / "project2"
    project1.mkdir()
    project2.mkdir()

    reply1 = await handle_command("workspace", f'save proj1 "{project1}"', user_id, group_a, isolated_store)
    reply2 = await handle_command("workspace", f'save proj2 "{project2}"', user_id, group_a, isolated_store)
    bind1 = await handle_command("workspace", "use proj1", user_id, group_a, isolated_store)
    bind2 = await handle_command("workspace", "use proj2", user_id, group_b, isolated_store)

    session_a = await isolated_store.get_current(user_id, group_a)
    session_b = await isolated_store.get_current(user_id, group_b)

    assert "已保存工作空间" in reply1
    assert "已保存工作空间" in reply2
    assert "当前群组已绑定工作空间 `proj1`" in bind1
    assert "当前群组已绑定工作空间 `proj2`" in bind2
    assert session_a.workspace == "proj1"
    assert session_a.cwd == str(project1)
    assert session_b.workspace == "proj2"
    assert session_b.cwd == str(project2)


@pytest.mark.asyncio
async def test_workspace_save_uses_current_cwd_by_default(isolated_store, tmp_path):
    user_id = "user_123"
    chat_id = "group_001"
    project = tmp_path / "project"
    project.mkdir()

    await isolated_store.set_cwd(user_id, chat_id, str(project))
    reply = await handle_command("workspace", "save backend", user_id, chat_id, isolated_store)

    assert "已保存工作空间 `backend`" in reply
    assert isolated_store.list_workspaces(user_id)["backend"] == str(project)


@pytest.mark.asyncio
async def test_cd_clears_named_workspace_binding(isolated_store, tmp_path):
    user_id = "user_123"
    chat_id = "group_001"
    project = tmp_path / "project"
    other = tmp_path / "other"
    project.mkdir()
    other.mkdir()

    await handle_command("workspace", f'save backend "{project}"', user_id, chat_id, isolated_store)
    await handle_command("workspace", "use backend", user_id, chat_id, isolated_store)

    reply = await handle_command("cd", str(other), user_id, chat_id, isolated_store)
    current = await isolated_store.get_current(user_id, chat_id)

    assert "解除原工作空间绑定" in reply
    assert current.workspace == ""
    assert current.cwd == str(other)


@pytest.mark.asyncio
async def test_ls_lists_current_workspace_contents(isolated_store, tmp_path):
    user_id = "user_123"
    chat_id = "group_001"
    project = tmp_path / "project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "README.md").write_text("hi", encoding="utf-8")

    await isolated_store.set_cwd(user_id, chat_id, str(project))
    reply = await handle_command("ls", "", user_id, chat_id, isolated_store)

    assert "目录内容" in reply
    assert f"绝对路径：`{project}`" in reply
    assert "`src/`" in reply
    assert "`README.md`" in reply


@pytest.mark.asyncio
async def test_ls_supports_relative_subdir(isolated_store, tmp_path):
    user_id = "user_123"
    chat_id = "group_001"
    project = tmp_path / "project"
    nested = project / "backend"
    project.mkdir()
    nested.mkdir()
    (nested / "app.py").write_text("print('ok')", encoding="utf-8")

    await isolated_store.set_cwd(user_id, chat_id, str(project))
    reply = await handle_command("ls", "backend", user_id, chat_id, isolated_store)

    assert "请求路径：`backend`" in reply
    assert f"绝对路径：`{nested}`" in reply
    assert "`app.py`" in reply


@pytest.mark.asyncio
async def test_project_new_creates_hub_files_and_binds_chat(isolated_store, tmp_path):
    user_id = "user_123"
    chat_id = "group_001"

    reply = await handle_command("project", "new alpha", user_id, chat_id, isolated_store)
    current = await isolated_store.get_current(user_id, chat_id)
    project = tmp_path / "projects" / "alpha"

    assert "当前聊天已绑定到项目 `alpha`" in reply
    assert current.cwd == str(project)
    assert current.workspace == "alpha"
    assert (project / "AGENTS.md").exists()
    assert (project / "CLAUDE.md").exists()
    assert (project / "PROJECT_CONTEXT.md").exists()
    assert (tmp_path / "projects" / "_agent-hub" / "lark-chat-map.json").exists()


@pytest.mark.asyncio
async def test_project_new_supports_unicode_project_names(isolated_store, tmp_path):
    user_id = "user_123"
    chat_id = "group_001"

    await handle_command("project", "new 小蓝不打工了", user_id, chat_id, isolated_store)
    current = await isolated_store.get_current(user_id, chat_id)

    assert current.cwd == str(tmp_path / "projects" / "小蓝不打工了")
    assert current.workspace == "小蓝不打工了"


@pytest.mark.asyncio
async def test_brief_handoff_task_and_sync_use_current_project(isolated_store, tmp_path):
    user_id = "user_123"
    chat_id = "group_001"

    await handle_command("project", "new alpha", user_id, chat_id, isolated_store)
    handoff = await handle_command("handoff", "Codex finished setup.", user_id, chat_id, isolated_store)
    task = await handle_command("task", "Wire Claude bridge into the same project.", user_id, chat_id, isolated_store)
    brief = await handle_command("brief", "", user_id, chat_id, isolated_store)
    sync = await handle_command("sync", "", user_id, chat_id, isolated_store)

    project = tmp_path / "projects" / "alpha"
    assert "已追加交接记录" in handoff
    assert "已追加任务" in task
    assert "Codex finished setup." in (project / "HANDOFF.md").read_text(encoding="utf-8")
    assert "Wire Claude bridge" in (project / "TASKS.md").read_text(encoding="utf-8")
    assert "# Project Brief: alpha" in brief
    assert "已同步项目摘要" in sync
    assert (project / "PROJECT_BRIEF.md").exists()
