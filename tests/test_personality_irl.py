import json
import random

import pytest


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    import db
    import personality
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    monkeypatch.setattr(personality, "lookup_guild_invite_right", lambda n: False)
    monkeypatch.setattr(personality, "lookup_bot_guild", lambda n: "")
    monkeypatch.setattr(personality, "lookup_bot_from_game_db", lambda n: {
        "race": "Orc", "class_name": "Warrior", "level": 20, "gender": "male", "faction": "Horde"})
    personality._personality_cache.clear()
    yield db, personality
    personality._personality_cache.clear()


def _insert_legacy(db, name, identity_id="retail_worker", irl_json=""):
    conn = db.get_db()
    conn.execute("""INSERT INTO bot_personalities
        (bot_name, race, class_name, level, gender, faction, identity_id, who, typing_style,
         current_goal, motivation, irl_json)
        VALUES (?, 'Orc','Warrior',20,'male','Horde',?, '23yo Best Buy employee', 'old style',
                'goal', 'farmer', ?)""", (name, identity_id, irl_json))
    conn.commit(); conn.close()


def _row(db, name):
    conn = db.get_db()
    r = conn.execute("SELECT * FROM bot_personalities WHERE bot_name=?", (name,)).fetchone()
    conn.close()
    return dict(r)


def test_irl_json_column_exists_and_init_idempotent(fresh):
    db, _ = fresh
    db.init_db()
    conn = db.get_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bot_personalities)")]
    conn.close()
    assert "irl_json" in cols


def test_legacy_row_migrates_in_place_keeping_archetype(fresh):
    db, personality = fresh
    _insert_legacy(db, "Trean")
    p = personality.get_or_create_personality("Trean")
    assert p["irl"]["archetype"] == "retail_worker"
    row = _row(db, "Trean")
    assert json.loads(row["irl_json"])["archetype"] == "retail_worker"
    assert row["who"] == p["irl"]["who"] != "23yo Best Buy employee"
    assert row["typing_style"] == p["irl"]["typing_style"]
    assert row["motivation"] == "farmer"            # untouched


def test_migration_idempotent(fresh):
    db, personality = fresh
    _insert_legacy(db, "Trean")
    first = personality.get_or_create_personality("Trean")["irl"]
    personality._personality_cache.clear()
    assert personality.get_or_create_personality("Trean")["irl"] == first


def test_unknown_identity_id_is_repaired(fresh):
    db, personality = fresh
    _insert_legacy(db, "Oddbot", identity_id="deleted_archetype")
    p = personality.get_or_create_personality("Oddbot")
    from irl_identity import IRL_IDENTITIES
    valid = {a["id"] for a in IRL_IDENTITIES}
    assert p["irl"]["archetype"] in valid
    assert _row(db, "Oddbot")["identity_id"] in valid


def test_pinned_cast_row_is_not_rewritten(fresh):
    db, personality = fresh
    _insert_legacy(db, "Geysse", irl_json='{"pinned": true}')
    p = personality.get_or_create_personality("Geysse")
    assert p["irl"] == {"pinned": True}
    assert _row(db, "Geysse")["who"] == "23yo Best Buy employee"


def test_new_bot_gets_composed_identity(fresh):
    db, personality = fresh
    p = personality.get_or_create_personality("Newbie")
    row = _row(db, "Newbie")
    assert row["identity_id"] == p["irl"]["archetype"] == p["identity_id"]
    assert row["who"] == p["who"] == p["irl"]["who"]
    assert json.loads(row["irl_json"]) == p["irl"]


def test_get_bot_names(fresh):
    db, _ = fresh
    _insert_legacy(db, "A1")
    _insert_legacy(db, "B2")
    assert sorted(db.get_bot_names()) == ["A1", "B2"]


def test_irl_identities_reexported():
    from personality import IRL_IDENTITIES
    from irl_identity import IRL_IDENTITIES as src
    assert IRL_IDENTITIES is src


def test_pick_mood_in_game_when_irl_denied():
    from personality import IN_GAME_MOODS, IRL_IDENTITIES, pick_mood
    ident = IRL_IDENTITIES[0]
    random.seed(1)
    assert all(pick_mood(ident, irl_ok=False) in IN_GAME_MOODS for _ in range(50))
    assert all(pick_mood(ident) in ident["mood_pool"] for _ in range(50))


def test_activity_menu_drops_irl_when_denied():
    from personality import pick_tick_activity
    random.seed(3)
    prompts = [pick_tick_activity(20, "Mage", "Elwynn Forest", True, irl_ok=False)["prompt"].lower()
               for _ in range(300)]
    assert not any("real life" in p or "real-life" in p for p in prompts)


def test_resting_variant_has_no_irl_when_denied():
    from personality import pick_tick_activity
    out = pick_tick_activity(20, "Mage", "Goldshire", True, activity="resting", irl_ok=False)
    assert out["channel"] == "GENERAL"
    assert "real-life" not in out["prompt"].lower() and "real life" not in out["prompt"].lower()
    allowed = pick_tick_activity(20, "Mage", "Goldshire", True, activity="resting")
    assert "real-life" in allowed["prompt"].lower()


def test_seed_cast_pins_irl(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    from sim.memory_fixture import seed_cast
    cast = tmp_path / "cast.json"
    cast.write_text(json.dumps({"bots": [{
        "bot_name": "Geysse", "race": "Dwarf", "class_name": "Rogue", "level": 16,
        "gender": "male", "faction": "Alliance", "identity_id": "class_clown",
        "who": "frozen who", "typing_style": "x", "current_goal": "y"}]}))
    seed_cast(str(cast))
    assert json.loads(_row(db, "Geysse")["irl_json"]) == {"pinned": True}
