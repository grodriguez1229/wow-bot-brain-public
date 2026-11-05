import random
from prompts import CHAT_PROMPT, TICK_PROMPT
from personality import pick_tick_activity


# ── CHAT_PROMPT: persona surfaces + topic range ───────────────────────────────

def test_chat_prompt_is_person_forward():
    # The real person should be the lead, not buried under the character line.
    assert "{who}" in CHAT_PROMPT
    low = CHAT_PROMPT.lower()
    assert "real person" in low
    # person introduced before the character block
    assert low.index("{who}") < low.index("{current_goal}")


def test_chat_prompt_asks_for_one_short_line():
    low = CHAT_PROMPT.lower()
    assert "2-4 sentences" not in low          # R9: the long cue produced run-ons
    assert "one short line, like a whisper" in low
    # the old hard cap is gone
    assert "5-15 words is ideal" not in low


def test_chat_prompt_has_persona_surface_rule():
    low = CHAT_PROMPT.lower()
    assert "ask about you" in low or "your day" in low or "your life" in low


def test_chat_prompt_widens_topics_beyond_grind():
    from prompts import CHAT_LIFE_RULE_OPEN, CHAT_LIFE_RULE_GAME
    assert "{life_rule}" in CHAT_PROMPT
    assert "not just" in CHAT_LIFE_RULE_OPEN.lower()  # "...not just quests and grinding"
    assert "not just" in CHAT_LIFE_RULE_GAME.lower()


def test_chat_prompt_keeps_guards():
    low = CHAT_PROMPT.lower()
    assert "no emoji" in low
    assert "never reveal you're an ai" in low
    assert "{action_rules}" in CHAT_PROMPT
    # format placeholders main.py depends on
    for ph in ("{name}", "{level}", "{race}", "{class_name}", "{faction}",
               "{typing_style}", "{mood}", "{motivation_line}",
               "{context_section}", "{memory_section}", "{nearby_section}", "{life_rule}"):
        assert ph in CHAT_PROMPT, ph


# ── TICK_PROMPT: stays terse, widens beyond errands ───────────────────────────

def test_tick_prompt_stays_one_line():
    low = TICK_PROMPT.lower()
    assert "one short line" in low or "one line" in low


def test_tick_prompt_widens_beyond_errands():
    low = TICK_PROMPT.lower()
    assert "not just" in low  # "...not just LFG/WTS/quests"


def test_tick_prompt_keeps_format_placeholders():
    for ph in ("{name}", "{level}", "{race}", "{class_name}", "{faction}",
               "{who}", "{typing_style}", "{mood}", "{current_goal}",
               "{motivation_line}", "{nearby_section}"):
        assert ph in TICK_PROMPT, ph


# ── pick_tick_activity: banter/IRL lane added ─────────────────────────────────

def test_tick_mix_includes_banter():
    random.seed(3)
    prompts = [pick_tick_activity(20, "Mage", "Elwynn Forest", has_guild=True)["prompt"]
               for _ in range(200)]
    assert any("real life" in p.lower() for p in prompts)
