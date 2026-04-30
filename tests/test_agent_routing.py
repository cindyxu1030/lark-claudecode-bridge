from agent_routing import extract_text_for_routing, route_message_for_agent


def test_group_message_without_bot_mention_responds():
    decision = route_message_for_agent(
        "please review this",
        [],
        is_group=True,
        self_aliases=("Codex",),
        other_aliases=("Claude", "Claude Code"),
    )

    assert decision.should_respond is True
    assert decision.reason == "no_bot_mentioned"
    assert decision.cleaned_text == "please review this"


def test_group_message_mentions_self_responds_and_strips_visible_tag():
    decision = route_message_for_agent(
        "@Codex say cwd",
        [],
        is_group=True,
        self_aliases=("Codex",),
        other_aliases=("Claude", "Claude Code"),
    )

    assert decision.should_respond is True
    assert decision.mentioned_self is True
    assert decision.cleaned_text == "say cwd"


def test_group_message_mentions_other_bot_is_ignored():
    decision = route_message_for_agent(
        "@Claude say cwd",
        [],
        is_group=True,
        self_aliases=("Codex",),
        other_aliases=("Claude", "Claude Code"),
    )

    assert decision.should_respond is False
    assert decision.reason == "other_bot_mentioned"


def test_group_message_mentions_both_bots_responds():
    decision = route_message_for_agent(
        "@Claude @Codex compare approaches",
        [],
        is_group=True,
        self_aliases=("Codex",),
        other_aliases=("Claude", "Claude Code"),
    )

    assert decision.should_respond is True
    assert decision.mentioned_self is True
    assert decision.mentioned_other is True
    assert decision.cleaned_text == "compare approaches"


def test_structured_mention_name_routes_to_self_and_strips_key():
    decision = route_message_for_agent(
        "@_user_1 say cwd",
        [{"key": "@_user_1", "name": "Codex"}],
        is_group=True,
        self_aliases=("Codex",),
        other_aliases=("Claude",),
    )

    assert decision.should_respond is True
    assert decision.mentioned_self is True
    assert decision.cleaned_text == "say cwd"


def test_extract_text_for_routing_handles_post_content():
    content = {
        "content": [
            [
                {"tag": "at", "text": "@Codex"},
                {"tag": "text", "text": " discuss this"},
            ]
        ]
    }

    assert extract_text_for_routing("post", content) == "@Codex  discuss this"
