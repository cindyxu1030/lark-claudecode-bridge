from __future__ import annotations

import os
from dataclasses import dataclass

import bot_config as config
from agent_hub import agent_context_preamble, append_discussion
from claude_runner import run_claude
from codex_runner import run_codex


@dataclass(frozen=True)
class DiscussionResult:
    summary: str
    transcript: str
    discussion_path: str


async def run_agent_discussion(
    topic: str,
    *,
    cwd: str,
    coordinator: str,
) -> DiscussionResult:
    """Run a bounded Claude/Codex discussion and persist the transcript."""
    topic = topic.strip()
    cwd = os.path.expanduser(cwd or "~")
    context = agent_context_preamble(cwd)
    base = (
        f"{context}"
        "You are participating in a private agent-to-agent discussion for a Lark group chat. "
        "Do not modify files. Do not ask the user follow-up questions. "
        "Be concrete, concise, and point out risks or disagreements.\n\n"
        f"Working directory: {cwd}\n"
        f"Discussion topic: {topic}\n"
    )

    claude_first = await _call_claude(
        "Claude",
        base
        + "\nClaude: give your initial analysis, recommended approach, and any risks. "
        "Keep it under 500 words.",
        cwd,
    )
    codex_reply = await _call_codex(
        "Codex",
        base
        + "\nClaude's initial view:\n"
        + claude_first
        + "\n\nCodex: respond to Claude. Agree, disagree, add implementation details, "
        "and propose a practical path. Keep it under 500 words.",
        cwd,
    )
    claude_final = await _call_claude(
        "Claude",
        base
        + "\nClaude initial view:\n"
        + claude_first
        + "\n\nCodex response:\n"
        + codex_reply
        + "\n\nClaude: give a final reconciliation. Highlight what should be done next. "
        "Keep it under 350 words.",
        cwd,
    )

    transcript = (
        "### Claude initial\n\n"
        + claude_first.strip()
        + "\n\n### Codex response\n\n"
        + codex_reply.strip()
        + "\n\n### Claude final\n\n"
        + claude_final.strip()
        + "\n"
    )
    summary_prompt = (
        base
        + "\nDiscussion transcript:\n"
        + _limit(transcript, 12000)
        + "\n\nWrite the user-facing summary. Include: consensus, disagreements, risks, and next steps. "
        "Keep it short enough for a chat card."
    )
    if coordinator.lower() == "claude":
        summary = await _call_claude("Claude summary", summary_prompt, cwd)
    else:
        summary = await _call_codex("Codex summary", summary_prompt, cwd)

    discussion_path = ""
    try:
        discussion_path = str(append_discussion(
            cwd,
            topic=topic,
            summary=summary,
            transcript=transcript,
            coordinator=coordinator,
        ))
    except Exception as exc:
        discussion_path = f"not saved: {type(exc).__name__}: {exc}"

    return DiscussionResult(summary=summary.strip(), transcript=transcript, discussion_path=discussion_path)


async def _call_claude(label: str, prompt: str, cwd: str) -> str:
    try:
        text, _, _ = await run_claude(
            message=prompt,
            session_id=None,
            model=config.COLLAB_CLAUDE_MODEL,
            cwd=cwd,
            permission_mode="plan",
        )
        return text.strip() or f"{label} returned no output."
    except Exception as exc:
        return f"{label} failed: {type(exc).__name__}: {exc}"


async def _call_codex(label: str, prompt: str, cwd: str) -> str:
    try:
        text, _, _ = await run_codex(
            message=prompt,
            session_id=None,
            model=config.COLLAB_CODEX_MODEL,
            cwd=cwd,
            permission_mode="plan",
        )
        return text.strip() or f"{label} returned no output."
    except Exception as exc:
        return f"{label} failed: {type(exc).__name__}: {exc}"


def _limit(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n\n... truncated ..."
