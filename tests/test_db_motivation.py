import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_bot_personalities_has_motivation_column(fresh_db):
    conn = fresh_db.get_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bot_personalities)").fetchall()]
    conn.close()
    assert "motivation" in cols


def test_set_motivation_roundtrip(fresh_db):
    conn = fresh_db.get_db()
    conn.execute("""INSERT INTO bot_personalities
        (bot_name, race, class_name, level, gender, faction, identity_id, who, typing_style, current_goal)
        VALUES ('Geysse','Dwarf','Rogue',16,'male','Alliance','class_clown','x','y','z')""")
    conn.commit(); conn.close()
    fresh_db.set_motivation("Geysse", "gold_maker")
    conn = fresh_db.get_db()
    row = conn.execute("SELECT motivation FROM bot_personalities WHERE bot_name='Geysse'").fetchone()
    conn.close()
    assert row["motivation"] == "gold_maker"


def test_init_db_idempotent(fresh_db):
    fresh_db.init_db()
