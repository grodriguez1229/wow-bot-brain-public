import pytest

import db
import events
import history

T = 1_700_000_000


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    events.reset_state()
    return db


def _ev(type_, player="Abril", **kw):
    return {"type": type_, "player": player, "level": 12, "faction": "Alliance", **kw}


def _play(player, bot):
    conn = db.get_db()
    try:
        r = conn.execute("SELECT play_points FROM relationships WHERE bot_name=? AND player_name=?",
                         (bot, player)).fetchone()
        return r[0] if r else 0
    finally:
        conn.close()


def _sessions(player, kind):
    conn = db.get_db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM play_sessions WHERE player_name=? AND kind=? ORDER BY id", (player, kind))]
    finally:
        conn.close()


def test_group_session_points(fresh_db):
    events.ingest(_ev("group", group=["Astianon"]), now=T)
    events.ingest(_ev("group", group=[]), now=T + 3600)
    rows = _sessions("Abril", "group")
    assert len(rows) == 1 and rows[0]["ended_at"] - rows[0]["started_at"] == 3600
    assert _play("Abril", "Astianon") == 6


def _wc_run(player="Abril"):
    g = ["Astianon"]
    events.ingest(_ev("group", player, group=g), now=T)
    events.ingest(_ev("map", player, group=g, instance="Wailing Caverns"), now=T)
    events.ingest(_ev("boss_kill", player, group=g, instance="Wailing Caverns",
                      boss="Mutanus the Devourer"), now=T + 1500)
    events.ingest(_ev("map", player, group=g, instance=""), now=T + 1800)


def test_wc_run_cleared_moment(fresh_db):
    _wc_run()
    run = _sessions("Abril", "run")[0]
    assert run["outcome"] == "cleared" and run["bosses"] == 1
    assert _play("Abril", "Astianon") == 8  # run 5 + clear 3; group session still open
    ms = history.moments_for("Abril", "Astianon", 10)
    assert len(ms) == 1
    assert "Mutanus the Devourer" in ms[0]["text"] and "Wailing Caverns" in ms[0]["text"]
    assert ms[0]["places"] == ["Wailing Caverns"]


def test_short_zone_in_is_bounce(fresh_db):
    g = ["Astianon"]
    events.ingest(_ev("map", group=g, instance="Wailing Caverns"), now=T)
    events.ingest(_ev("map", group=g, instance=""), now=T + 120)
    assert _sessions("Abril", "run")[0]["outcome"] == "bounce"
    assert history.runs_together("Abril", "Astianon") == 0
    assert _play("Abril", "Astianon") == 0


def test_deadmines_map_name_resolves(fresh_db):
    g = ["Astianon"]
    events.ingest(_ev("map", group=g, instance="The Deadmines"), now=T)
    events.ingest(_ev("boss_kill", group=g, instance="The Deadmines", boss="Edwin VanCleef"), now=T + 900)
    assert _sessions("Abril", "run")[0]["outcome"] == "cleared"


def test_wipe_needs_whole_group_dead(fresh_db):
    g = ["Astianon", "Lelindea"]
    events.ingest(_ev("map", group=g, instance="Wailing Caverns"), now=T)

    def died(who, dt):
        events.ingest(_ev("died", group=g, instance="Wailing Caverns", who=who,
                          boss="Lord Cobrahn"), now=T + dt)

    def wipes():
        return history.count_events("Abril", "Astianon", "wipe", since=0)

    died("Abril", 100)
    died("Astianon", 110)
    assert wipes() == 0
    died("Lelindea", 130)
    assert wipes() == 1
    assert any("wiped on Lord Cobrahn" in m["text"] for m in history.moments_for("Abril", "Astianon", 10))
    # spread over 90 s -> no wipe
    died("Abril", 300)
    died("Astianon", 345)
    died("Lelindea", 390)
    assert wipes() == 1


def test_login_closes_stale_sessions_at_last_seen(fresh_db):
    events.ingest(_ev("group", group=["Astianon"]), now=T)
    events.ingest(_ev("level_up", group=["Astianon"], level=13), now=T + 600)
    events.ingest(_ev("login", group=[]), now=T + 3 * 86400)
    rows = _sessions("Abril", "group")
    assert rows[0]["ended_at"] == T + 600
    assert history.long_sessions("Abril", "Astianon", 2700) == 0


def test_duplicate_logout_is_safe(fresh_db):
    events.ingest(_ev("group", group=["Astianon"]), now=T)
    events.ingest(_ev("logout", group=["Astianon"]), now=T + 600)
    events.ingest(_ev("logout", group=["Astianon"]), now=T + 900)
    rows = _sessions("Abril", "group")
    assert len(rows) == 1 and rows[0]["ended_at"] == T + 600


def test_level_up_grouped_only(fresh_db):
    events.ingest(_ev("level_up", group=[], level=13), now=T)
    assert history.moments_for("Abril", "Astianon") == []
    events.ingest(_ev("level_up", group=["Astianon"], level=14), now=T + 5)
    assert "dinged 14" in history.moments_for("Abril", "Astianon")[0]["text"]


def test_events_for_any_real_player(fresh_db):
    _wc_run("Bob")
    assert _sessions("Bob", "run")[0]["outcome"] == "cleared"
    assert history.moments_for("Bob", "Astianon")
    assert history.moments_for("Abril", "Astianon") == []


