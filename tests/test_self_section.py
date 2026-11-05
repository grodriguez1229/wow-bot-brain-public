from memory_prompt import build_self_section
from prompts import CHAT_PROMPT, TICK_PROMPT


def test_empty_self_section_renders_nothing():
    assert build_self_section([]) == ""
    assert build_self_section(None) == ""


def test_self_section_formats_notes():
    out = build_self_section([{"subject": "mood", "content": "burned out"},
                              {"subject": "interests", "content": "into fishing"}])
    assert "burned out" in out
    assert "into fishing" in out
    low = out.lower()
    assert "yourself" in low or "you've been" in low


def test_prompts_have_self_placeholder():
    assert "{self_section}" in CHAT_PROMPT
    assert "{self_section}" in TICK_PROMPT
