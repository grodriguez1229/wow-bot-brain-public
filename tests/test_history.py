import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_tables_created_and_init_idempotent(fresh_db):
    fresh_db.init_db()
    conn = fresh_db.get_db()
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"play_sessions", "shared_events", "moments", "player_seen"} <= names


def test_open_close_session_roundtrip(fresh_db):
    import history
    sid = history.open_session("Abril", "Astianon", "run", instance="Deadmines", now=1000)
    assert len(history.open_sessions("Abril", "run")) == 1
    row = history.close_session(sid, ended_at=1900, outcome="cleared")
    assert row["ended_at"] == 1900 and row["outcome"] == "cleared"
    assert history.open_sessions("Abril") == []
    assert history.runs_together("Abril", "Astianon") == 1


def test_bounce_runs_not_counted(fresh_db):
    import history
    sid = history.open_session("Abril", "Astianon", "run", now=1000)
    history.close_session(sid, ended_at=1100, outcome="bounce")
    assert history.runs_together("Abril", "Astianon") == 0


def test_bump_session(fresh_db):
    import history
    sid = history.open_session("Abril", "Astianon", "run", now=1000)
    history.bump_session(sid, bosses=1)
    history.bump_session(sid, wipes=2, outcome="partial")
    row = history.close_session(sid, ended_at=1500)
    assert (row["bosses"], row["wipes"], row["outcome"]) == (1, 2, "partial")


def test_long_sessions_threshold(fresh_db):
    import history
    for i, dur in enumerate((2699, 2700)):
        sid = history.open_session("Abril", "Astianon", "group", now=1000 * (i + 1))
        history.close_session(sid, ended_at=1000 * (i + 1) + dur)
    assert history.long_sessions("Abril", "Astianon", 2700) == 1


def test_events_count_and_last(fresh_db):
    import history
    history.add_event("Abril", "Astianon", "wipe", detail="a", now=100)
    history.add_event("Abril", "Astianon", "wipe", detail="b", now=200)
    assert history.count_events("Abril", "Astianon", "wipe", since=150) == 1
    assert history.last_event("Abril", "Astianon", "wipe")["detail"] == "b"
    assert history.last_event("Abril", "Astianon", "level_up") is None


def test_moments_rotate_least_recently_cited(fresh_db):
    import history
    ids = [history.add_moment("Abril", "Astianon", f"m{i}", source="event", source_id=i,
                              places=["Deadmines"], now=100 + i) for i in range(3)]
    history.mark_cited([ids[0]], now=500)
    got = history.moments_for("Abril", "Astianon", limit=2)
    assert [m["id"] for m in got] == [ids[2], ids[1]]
    assert got[0]["places"] == ["Deadmines"]


def test_player_seen_partial_update(fresh_db):
    import history
    assert history.player_seen("Abril") is None
    history.note_player_seen("Abril", level=10, login=True, now=100)
    history.note_player_seen("Abril", zone="Darkshore", now=200)
    row = history.player_seen("Abril")
    assert row["level"] == 10 and row["zone"] == "Darkshore"
    assert row["last_login"] == 100 and row["last_seen"] == 200