def test_unknown_and_ping_write_nothing(fresh_db):
    events.ingest({"type": "teleport", "player": "Abril"}, now=T)
    events.ingest(_ev("ping"), now=T)
    assert history.player_seen("Abril") is None


def test_login_updates_seen_and_opens_sessions(fresh_db):
    events.ingest(_ev("login", group=["Astianon"]), now=T)
    assert history.player_seen("Abril")["last_login"] == T
    assert len(history.open_sessions("Abril", "group")) == 1


def test_reentry_after_wipe_is_one_run(fresh_db):
    g = ["Astianon"]
    wc = "Wailing Caverns"
    events.ingest(_ev("group", group=g), now=T)
    events.ingest(_ev("map", group=g, instance=wc), now=T)
    events.ingest(_ev("died", group=g, instance=wc, who="Abril"), now=T + 400)
    events.ingest(_ev("died", group=g, instance=wc, who="Astianon"), now=T + 410)
    events.ingest(_ev("map", group=g, instance=""), now=T + 420)       # released
    events.ingest(_ev("map", group=g, instance=wc), now=T + 500)       # corpse run
    events.ingest(_ev("map", group=g, instance=wc), now=T + 505)       # duplicate re-send
    events.ingest(_ev("boss_kill", group=g, instance=wc, boss="Mutanus the Devourer"), now=T + 1500)
    events.ingest(_ev("map", group=g, instance=""), now=T + 1800)
    runs = _sessions("Abril", "run")
    assert len(runs) == 1 and runs[0]["outcome"] == "cleared" and runs[0]["bosses"] == 1
    assert runs[0]["wipes"] == 1
    assert history.runs_together("Abril", "Astianon") == 1
    run_moments = [m for m in history.moments_for("Abril", "Astianon", 20)
                   if m["text"].startswith(("ran ", "killed "))]
    assert len(run_moments) == 1
    assert _play("Abril", "Astianon") == 8  # run 5 + clear 3, once


def test_reentry_too_late_is_new_run(fresh_db):
    g = ["Astianon"]
    wc = "Wailing Caverns"
    events.ingest(_ev("map", group=g, instance=wc), now=T)
    events.ingest(_ev("boss_kill", group=g, instance=wc, boss="Lord Cobrahn"), now=T + 600)
    events.ingest(_ev("map", group=g, instance=""), now=T + 700)
    events.ingest(_ev("map", group=g, instance=wc), now=T + 700 + 601)
    assert len(_sessions("Abril", "run")) == 2


def test_concurrent_group_events_one_session(fresh_db):
    import threading
    barrier = threading.Barrier(8)

    def go():
        barrier.wait()
        events.ingest(_ev("group", group=["Astianon"]), now=T)

    ts = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(history.open_sessions("Abril", "group")) == 1


def test_login_inside_instance_opens_run(fresh_db):
    events.ingest(_ev("login", group=["Astianon"], instance="The Deadmines"), now=T)
    runs = history.open_sessions("Abril", "run")
    assert len(runs) == 1 and runs[0]["instance"] == "Deadmines"


def test_level_up_without_level_is_skipped(fresh_db):
    events.ingest({"type": "level_up", "player": "Abril", "group": ["Astianon"]}, now=T)
    assert history.moments_for("Abril", "Astianon") == []


def test_second_final_boss_kill_no_second_moment(fresh_db):
    g = ["Astianon"]
    events.ingest(_ev("map", group=g, instance="Wailing Caverns"), now=T)
    for dt in (900, 950):
        events.ingest(_ev("boss_kill", group=g, instance="Wailing Caverns",
                          boss="Mutanus the Devourer"), now=T + dt)
    assert len([m for m in history.moments_for("Abril", "Astianon", 10)
                if m["text"].startswith("killed ")]) == 1


def test_relog_inside_instance_is_one_run(fresh_db):
    g = ["Astianon"]
    wc = "Wailing Caverns"
    events.ingest(_ev("group", group=g), now=T)
    events.ingest(_ev("map", group=g, instance=wc), now=T)
    events.ingest(_ev("boss_kill", group=g, instance=wc, boss="Lord Cobrahn"), now=T + 900)
    events.ingest(_ev("login", group=g, instance=wc), now=T + 1000)
    events.ingest(_ev("map", group=g, instance=wc), now=T + 1001)
    events.ingest(_ev("map", group=g, instance=""), now=T + 2000)
    runs = _sessions("Abril", "run")
    assert len(runs) == 1 and runs[0]["bosses"] == 1
    assert _play("Abril", "Astianon") >= 5
    assert history.runs_together("Abril", "Astianon") == 1


def test_bot_leaves_and_rejoins_inside_instance_is_one_run(fresh_db):
    g = ["Astianon"]
    wc = "Wailing Caverns"
    events.ingest(_ev("map", group=g, instance=wc), now=T)
    events.ingest(_ev("group", group=g, instance=wc), now=T + 1)
    events.ingest(_ev("group", group=[], instance=wc), now=T + 900)
    events.ingest(_ev("group", group=g, instance=wc), now=T + 950)
    events.ingest(_ev("map", group=g, instance=""), now=T + 2000)
    assert len(_sessions("Abril", "run")) == 1
    assert history.runs_together("Abril", "Astianon") == 1
    assert _play("Abril", "Astianon") >= 5
