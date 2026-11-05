"""R9 Task 9: login whisper planner and grounded opener."""
import asyncio
import random
import time

import pytest

T0 = 1_800_000_000.0


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    import presence
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    presence.reset_state()
    yield db
    presence.reset_state()


@pytest.fixture
def lw(fresh_db, monkeypatch):
    import login_whisper
    monkeypatch.setattr(login_whisper, "FRIENDS_ENABLED", True)
    monkeypatch.setattr(login_whisper, "LOGIN_WHISPER_RATE", 1.0)
    monkeypatch.setattr(login_whisper, "SECOND_WHISPER_RATE", 0.0)
    return login_whisper


def _persona(monkeypatch, name, *, level=12, faction="Alliance", race="Night Elf",
             class_name="Hunter"):
    import personality
    monkeypatch.setitem(personality._personality_cache, name, {
        "bot_name": name, "level": level, "faction": faction, "race": race,
        "class_name": class_name, "gender": "male", "who": "a college kid who games too much",
        "typing_style": "lowercase, fast", "identity_id": "none", "current_goal": "level up",
        "irl": {"who_core": "a college kid who games too much"}})
    monkeypatch.setitem(personality._level_checked, name, time.monotonic())


def _online(bot, *, now=T0, activity="questing", zone="Darkshore"):
    import presence
    presence.note_tick(bot, zone=zone, subzone=None, activity=activity, now=now)


def _runs(player, bot, n, *, instance="Wailing Caverns", now=T0):
    import history
    for i in range(n):
        sid = history.open_session(player, bot, "run", instance=instance, now=now - 7200 + i * 600)
        history.close_session(sid, ended_at=now - 7200 + i * 600 + 400, outcome="cleared")


def _friend(monkeypatch, bot, player="Abril", *, fam=28, runs=2, now=T0, **kw):
    import friendship
    _persona(monkeypatch, bot, **kw)
    friendship.add_play(bot, player, fam, now=now - 60)
    _runs(player, bot, runs, now=now)
    _online(bot, now=now)


def _plan(lw, player="Abril", *, level=10, faction="Alliance", seed=1, now=T0):
    return lw.plan_login(player, level=level, faction=faction, rng=random.Random(seed), now=now)


# ── planner ───────────────────────────────────────────────────────────────────

def test_stranger_never_planned(lw, monkeypatch):
    import friendship
    _persona(monkeypatch, "Trean")
    friendship.add_chat("Trean", "Abril", 5, now=T0 - 60)
    _online("Trean")
    assert _plan(lw) == []


def test_chat_only_acquaintance_never_planned(lw, monkeypatch):
    import friendship
    _persona(monkeypatch, "Trean")
    for i in range(40):
        friendship.add_chat("Trean", "Abril", now=T0 - 600 + i)
    _online("Trean")
    assert _plan(lw) == []


def test_friend_with_two_runs_planned(lw, monkeypatch):
    _friend(monkeypatch, "Trean")
    plans = _plan(lw)
    assert len(plans) == 1
    p = plans[0]
    assert p.bot == "Trean" and p.kind in ("callback", "invite", "checkin")
    assert 20 <= p.delay_s <= 120
    assert p.long_absence_days is None


def test_no_relationship_rows_created_for_other_bots(lw, monkeypatch, fresh_db):
    _friend(monkeypatch, "Trean")
    _persona(monkeypatch, "Other")
    _online("Other")                                 # online, but never met Abril
    _plan(lw)
    conn = fresh_db.get_db()
    rows = conn.execute("SELECT bot_name FROM relationships WHERE player_name='Abril'").fetchall()
    conn.close()
    assert [r["bot_name"] for r in rows] == ["Trean"]


def test_rate_roll_half(lw, monkeypatch):
    monkeypatch.setattr(lw, "LOGIN_WHISPER_RATE", 0.5)
    monkeypatch.setattr(lw, "LOGIN_WHISPER_COOLDOWN_S", 0)
    _friend(monkeypatch, "Trean")
    rng = random.Random(42)
    hits = sum(bool(lw.plan_login("Abril", level=10, faction="Alliance", rng=rng, now=T0))
               for _ in range(1000))
    assert 0.45 <= hits / 1000 <= 0.55


def test_max_two_whisperers(lw, monkeypatch):
    monkeypatch.setattr(lw, "SECOND_WHISPER_RATE", 1.0)
    for b in ("Aa", "Bb", "Cc", "Dd", "Ee"):
        _friend(monkeypatch, b)
    for seed in range(20):
        plans = _plan(lw, seed=seed)
        assert len(plans) == 2
        assert plans[0].bot != plans[1].bot
        assert plans[1].delay_s >= plans[0].delay_s + 30


