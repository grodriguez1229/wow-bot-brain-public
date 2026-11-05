import importlib
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_bot_memory_table_exists(fresh_db):
    conn = fresh_db.get_db()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_memory'"
    ).fetchall()
    conn.close()
    assert rows


def test_set_and_read_relationship_notes(fresh_db):
    fresh_db.update_relationship("Geysse", "Lynea", familiarity_delta=3)
    fresh_db.set_relationship_notes("Geysse", "Lynea", "ran Deadmines together")
    rel = fresh_db.get_relationship("Geysse", "Lynea")
    assert rel["notes"] == "ran Deadmines together"


def test_upsert_memory_is_idempotent_per_key(fresh_db):
    fresh_db.upsert_memory("Geysse", "relationship", "Lynea", "first note")
    fresh_db.upsert_memory("Geysse", "relationship", "Lynea", "updated note", weight=2)
    sheet = fresh_db.get_memory_sheet("Geysse")
    rel_rows = [r for r in sheet if r["kind"] == "relationship" and r["subject"] == "Lynea"]
    assert len(rel_rows) == 1
    assert rel_rows[0]["content"] == "updated note"
    assert rel_rows[0]["weight"] == 2


def test_init_db_idempotent(fresh_db):
    fresh_db.init_db()  # second call must not raise


def test_familiarity_never_goes_negative_on_existing(fresh_db):
    fresh_db.update_relationship("Geysse", "Lynea", familiarity_delta=2)
    fresh_db.update_relationship("Geysse", "Lynea", familiarity_delta=-5)
    assert fresh_db.get_relationship("Geysse", "Lynea")["familiarity"] == 0


def test_familiarity_never_negative_on_new_pair(fresh_db):
    fresh_db.update_relationship("Geysse", "Bob", familiarity_delta=-3)
    assert fresh_db.get_relationship("Geysse", "Bob")["familiarity"] == 0
