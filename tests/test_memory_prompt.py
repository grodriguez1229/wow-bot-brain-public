from memory_prompt import build_nearby_section, build_relationship_section
from prompts import CHAT_PROMPT, TICK_PROMPT


def test_nearby_section_empty_when_no_lines():
    assert build_nearby_section(None) == ""
    assert build_nearby_section([]) == ""


def test_nearby_section_renders_lines():
    out = build_nearby_section([
        {"speaker": "Lynea", "text": "anyone running Deadmines?"},
        {"speaker": "Geysse", "text": "nah im broke"},
    ])
    assert "OVERHEARD NEARBY" in out
    assert "don't repeat it" in out
    assert "  Lynea: anyone running Deadmines?" in out
    assert "  Geysse: nah im broke" in out


def test_relationship_section_empty_when_no_notes():
    assert build_relationship_section({"familiarity": 0, "notes": ""}) == ""
    assert build_relationship_section(None) == ""


def test_relationship_section_renders_notes():
    out = build_relationship_section({"familiarity": 12, "notes": "ran Deadmines together, owes you 2g"})
    assert "ran Deadmines together, owes you 2g" in out


def test_both_prompts_have_nearby_placeholder():
    assert "{nearby_section}" in CHAT_PROMPT
    assert "{nearby_section}" in TICK_PROMPT


def test_tick_prompt_formats_with_nearby_section():
    s = TICK_PROMPT.format(
        name="Geysse", level=16, race="Dwarf", class_name="Rogue", faction="Alliance",
        who="a tired night-shift nurse", typing_style="terse", mood="chill",
        current_goal="grind to 17", nearby_section="OVERHEARD NEARBY:\n  Lynea: hey",
        motivation_line="", self_section="", identity_section="", state_line="",
        irl_section="", examples_section="",
    )
    assert "OVERHEARD NEARBY" in s


def test_chat_prompt_formats_with_nearby_section():
    s = CHAT_PROMPT.format(
        name="Geysse", level=16, race="Dwarf", class_name="Rogue", faction="Alliance",
        who="a tired night-shift nurse", typing_style="terse", mood="chill",
        current_goal="grind to 17", context_section="TALKING TO: Gus",
        memory_section="", nearby_section="OVERHEARD NEARBY:\n  Lynea: hey",
        action_rules="", motivation_line="", self_section="", identity_section="", life_rule="",
        examples_section="", moments_section="",
    )
    assert "OVERHEARD NEARBY" in s
