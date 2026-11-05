import random

import chat_log as cl


def setup_function():
    cl.reset_state()


def _cands(bot="Me", **kw):
    args = dict(faction="Horde", zone="Barrens", guild="Wolves", nearby=(), now=100.0)
    args.update(kw)
    return cl.reply_candidates(bot, **args)


def test_general_scoped_by_zone_and_faction():
    cl.record_line("A", "GENERAL", "where is mankrik's wife", faction="Horde", zone="Barrens", now=90)
    cl.record_line("B", "GENERAL", "hi", faction="Alliance", zone="Barrens", now=90)
    cl.record_line("C", "GENERAL", "yo", faction="Horde", zone="Durotar", now=90)
    assert [e["speaker"] for e in _cands()] == ["A"]


def test_trade_lfg_faction_wide_and_player_lines_match_any_faction():
    cl.record_line("A", "LFG", "lfm wc", faction="Horde", zone="Durotar", now=90)
    cl.record_line("Gus", "TRADE", "wtb linen", faction=None, zone="Elwynn", now=90)
    cl.record_line("B", "TRADE", "wts ore", faction="Alliance", now=90)
    assert {e["speaker"] for e in _cands()} == {"A", "Gus"}


def test_guild_and_say_scopes():
    cl.record_line("G", "GUILD", "anyone on", guild="Wolves", now=90)
    cl.record_line("H", "GUILD", "hey", guild="Other", now=90)
    cl.record_line("S", "SAY", "oom", zone="Barrens", now=90)
    cl.record_line("T", "SAY", "brb", zone="Barrens", now=90)
    got = {e["speaker"] for e in _cands(nearby=("S",))}
    assert got == {"G", "S"}
    assert "G" not in {e["speaker"] for e in _cands(guild=None)}


def test_own_lines_and_stale_lines_excluded():
    cl.record_line("Me", "LFG", "lfg", faction="Horde", now=90)
    cl.record_line("A", "LFG", "old", faction="Horde", now=100 - cl.CHAT_LOG_TTL_S - 1)
    assert _cands() == []


def test_depth_cap_and_reply_counts():
    root = cl.record_line("A", "LFG", "need tank?", faction="Horde", now=90)
    r1 = cl.record_line("B", "LFG", "me", faction="Horde", reply_to=root, now=91)
    r2 = cl.record_line("A", "LFG", "inv", faction="Horde", reply_to=r1, now=92)
    r3 = cl.record_line("B", "LFG", "ty", faction="Horde", reply_to=r2, now=93)
    e3 = cl.get(r3)
    assert e3["depth"] == 3 and e3["root"] == root
    ids = {e["id"] for e in _cands(bot="C")}
    assert r3 not in ids                      # depth cap 3 reached
    assert root in ids and r1 in ids          # each has 1 reply < 2


def test_max_direct_replies_and_no_double_reply():
    root = cl.record_line("A", "GENERAL", "lol", faction="Horde", zone="Barrens", now=90)
    cl.record_line("B", "GENERAL", "ha", faction="Horde", zone="Barrens", reply_to=root, now=91)
    assert root not in {e["id"] for e in _cands(bot="B")}      # B already replied
    cl.record_line("C", "GENERAL", "lmao", faction="Horde", zone="Barrens", reply_to=root, now=92)
    assert root not in {e["id"] for e in _cands(bot="D")}      # 2 replies -> closed


def test_pick_prefers_unanswered_questions():
    q = cl.record_line("A", "GENERAL", "anyone know where the inn is", faction="Horde",
                       zone="Barrens", now=99)
    s = cl.record_line("B", "GENERAL", "this zone is big", faction="Horde", zone="Barrens", now=99)
    rng = random.Random(0)
    picks = [cl.pick_reply_target(_cands(), rng, now=100)["id"] for _ in range(600)]
    assert picks.count(q) > 2 * picks.count(s)
    assert cl.pick_reply_target([], rng) is None


def test_is_question():
    assert cl.is_question("where is the inn")
    assert cl.is_question("u doing this quest too?")
    assert not cl.is_question("this zone is ugly")


def test_recent_context_ends_with_target():
    ids = [cl.record_line(f"S{i}", "GENERAL", f"line {i}", faction="Horde", zone="Barrens",
                          now=90 + i) for i in range(6)]
    cl.record_line("X", "GENERAL", "elsewhere", faction="Horde", zone="Durotar", now=92.5)
    tgt = cl.get(ids[3])
    ctx = cl.recent_context(tgt, n=3)
    assert [e["text"] for e in ctx] == ["line 1", "line 2", "line 3"]


def test_yell_and_party_map_to_say():
    eid = cl.record_line("Gus", "YELL", "HELP", zone="Barrens", now=90)
    assert cl.get(eid)["channel"] == "SAY"


def test_ring_buffer_bounded():
    for i in range(cl.CHAT_LOG_MAXLEN + 10):
        cl.record_line("A", "LFG", str(i), faction="Horde", now=90)
    assert len(cl._log) == cl.CHAT_LOG_MAXLEN == len(cl._by_id)
