import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_delete_memory_removes_one_subject(fresh_db):
    fresh_db.upsert_memory("Bot", "identity", "outlook", "cynical", weight=3)
    fresh_db.upsert_memory("Bot", "identity", "pugs", "done with them", weight=2)
    fresh_db.delete_memory("Bot", "identity", "outlook")
    rows = fresh_db.get_memory_sheet("Bot", "identity")
    assert {r["subject"] for r in rows} == {"pugs"}


def test_prune_by_weight_keeps_strongest(fresh_db):
    fresh_db.upsert_memory("Bot", "identity", "a", "x", weight=5)
    fresh_db.upsert_memory("Bot", "identity", "b", "x", weight=1)
    fresh_db.upsert_memory("Bot", "identity", "c", "x", weight=3)
    fresh_db.prune_memory_by_weight("Bot", "identity", keep=2)
    rows = fresh_db.get_memory_sheet("Bot", "identity")
    assert {r["subject"] for r in rows} == {"a", "c"}  # weakest (b) pruned


def test_prune_by_weight_other_kinds_untouched(fresh_db):
    fresh_db.upsert_memory("Bot", "identity", "a", "x", weight=1)
    fresh_db.upsert_memory("Bot", "self", "mood", "tired", weight=1)
    fresh_db.prune_memory_by_weight("Bot", "identity", keep=0)
    assert fresh_db.get_memory_sheet("Bot", "identity") == []
    assert len(fresh_db.get_memory_sheet("Bot", "self")) == 1


def test_get_who_returns_persona_or_empty(fresh_db):
    assert fresh_db.get_who("Nobody") == ""
    conn = fresh_db.get_db()
    conn.execute(
        """INSERT INTO bot_personalities
           (bot_name, race, class_name, level, gender, faction, identity_id, who,
            typing_style, current_goal)
           VALUES ('Bot','Dwarf','Rogue',16,'male','Alliance','retail_worker',
                   'a tired retail worker who games to unwind','terse','hit 20')""")
    conn.commit(); conn.close()
    assert "retail worker" in fresh_db.get_who("Bot")
