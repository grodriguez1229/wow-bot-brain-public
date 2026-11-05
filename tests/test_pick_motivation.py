import random
from personality import pick_motivation
from capabilities import MOTIVATIONS


def test_always_returns_valid_motivation():
    random.seed(1)
    for _ in range(50):
        assert pick_motivation("Mage", 30, has_guild=False, can_guild_invite=False) in MOTIVATIONS


def test_non_guilded_never_recruiter():
    random.seed(2)
    for _ in range(200):
        m = pick_motivation("Warrior", 40, has_guild=False, can_guild_invite=False)
        assert m != "guild_recruiter"


def test_rank_holder_can_be_recruiter():
    random.seed(3)
    got = {pick_motivation("Warrior", 40, has_guild=True, can_guild_invite=True)
           for _ in range(200)}
    assert "guild_recruiter" in got


def test_lowbie_skews_explore_farm():
    random.seed(4)
    low = [pick_motivation("Mage", 8, has_guild=False, can_guild_invite=False) for _ in range(300)]
    frac = sum(m in ("world_explorer", "farmer") for m in low) / len(low)
    assert frac > 0.4


import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_new_personality_gets_motivation(fresh_db, monkeypatch):
    import personality
    personality._personality_cache.clear()
    monkeypatch.setattr(personality, "lookup_bot_from_game_db",
                        lambda n: {"race": "Dwarf", "class_name": "Warrior", "level": 20,
                                   "gender": "male", "faction": "Alliance"})
    monkeypatch.setattr(personality, "lookup_bot_guild", lambda n: "")
    monkeypatch.setattr(personality, "lookup_guild_invite_right", lambda n: False)
    p = personality.get_or_create_personality("Newbot")
    from capabilities import MOTIVATIONS
    assert p["motivation"] in MOTIVATIONS
    row = fresh_db.get_db().execute(
        "SELECT motivation FROM bot_personalities WHERE bot_name='Newbot'").fetchone()
    assert row["motivation"] in MOTIVATIONS


def test_existing_row_without_motivation_is_backfilled(fresh_db, monkeypatch):
    import personality
    personality._personality_cache.clear()
    conn = fresh_db.get_db()
    conn.execute("""INSERT INTO bot_personalities
        (bot_name, race, class_name, level, gender, faction, identity_id, who, typing_style, current_goal, motivation)
        VALUES ('Oldbot','Dwarf','Rogue',16,'male','Alliance','class_clown','x','y','z','')""")
    conn.commit(); conn.close()
    monkeypatch.setattr(personality, "lookup_guild_invite_right", lambda n: False)
    p = personality.get_or_create_personality("Oldbot")
    from capabilities import MOTIVATIONS
    assert p["motivation"] in MOTIVATIONS
    # backfill must PERSIST, not just populate the cache
    row = fresh_db.get_db().execute(
        "SELECT motivation FROM bot_personalities WHERE bot_name='Oldbot'").fetchone()
    assert row["motivation"] in MOTIVATIONS


def test_personality_caches_can_guild_invite(fresh_db, monkeypatch):
    import personality
    personality._personality_cache.clear()
    monkeypatch.setattr(personality, "lookup_bot_from_game_db",
                        lambda n: {"race": "Human", "class_name": "Paladin", "level": 30,
                                   "gender": "male", "faction": "Alliance"})
    monkeypatch.setattr(personality, "lookup_bot_guild", lambda n: "The Knights")
    calls = {"n": 0}
    def fake_right(n):
        calls["n"] += 1
        return True
    monkeypatch.setattr(personality, "lookup_guild_invite_right", fake_right)
    p = personality.get_or_create_personality("Officer1")
    assert p["can_guild_invite"] is True
    # second load hits the cache -> no extra rank lookup
    p2 = personality.get_or_create_personality("Officer1")
    assert p2["can_guild_invite"] is True
    assert calls["n"] == 1  # looked up once, then cached
