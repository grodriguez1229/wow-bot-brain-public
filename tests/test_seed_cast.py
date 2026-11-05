import pytest

from sim.memory_fixture import seed_cast

CAST = "eval/evolution/fixtures/cast.json"


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_seed_cast_pins_personalities(fresh_db):
    seed_cast(CAST, db_path=str(fresh_db.DB_PATH))
    # Geysse resolves to the pinned identity, not a re-roll / L1 fallback
    who = fresh_db.get_who("Geysse")
    assert who and "L1" not in who
    rows = fresh_db.get_memory_sheet("Geysse", "identity")  # no identity yet, fresh
    assert rows == []


def test_seed_cast_idempotent(fresh_db):
    seed_cast(CAST, db_path=str(fresh_db.DB_PATH))
    first = fresh_db.get_who("Lynea")
    seed_cast(CAST, db_path=str(fresh_db.DB_PATH))  # re-seed overwrites, no duplicate-key error
    assert fresh_db.get_who("Lynea") == first


def test_seed_cast_seeds_all_partner_names(fresh_db):
    # day_plan partners are Lynea/Geysse; both must be seeded so they don't fall back to L1
    seed_cast(CAST, db_path=str(fresh_db.DB_PATH))
    assert fresh_db.get_who("Lynea")
    assert fresh_db.get_who("Geysse")
