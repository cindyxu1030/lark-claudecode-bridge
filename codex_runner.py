"""
Run the local Codex CLI and parse its JSONL event stream.

This mirrors the old Claude runner contract so the Lark bridge can keep its
existing card streaming, cancellation, and per-chat session handling.
"""

import asyncio
import json
import os
from typing import Callable, Optional

from bot_config import CODEX_CLI, CODEX_HOME, PERMISSION_MODE

IDLE_TIMEOUT = 900  # 15 minutes without output is treated as a hung run.


def _permission_args(permission_mode: Optional[str]) -> list[str]:
    """Return global Codex CLI permission flags.

    Newer Codex CLI versions accept approval flags at the top level, not after
    `codex exec`. Keep these args before the subcommand when building commands.
    """
    mode = permission_mode or PERMISSION_MODE
    if mode == "plan":
        return ["--ask-for-approval", "never", "--sandbox", "read-only"]
    if mode in {"bypassPermissions", "dontAsk"}:
        if os.getenv("CODEX_DANGEROUS_BYPASS", "").lower() in {"1", "true", "yes"}:
            return ["--dangerously-bypass-approvals-and-sandbox"]
        return ["--ask-for-approval", "never", "--sandbox", "workspace-write"]
    if mode == "acceptEdits":
        return ["--ask-for-approval", "on-request", "--sandbox", "workspace-write"]
    return ["--ask-for-approval", "on-request", "--sandbox", "workspace-write"]


def _prompt_for_mode(message: str, permission_mode: Optional[str]) -> str:
    if (permission_mode or PERMISSION_MODE) != "plan":
        return message
    return (
        "Plan only. Do not modify files or run write operations. "
        "Give the implementation plan and stop.\n\n"
        + message
    )


async def _fire_callback(cb, *args):
    if cb is None:
        return
    if asyncio.iscoroutinefunction(cb):
        await cb(*args)
    else:
        cb(*args)


async def run_codex(
    message: str,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    cwd: Optional[str] = None,
    permission_mode: Optional[str] = None,
    on_text_chunk: Optional[Callable[[str], None]] = None,
    on_tool_use: Optional[Callable[[str, dict], None]] = None,
    on_process_start: Optional[Callable[[asyncio.subprocess.Process], None]] = None,
) -> tuple[str, Optional[str], bool]:
    """
    Invoke Codex CLI and stream JSONL events.

    Returns:
        (full_response_text, new_session_id, used_fresh_session_fallback)
    """

    async def _run_once(active_session_id: Optional[str]) -> tuple[str, Optional[str], int, str]:
        global_args = _permission_args(permission_mode)
        exec_args = [
            "--json",
            "--skip-git-repo-check",
        ]
        if model:
            exec_args += ["--model", model]

        prompt = _prompt_for_mode(message, permission_mode)
        if active_session_id:
            cmd = [CODEX_CLI, *global_args, "exec", "resume", *exec_args, active_session_id, "-"]
        else:
            cmd = [CODEX_CLI, *global_args, "exec", *exec_args, "-"]

        env = os.environ.copy()
        env["CODEX_HOME"] = os.path.expanduser(CODEX_HOME)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or os.path.expanduser("~"),
            env=env,
            limit=10 * 1024 * 1024,
        )

        await _fire_callback(on_process_start, proc)

        proc.stdin.write((prompt + "\n").encode())
        await proc.stdin.drain()
        proc.stdin.close()

        full_text = ""
        new_session_id = active_session_id

        while True:
            try:
                raw_line = await asyncio.wait_for(proc.stdout.readline(), timeout=IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise RuntimeError(f"Codex timed out after {IDLE_TIMEOUT}s without output; process killed")

            if not raw_line:
                break

            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = data.get("type")
            if event_type == "thread.started":
                new_session_id = data.get("thread_id") or new_session_id
                continue

            item = data.get("item")
            if isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type == "agent_message":
                    text = item.get("text", "")
                    if text:
                        if not full_text:
                            await _fire_callback(on_text_chunk, text)
                        full_text = text
                elif item_type in {"tool_call", "function_call", "command_execution"}:
                    name = item.get("name") or item.get("tool_name") or item_type
                    inp = item.get("arguments") or item.get("input") or {}
                    if not isinstance(inp, dict):
                        inp = {"value": inp}
                    await _fire_callback(on_tool_use, name, inp)

        stderr_output = await proc.stderr.read()
        await proc.wait()
        stderr_text = stderr_output.decode("utf-8", errors="replace").strip()
        return full_text.strip(), new_session_id, proc.returncode, stderr_text

    final_text, new_session_id, returncode, stderr_text = await _run_once(session_id)
    used_fresh_session_fallback = False

    if session_id and returncode != 0 and not final_text:
        print("[run_codex] resume failed, retrying with fresh session", flush=True)
        final_text, new_session_id, returncode, stderr_text = await _run_once(None)
        used_fresh_session_fallback = True

    if returncode != 0:
        detail = stderr_text or "no stderr"
        if final_text:
            return final_text, new_session_id, used_fresh_session_fallback
        raise RuntimeError(f"codex exited with code {returncode}: {detail}")

    return final_text, new_session_id, used_fresh_session_fallback