def test_cross_faction_friend_never_planned(lw, monkeypatch):
    _friend(monkeypatch, "Grokk", faction="Horde", race="Orc", class_name="Warrior")
    for seed in range(10):
        assert _plan(lw, faction="Alliance", seed=seed) == []


def test_pair_cooldown_blocks_relog_whisper(lw, monkeypatch):
    import history
    _friend(monkeypatch, "Trean")
    history.add_event("Abril", "Trean", "login_whisper", detail="checkin", now=T0)
    _online("Trean", now=T0 + 600)
    assert _plan(lw, now=T0 + 600) == []
    _online("Trean", now=T0 + 72001)
    assert [p.bot for p in _plan(lw, now=T0 + 72001)] == ["Trean"]


def test_busy_or_stale_bot_not_planned(lw, monkeypatch):
    _friend(monkeypatch, "Trean")
    _online("Trean", now=T0, activity="in_combat")
    assert _plan(lw, now=T0) == []
    _online("Trean", now=T0, activity="dead")
    assert _plan(lw, now=T0) == []
    _online("Trean", now=T0 - 301, activity="questing")
    assert _plan(lw, now=T0) == []
    _online("Trean", now=T0 - 10, activity="questing")
    assert len(_plan(lw, now=T0)) == 1


def test_max_zero_plans_nothing(lw, monkeypatch, capsys):
    monkeypatch.setattr(lw, "LOGIN_WHISPER_MAX", 0)
    _friend(monkeypatch, "Trean")
    assert _plan(lw) == []
    assert "-> none (max=0)" in capsys.readouterr().out


def test_friends_disabled_plans_nothing(lw, monkeypatch):
    monkeypatch.setattr(lw, "FRIENDS_ENABLED", False)
    _friend(monkeypatch, "Trean")
    assert _plan(lw) == []


def test_long_absence_days(lw, monkeypatch):
    import history
    _friend(monkeypatch, "Trean")
    history.note_player_seen("Abril", logout=True, now=T0 - 9 * 86400)
    assert _plan(lw)[0].long_absence_days == 9
    history.note_player_seen("Abril", logout=True, now=T0 - 2 * 86400)
    assert _plan(lw)[0].long_absence_days is None


def test_kind_needs_moments_or_invite(lw, monkeypatch):
    # no moments, bot in a zone the player can't quest in -> only checkin is possible
    _friend(monkeypatch, "Trean", level=40)
    _online("Trean", zone="Stranglethorn Vale")
    for seed in range(20):
        assert _plan(lw, seed=seed)[0].kind == "checkin"


def test_invite_kind_carries_place(lw, monkeypatch):
    monkeypatch.setattr(lw, "KIND_WEIGHTS", {"callback": 0, "invite": 1, "checkin": 0})
    _friend(monkeypatch, "Trean")
    p = _plan(lw)[0]
    assert p.kind == "invite" and p.invite == {"type": "quest", "place": "Darkshore"}


def test_invite_option_rules(lw, monkeypatch):
    from knowledge import RAIDS, dungeons_for_level
    rng = random.Random(3)
    bot12 = {"level": 12}
    st = {"zone": "Darkshore", "activity": "questing"}
    assert lw.invite_option(bot12, st, 10, "Alliance", rng) == {"type": "quest", "place": "Darkshore"}
    assert lw.invite_option(bot12, {"zone": "Stranglethorn Vale", "activity": "questing"},
                            10, "Alliance", rng) is None
    assert lw.invite_option(bot12, None, 10, "Alliance", rng) is None
    assert lw.invite_option(bot12, dict(st, activity="in_combat"), 10, "Alliance", rng) is None
    assert lw.invite_option(bot12, dict(st, activity="dead"), 10, "Alliance", rng) is None
    monkeypatch.setattr(lw, "RUN_OFFER_RATE", 1.0)
    bot30 = {"level": 30}
    assert lw.invite_option(bot30, st, 10, "Alliance", rng) is None     # no dungeon at 10
    r = lw.invite_option(bot30, st, 15, "Alliance", rng)
    assert r["type"] == "run" and r["place"] in dungeons_for_level(15, "Alliance")
    raids = {r[0] for r in RAIDS}
    bot60 = {"level": 60}
    for lvl in range(1, 55):
        for zone in ("Darkshore", "Molten Core", "Blackrock Mountain", "Winterspring"):
            got = lw.invite_option(bot60, {"zone": zone, "activity": "questing"}, lvl,
                                   "Alliance", rng)
            assert got is None or got["place"] not in raids, (lvl, got)


