from prompts import IRL_DENIED_RULE, TICK_PROMPT, build_irl_section

IRL = {"irl_facts": ["works at GameStop", "has a cat named Mochi"],
       "signature": "my girlfriend says hi", "signature_irl": True}


def test_tick_prompt_has_irl_placeholder_and_no_static_irl_rule():
    assert "{irl_section}" in TICK_PROMPT
    assert "real-life aside" not in TICK_PROMPT.lower()
    assert "not just" in TICK_PROMPT.lower()


def test_allowed_includes_facts_and_permission():
    s = build_irl_section(IRL, allowed=True)
    assert "works at GameStop; has a cat named Mochi" in s
    assert "real-life aside" in s.lower()
    assert IRL_DENIED_RULE not in s


def test_denied_has_rule_and_no_facts():
    s = build_irl_section(IRL, allowed=False)
    assert IRL_DENIED_RULE in s
    assert "GameStop" not in s and "Mochi" not in s


def test_irl_signature_only_when_allowed():
    assert "my girlfriend says hi" in build_irl_section(IRL, allowed=True, signature_on=True)
    assert "my girlfriend says hi" not in build_irl_section(IRL, allowed=False, signature_on=True)
    assert "my girlfriend says hi" not in build_irl_section(IRL, allowed=True, signature_on=False)


def test_non_irl_signature_offered_even_when_denied():
    irl = {"irl_facts": [], "signature": "hooah", "signature_irl": False}
    assert "hooah" in build_irl_section(irl, allowed=False, signature_on=True)


def test_pinned_or_empty_irl_is_safe():
    assert build_irl_section({"pinned": True}, allowed=True)          # permission rule only
    assert "YOUR LIFE" not in build_irl_section({"pinned": True}, allowed=True)
    assert IRL_DENIED_RULE in build_irl_section(None, allowed=False)
