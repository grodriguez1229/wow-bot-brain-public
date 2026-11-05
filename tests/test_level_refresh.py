import pytest


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    import db
    import personality
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    monkeypatch.setattr(personality, "lookup_guild_invite_right", lambda n: False)
    monkeypatch.setattr(personality, "lookup_bot_guild", lambda n: "")
    game = {"level": 20}
    monkeypatch.setattr(personality, "lookup_bot_from_game_db", lambda n: {
        "race": "Orc", "class_name": "Warrior", "level": game["level"], "gender": "male",
        "faction": "Horde"})
    clock = {"t": 1000.0}
    monkeypatch.setattr(personality.time, "monotonic", lambda: clock["t"])
    personality._personality_cache.clear()
    personality._level_checked.clear()
    yield db, personality, game, clock
    personality._personality_cache.clear()
    personality._level_checked.clear()


def _stored(db, name):
    conn = db.get_db()
    row = conn.execute("SELECT level, current_goal FROM bot_personalities WHERE bot_name = ?",
                       (name,)).fetchone()
    conn.close()
    return dict(row)


def test_level_is_refreshed_from_game_db_after_ttl(fresh):
    db, personality, game, clock = fresh
    assert personality.get_or_create_personality("Trean")["level"] == 20
    game["level"] = 34
    assert personality.get_or_create_personality("Trean")["level"] == 20   # within TTL
    clock["t"] += personality.LEVEL_TTL_S + 1
    p = personality.get_or_create_personality("Trean")
    assert p["level"] == 34
    assert _stored(db, "Trean")["level"] == 34


def test_goal_is_repicked_when_level_changes(fresh, monkeypatch):
    db, personality, game, clock = fresh
    monkeypatch.setattr(personality, "pick_goal_for_level", lambda lvl, cls: f"goal@{lvl}")
    personality.get_or_create_personality("Trean")
    game["level"] = 45
    clock["t"] += personality.LEVEL_TTL_S + 1
    p = personality.get_or_create_personality("Trean")
    assert p["current_goal"] == "goal@45"
    assert _stored(db, "Trean")["current_goal"] == "goal@45"


def test_lookup_failure_keeps_stored_level(fresh, monkeypatch):
    db, personality, game, clock = fresh
    personality.get_or_create_personality("Trean")
    monkeypatch.setattr(personality, "lookup_bot_from_game_db", lambda n: None)
    clock["t"] += personality.LEVEL_TTL_S + 1
    assert personality.get_or_create_personality("Trean")["level"] == 20


def test_stale_row_loaded_from_sqlite_is_refreshed(fresh):
    db, personality, game, clock = fresh
    personality.get_or_create_personality("Trean")
    personality._personality_cache.clear()          # e.g. after a restart
    personality._level_checked.clear()
    game["level"] = 52
    assert personality.get_or_create_personality("Trean")["level"] == 52