# ── opener ────────────────────────────────────────────────────────────────────

def _fake_llm(monkeypatch, lw, *replies):
    calls = []

    async def fake(system, history, user, **kw):
        calls.append({"system": system, "user": user, **kw})
        return replies[min(len(calls) - 1, len(replies) - 1)]
    monkeypatch.setattr(lw, "call_ollama", fake)
    return calls


def _wc_moments(player="Abril", bot="Trean", n=3):
    import history
    ids = []
    for i in range(n):
        ids.append(history.add_moment(player, bot, f"ran Wailing Caverns together (run {i + 1})",
                                      source="run", source_id=i, places=["Wailing Caverns"],
                                      now=T0 - 1000 + i))
    return ids


def _open(lw, plan, player="Abril", zone=None, seed=0):
    return asyncio.run(lw.generate_opener(plan, player, player_zone=zone, rng=random.Random(seed)))


def _cb(lw, bot="Trean", kind="callback", invite=None, absence=None):
    return lw.Plan(bot=bot, kind=kind, delay_s=40, invite=invite, long_absence_days=absence)


def test_callback_cites_only_history(lw, monkeypatch):
    from knowledge import ungrounded_mentions
    _persona(monkeypatch, "Trean")
    ids = _wc_moments()
    calls = _fake_llm(monkeypatch, lw, "deadmines again tonight?", "lol wc again?")
    out = _open(lw, _cb(lw))
    assert len(calls) == 2
    assert out["fallback"] is False
    assert "wc again" in out["message"].lower()
    allowed = " ".join(f"ran Wailing Caverns together (run {i + 1})" for i in range(3))
    assert ungrounded_mentions(out["message"], allowed) == []
    assert sorted(out["moment_ids"]) == sorted(ids)
    assert out["actions"] == []
    assert calls[0]["lane"] == "chat" and calls[0]["num_predict"] == 24
    assert calls[0]["max_sentences"] == 2
    assert "Wailing Caverns" in calls[0]["system"]


def test_alias_not_in_history_rejected(lw, monkeypatch):
    """P3: "wc again?" with no Wailing Caverns history is ungrounded -> re-roll -> fallback."""
    import history
    _persona(monkeypatch, "Trean", level=20)
    history.add_moment("Abril", "Trean", "ran Deadmines together", source="run", source_id=1,
                       places=["Deadmines"], now=T0)
    calls = _fake_llm(monkeypatch, lw, "wc again?")
    out = _open(lw, _cb(lw))
    assert len(calls) == 2
    assert out["fallback"] is True
    assert out["message"] in lw.OPENER_FALLBACKS["callback"]
    assert out["moment_ids"] == []


def test_ungrounded_twice_uses_fallback(lw, monkeypatch):
    _persona(monkeypatch, "Trean")
    _wc_moments()
    calls = _fake_llm(monkeypatch, lw, "deadmines tonight?")
    out = _open(lw, _cb(lw))
    assert len(calls) == 2
    assert out["fallback"] is True
    assert out["message"] in lw.OPENER_FALLBACKS["callback"]


def test_opener_length_and_no_intro(lw, monkeypatch):
    from postfilter import is_self_intro
    _persona(monkeypatch, "Trean")
    _wc_moments()
    intro = "hey im trean, a level 12 night elf hunter, just wanted to say hi and see whats up today"
    assert len(intro) >= 85
    calls = _fake_llm(monkeypatch, lw, intro, "u up for more wc?")
    out = _open(lw, _cb(lw))
    assert len(calls) == 2
    assert len(out["message"]) <= 60
    assert not is_self_intro(out["message"], bot_name="Trean", race="Night Elf",
                             class_name="Hunter", level=12)
    assert out["fallback"] is False


def test_knowledge_violation_rerolls(lw, monkeypatch):
    _persona(monkeypatch, "Trean")
    _wc_moments()
    calls = _fake_llm(monkeypatch, lw, "molten core later?", "hey u on")
    out = _open(lw, _cb(lw))
    assert len(calls) == 2 and out["fallback"] is False


def test_invite_opener_has_real_invite_action(lw, monkeypatch):
    _persona(monkeypatch, "Trean")
    _fake_llm(monkeypatch, lw, "questing in darkshore, wanna group?")
    out = _open(lw, _cb(lw, kind="invite", invite={"type": "quest", "place": "Darkshore"}))
    assert out["actions"] == [{"type": "invite", "target": "Abril"}]
    assert out["fallback"] is False and "darkshore" in out["message"].lower()
    out = _open(lw, _cb(lw, kind="checkin"))
    assert out["actions"] == []


