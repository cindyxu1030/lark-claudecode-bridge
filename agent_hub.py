from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from bot_config import AGENT_HUB_ROOT, PROJECTS_ROOT

PROJECT_MEMORY_FILES = {
    "AGENTS.md": "# Agent Instructions\n\nRead PROJECT_CONTEXT.md, TASKS.md, DECISIONS.md, and HANDOFF.md before substantive work.\n\nUpdate HANDOFF.md before pausing or switching agents.\n",
    "CLAUDE.md": "# Claude Project Instructions\n\nRead AGENTS.md first, then PROJECT_CONTEXT.md, TASKS.md, DECISIONS.md, and HANDOFF.md.\n",
    "PROJECT_CONTEXT.md": "# Project Context\n\n## Goal\n\nTBD.\n\n## Users\n\nTBD.\n\n## Constraints\n\nTBD.\n",
    "TASKS.md": "# Tasks\n\n- [ ] Define the current project goal.\n",
    "DECISIONS.md": "# Decisions\n\n| Date | Decision | Reason |\n| --- | --- | --- |\n",
    "HANDOFF.md": "# Handoff\n\n## Current State\n\nTBD.\n\n## Next Best Action\n\nTBD.\n\n## Last Updates\n",
}

HUB_FILES = {
    "GLOBAL_CONTEXT.md": "# Global Agent Context\n\nCanonical project root: `/Users/cindy/projects`.\n",
    "WORKING_RULES.md": "# Working Rules\n\nOne project = one folder = one Lark group chat = one shared memory set.\n",
    "shared-memory.md": "# Shared Memory\n\nUse project-specific memory files for durable context.\n",
}


def ensure_hub() -> Path:
    hub = Path(AGENT_HUB_ROOT).expanduser()
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "latest-briefs").mkdir(exist_ok=True)
    for name, content in HUB_FILES.items():
        _write_if_missing(hub / name, content)
    _write_if_missing(hub / "lark-chat-map.json", "{}\n")
    return hub


def list_projects() -> list[tuple[str, Path]]:
    root = Path(PROJECTS_ROOT).expanduser()
    if not root.exists():
        return []
    projects = []
    for path in root.iterdir():
        if path.is_dir() and path.name != "_agent-hub" and not path.name.startswith("."):
            if (path / "AGENTS.md").exists() or (path / "PROJECT_CONTEXT.md").exists():
                projects.append((path.name, path))
    return sorted(projects, key=lambda item: item[0].lower())


def init_project(name_or_path: str, *, display_name: str | None = None) -> Path:
    path = resolve_project_path(name_or_path)
    path.mkdir(parents=True, exist_ok=True)
    for name, content in PROJECT_MEMORY_FILES.items():
        _write_if_missing(path / name, content)
    return path


def resolve_project_path(name_or_path: str) -> Path:
    raw = name_or_path.strip()
    if not raw:
        raise ValueError("project name/path is required")
    expanded = Path(os.path.expanduser(raw))
    if expanded.is_absolute():
        return expanded
    return Path(PROJECTS_ROOT).expanduser() / _safe_project_name(raw)


def bind_chat(chat_id: str, project_name: str, project_path: str) -> None:
    hub = ensure_hub()
    chat_map = hub / "lark-chat-map.json"
    try:
        data = json.loads(chat_map.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data[chat_id] = {
        "project": project_name,
        "path": project_path,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    tmp = chat_map.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(chat_map)


def get_chat_binding(chat_id: str) -> dict:
    chat_map = ensure_hub() / "lark-chat-map.json"
    try:
        return json.loads(chat_map.read_text(encoding="utf-8")).get(chat_id, {})
    except Exception:
        return {}


def build_brief(project_path: str) -> str:
    path = Path(project_path).expanduser()
    parts = []
    for name in ("PROJECT_CONTEXT.md", "TASKS.md", "DECISIONS.md", "HANDOFF.md"):
        parts.append(f"## {name}\n\n{_read_preview(path / name)}")
    return f"# Project Brief: {path.name}\n\n" + "\n\n".join(parts).strip() + "\n"


def sync_brief(project_path: str) -> Path:
    path = Path(project_path).expanduser()
    brief = build_brief(str(path))
    project_brief = path / "PROJECT_BRIEF.md"
    project_brief.write_text(brief, encoding="utf-8")
    latest = ensure_hub() / "latest-briefs" / f"{path.name}.md"
    latest.write_text(brief, encoding="utf-8")
    return project_brief


def append_handoff(project_path: str, text: str, *, actor: str = "Lark") -> None:
    path = init_project(project_path)
    stamp = datetime.now().isoformat(timespec="seconds")
    with (path / "HANDOFF.md").open("a", encoding="utf-8") as f:
        f.write(f"\n### {stamp} - {actor}\n\n{text.strip()}\n")


def append_task(project_path: str, text: str) -> None:
    path = init_project(project_path)
    stamp = datetime.now().strftime("%Y-%m-%d")
    with (path / "TASKS.md").open("a", encoding="utf-8") as f:
        f.write(f"\n- [ ] {text.strip()} _(added {stamp})_\n")


def agent_context_preamble(project_path: str) -> str:
    path = Path(project_path).expanduser()
    names = ["AGENTS.md", "PROJECT_CONTEXT.md", "TASKS.md", "DECISIONS.md", "HANDOFF.md"]
    existing = [name for name in names if (path / name).exists()]
    if not existing:
        return ""
    files = "\n".join(f"- {name}" for name in existing)
    return (
        "Project memory is stored in this working directory. "
        "Before substantive work, read the relevant shared memory files:\n"
        f"{files}\n\nUpdate HANDOFF.md before stopping.\n\n"
    )


def _safe_project_name(raw: str) -> str:
    name = raw.strip().replace(" ", "-")
    name = "".join("-" if ch in {"/", "\\", ":"} or ord(ch) < 32 else ch for ch in name)
    while "--" in name:
        name = name.replace("--", "-")
    name = name.strip("-")
    if not name or name in {".", ".."}:
        raise ValueError(f"invalid project name: {raw!r}")
    return name


def _read_preview(path: Path, max_chars: int = 1800) -> str:
    if not path.exists():
        return "_Missing._"
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return "_Empty._"
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n... truncated ..."


def _write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
