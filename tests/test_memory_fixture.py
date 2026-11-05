import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_load_into_explicit_db_path(tmp_path, monkeypatch):
    import db
    from sim.memory_fixture import load_memory_fixture
    target = str(tmp_path / "brain.db")
    monkeypatch.setattr(db, "DB_PATH", target)
    db.init_db()  # create schema in the target file
    load_memory_fixture("eval/optimizer/memory_fixture.json", db_path=target)
    # read back via db (still pointed at target)
    rel = db.get_relationship("Geysse", "Lynea")
    assert rel["familiarity"] == 12
    assert rel["notes"] == "duo partner, ran Deadmines last week"


def test_fixture_load_is_deterministic(fresh_db):
    from sim.memory_fixture import load_memory_fixture
    path = "eval/optimizer/memory_fixture.json"

    load_memory_fixture(path)
    rel1 = fresh_db.get_relationship("Geysse", "Lynea")
    sheet1 = fresh_db.get_memory_sheet("Geysse")

    load_memory_fixture(path)  # second load must reset to the same state
    rel2 = fresh_db.get_relationship("Geysse", "Lynea")
    sheet2 = fresh_db.get_memory_sheet("Geysse")

    assert rel1 == rel2
    assert rel1["notes"] == "duo partner, ran Deadmines last week"
    assert rel1["familiarity"] == 12
    assert [(r["kind"], r["subject"], r["content"]) for r in sheet1] == \
           [(r["kind"], r["subject"], r["content"]) for r in sheet2]