def test_invite_prompt_names_place_and_run(lw, monkeypatch):
    _persona(monkeypatch, "Trean", level=30)
    calls = _fake_llm(monkeypatch, lw, "want a run?")
    _open(lw, _cb(lw, kind="invite", invite={"type": "run", "place": "Deadmines"}))
    assert "Deadmines" in calls[0]["system"]
    assert "run them through" in calls[0]["system"]


def test_player_zone_and_said_lines_are_grounding(lw, monkeypatch, fresh_db):
    _persona(monkeypatch, "Trean")
    fresh_db.save_message("Trean", "Abril", "user", "stuck in westfall lol")
    _fake_llm(monkeypatch, lw, "still in westfall?")
    assert _open(lw, _cb(lw, kind="checkin"))["fallback"] is False
    _fake_llm(monkeypatch, lw, "u in darkshore?")
    assert _open(lw, _cb(lw, kind="checkin"), zone="Darkshore")["fallback"] is False


def test_checkin_fallback_where_u_been_only_on_long_absence(lw, monkeypatch):
    _persona(monkeypatch, "Trean")
    _fake_llm(monkeypatch, lw, "deadmines?")          # always ungrounded -> fallback
    seen = {_open(lw, _cb(lw, kind="checkin"), seed=s)["message"] for s in range(60)}
    assert "where u been" not in seen
    assert seen <= set(lw.OPENER_FALLBACKS["checkin"])
    seen = {_open(lw, _cb(lw, kind="checkin", absence=10), seed=s)["message"] for s in range(60)}
    assert "where u been" in seen


def test_empty_llm_line_uses_fallback(lw, monkeypatch):
    _persona(monkeypatch, "Trean")
    calls = _fake_llm(monkeypatch, lw, "")
    out = _open(lw, _cb(lw, kind="checkin"))
    assert len(calls) == 2 and out["fallback"] is True and isinstance(out["message"], str)
    assert out["message"]


def test_prompt_has_no_self_statement_instruction(lw, monkeypatch):
    _persona(monkeypatch, "Trean")
    _wc_moments()
    calls = _fake_llm(monkeypatch, lw, "lol wc")
    _open(lw, _cb(lw))
    s = calls[0]["system"]
    assert "a college kid who games too much" in s
    assert "Trean, level 12 Night Elf Hunter" in s
    assert "Greetings" in s                      # named only as a thing not to do
    assert "never" in s.lower() or "don't" in s.lower()


def test_whisper_ab_opener_path(tmp_path, monkeypatch):
    import json
    import os
    monkeypatch.syspath_prepend(os.path.join(os.path.dirname(os.path.dirname(__file__)), "eval"))
    import login_whisper
    import whisper_ab

    async def fake(*a, **k):
        return "yo u on"
    monkeypatch.setattr(login_whisper, "call_ollama", fake)
    out = tmp_path / "o.jsonl"
    whisper_ab.main(["run", "--model", "fake:1", "--only", "opener", "--out", str(out)])
    rows = [json.loads(ln) for ln in out.read_text().splitlines()]
    assert len(rows) == 10 and all(r["message"] for r in rows)


def test_callback_without_place_cites_most_recent_shown_moment(lw, monkeypatch):
    _persona(monkeypatch, "Trean")
    ids = _wc_moments()                       # run 3 is the newest
    _fake_llm(monkeypatch, lw, "we gotta do that again")
    out = _open(lw, _cb(lw))
    assert out["fallback"] is False and out["moment_ids"] == [ids[-1]]
    _fake_llm(monkeypatch, lw, "hey u on")
    assert _open(lw, _cb(lw, kind="checkin"))["moment_ids"] == []


def test_callback_prompt_says_details_come_from_moments(lw, monkeypatch):
    _persona(monkeypatch, "Trean")
    _wc_moments()
    calls = _fake_llm(monkeypatch, lw, "round 2?")
    _open(lw, _cb(lw))
    assert "must come from the list above" in calls[0]["system"]


def test_long_absence_checkin_examples_only_after_long_absence(lw, monkeypatch):
    _persona(monkeypatch, "Trean")
    long_only = set(lw.OPENER_LONG_ABSENCE_EXAMPLES)

    def shown(absence):
        seen = set()
        for s in range(40):
            calls = _fake_llm(monkeypatch, lw, "hey u on")
            _open(lw, _cb(lw, kind="checkin", absence=absence), seed=s)
            seen |= {x for x in long_only if f"  {x}\n" in calls[0]["system"] + "\n"}
        return seen
    assert shown(None) == set()
    assert shown(3) == set()
    assert shown(10) == long_only
