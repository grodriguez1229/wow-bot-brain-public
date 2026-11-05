from prompts import build_motivation_line, CHAT_PROMPT, TICK_PROMPT


def test_flavor_line_per_motivation():
    assert "gold" in build_motivation_line("gold_maker").lower()
    assert build_motivation_line("dungeon_seeker")
    assert build_motivation_line("") == ""


def test_prompts_have_motivation_placeholder():
    assert "{motivation_line}" in CHAT_PROMPT
    assert "{motivation_line}" in TICK_PROMPT


import random
from personality import pick_tick_activity


def _channel_dist(motivation, n=300):
    random.seed(7)
    counts = {}
    for _ in range(n):
        a = pick_tick_activity(20, "Mage", "Elwynn Forest", has_guild=True, motivation=motivation)
        counts[a["channel"]] = counts.get(a["channel"], 0) + 1
    return counts


def test_gold_maker_favors_trade():
    d = _channel_dist("gold_maker")
    assert d.get("TRADE", 0) > d.get("SAY", 0)


def test_dungeon_seeker_favors_lfg():
    d = _channel_dist("dungeon_seeker")
    assert d.get("LFG", 0) >= max(d.values()) * 0.5


def test_explorer_favors_say():
    d = _channel_dist("world_explorer")
    assert d.get("SAY", 0) > 0
