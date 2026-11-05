import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    import events, presence
    events.reset_state()
    presence.reset_state()
    return db


def test_online_window(fresh_db):
    import presence
    t = 1_000_000
    presence.note_tick("Astianon", zone="Teldrassil", subzone="Dolanaar", activity="questing", now=t)
    assert presence.is_online("Astianon", now=t + 300)
    assert not presence.is_online("Astianon", now=t + 301)
    assert presence.state("Astianon")["activity"] == "questing"
    assert presence.online_bots(now=t + 10) == ["Astianon"]
    assert presence.online_bots(now=t + 400) == []
    assert presence.state("Nobody") is None


def test_copresence_gap_and_daily_cap(fresh_db):
    import presence, history, db
    t = 1_000_000
    for i in range(73):  # 12 h at 10 min
        presence.note_tick("Astianon", zone="Teldrassil", subzone=None, activity=None,
                           nearby_players=["Abril"], now=t + i * 600)
    assert history.count_events("Abril", "Astianon", "same_zone", since=0) == 3
    conn = db.get_db()
    pts = conn.execute("SELECT play_points FROM relationships WHERE bot_name='Astianon'"
                       " AND player_name='Abril'").fetchone()[0]
    conn.close()
    assert pts == 3
