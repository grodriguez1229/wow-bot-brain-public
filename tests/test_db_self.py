import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_prune_keeps_newest_n(fresh_db):
    import time
    for i in range(6):
        fresh_db.upsert_memory("Bot", "self", f"s{i}", f"note {i}")
        time.sleep(0.01)  # distinct updated_at ordering
    fresh_db.prune_memory("Bot", "self", keep=4)
    rows = fresh_db.get_memory_sheet("Bot", "self")
    assert len(rows) == 4
    subjects = {r["subject"] for r in rows}
    # newest 4 survive (s2..s5), oldest two pruned
    assert subjects == {"s2", "s3", "s4", "s5"}


def test_prune_other_kinds_untouched(fresh_db):
    fresh_db.upsert_memory("Bot", "self", "a", "x")
    fresh_db.upsert_memory("Bot", "relationship", "Gus", "cool guy")
    fresh_db.prune_memory("Bot", "self", keep=0)
    assert fresh_db.get_memory_sheet("Bot", "self") == []
    assert len(fresh_db.get_memory_sheet("Bot", "relationship")) == 1


def test_get_recent_messages_across_players(fresh_db):
    fresh_db.save_message("Bot", "Gus", "user", "hi")
    fresh_db.save_message("Bot", "Gus", "assistant", "hey")
    fresh_db.save_message("Bot", "Lyn", "user", "sup")
    fresh_db.save_message("Bot", "Lyn", "assistant", "not much")
    msgs = fresh_db.get_recent_messages("Bot", limit=3)
    assert len(msgs) == 3
    # chronological (oldest -> newest), includes both players
    assert msgs[-1]["content"] == "not much"
    assert {m["player_name"] for m in msgs} <= {"Gus", "Lyn"}
