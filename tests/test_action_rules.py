from prompts import build_action_rules


def test_invite_tag_targets_the_player():
    out = build_action_rules("Abril", caps={"party_invite"})
    assert "[ACTION:invite Abril]" in out
    assert "[ACTION:emote" not in out   # R9: emotes never reached the game; not offered


def test_handles_missing_name():
    assert "[ACTION:invite them]" in build_action_rules("", caps={"party_invite"})


def test_guildinvite_present_only_with_capability():
    assert "guildinvite" not in build_action_rules("Gus", caps={"party_invite"})
    out = build_action_rules("Gus", caps={"party_invite", "guild_invite"})
    assert "[ACTION:guildinvite Gus]" in out


def test_does_not_leak_tag_instruction_as_speech():
    assert "Never say the tag out loud" in build_action_rules("Gus", caps={"party_invite"})


def test_no_party_invite_without_capability():
    # Ambient/heard reactions pass no invite caps -> no real invite is offered or forced.
    out = build_action_rules("Gus", caps=set())
    assert "[ACTION:invite" not in out
    assert "guildinvite" not in out
    assert "you MUST" not in out
    assert out == ""  # R9: nothing to offer -> no action block at all
