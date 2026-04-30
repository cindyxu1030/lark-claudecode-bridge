from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RoutingDecision:
    should_respond: bool
    cleaned_text: str
    mentioned_self: bool
    mentioned_other: bool
    reason: str


def route_message_for_agent(
    text: str,
    mentions: Sequence[dict] | None,
    *,
    is_group: bool,
    self_aliases: Iterable[str],
    other_aliases: Iterable[str],
    self_ids: Iterable[str] = (),
    other_ids: Iterable[str] = (),
) -> RoutingDecision:
    """Apply multi-bot group routing rules.

    Rules:
    - Direct/private chats always respond.
    - Group message with no bot mention: respond.
    - Group message mentioning this bot: respond.
    - Group message mentioning only the other bot: ignore.
    """
    self_aliases = tuple(_clean_alias(a) for a in self_aliases if _clean_alias(a))
    other_aliases = tuple(_clean_alias(a) for a in other_aliases if _clean_alias(a))
    self_ids = {v.strip() for v in self_ids if v and v.strip()}
    other_ids = {v.strip() for v in other_ids if v and v.strip()}

    text = text or ""
    mentions = mentions or []
    mentioned_self = _text_mentions_alias(text, self_aliases) or _mentions_match(mentions, self_aliases, self_ids)
    mentioned_other = _text_mentions_alias(text, other_aliases) or _mentions_match(mentions, other_aliases, other_ids)
    cleaned = clean_bot_mentions(text, mentions, (*self_aliases, *other_aliases))

    if not is_group:
        return RoutingDecision(True, cleaned, mentioned_self, mentioned_other, "direct")
    if mentioned_self:
        return RoutingDecision(True, cleaned, mentioned_self, mentioned_other, "self_mentioned")
    if mentioned_other:
        return RoutingDecision(False, cleaned, mentioned_self, mentioned_other, "other_bot_mentioned")
    return RoutingDecision(True, cleaned, mentioned_self, mentioned_other, "no_bot_mentioned")


def clean_bot_mentions(text: str, mentions: Sequence[dict] | None, aliases: Iterable[str]) -> str:
    cleaned = text or ""
    for mention in mentions or []:
        key = str(mention.get("key", "")).strip()
        if key:
            cleaned = cleaned.replace(key, "")
    for alias in sorted({_clean_alias(a) for a in aliases if _clean_alias(a)}, key=len, reverse=True):
        cleaned = _remove_visible_mention(cleaned, alias)
    return _normalize_spacing(cleaned)


def extract_text_for_routing(msg_type: str, content) -> str:
    if msg_type == "text":
        if isinstance(content, dict):
            return str(content.get("text", ""))
        return str(content or "")

    if msg_type != "post":
        return ""

    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return ""

    if "text" in content and "content" not in content and len(content) <= 2:
        return str(content.get("text", ""))

    body = content.get("content")
    if not isinstance(body, list):
        for lang_key in ("zh_cn", "en_us", "ja_jp"):
            lang_body = content.get(lang_key)
            if isinstance(lang_body, dict) and isinstance(lang_body.get("content"), list):
                body = lang_body["content"]
                break

    parts: list[str] = []
    if isinstance(body, list):
        for paragraph in body:
            if not isinstance(paragraph, list):
                continue
            for node in paragraph:
                if not isinstance(node, dict):
                    continue
                tag = node.get("tag", "")
                if tag in {"text", "a", "at"}:
                    parts.append(str(node.get("text", "")))
    return " ".join(p for p in parts if p).strip()


def _mentions_match(mentions: Sequence[dict], aliases: Sequence[str], ids: set[str]) -> bool:
    alias_norm = {_normalize_alias(a) for a in aliases}
    for mention in mentions:
        values = _mention_values(mention)
        if ids and any(value in ids for value in values):
            return True
        if alias_norm and any(_normalize_alias(value) in alias_norm for value in values):
            return True
    return False


def _mention_values(mention: dict) -> set[str]:
    values: set[str] = set()
    for key in ("name", "key", "tenant_key"):
        value = mention.get(key)
        if value:
            values.add(str(value).strip())
    mention_id = mention.get("id")
    if isinstance(mention_id, dict):
        for key in ("open_id", "union_id", "user_id", "name"):
            value = mention_id.get(key)
            if value:
                values.add(str(value).strip())
    return {v for v in values if v}


def _text_mentions_alias(text: str, aliases: Sequence[str]) -> bool:
    return any(_visible_mention_pattern(alias).search(text or "") for alias in aliases)


def _remove_visible_mention(text: str, alias: str) -> str:
    return _visible_mention_pattern(alias).sub("", text)


def _visible_mention_pattern(alias: str) -> re.Pattern:
    # Lark can render bot tags as plain visible text in compact events.
    pieces = [re.escape(piece) for piece in alias.split()]
    alias_expr = r"\s+".join(pieces)
    return re.compile(rf"(?<![\w@.])[@＠]\s*{alias_expr}(?![\w-])", re.IGNORECASE)


def _normalize_alias(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lstrip("@＠")).casefold()


def _clean_alias(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lstrip("@＠"))


def _normalize_spacing(value: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in (value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()
