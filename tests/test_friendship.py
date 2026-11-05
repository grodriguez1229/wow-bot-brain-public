import pytest

T0 = 1_800_000_000.0
DAY = 86400


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def _set(db, **cols):
    conn = db.get_db()
    sets = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(f"UPDATE relationships SET {sets} WHERE bot_name='B' AND player_name='P'",
                 list(cols.values()))
    conn.commit()
    conn.close()


def test_chat_alone_caps_at_acquaintance(fresh_db):
    import friendship
    for i in range(40):
        row = friendship.add_chat("B", "P", now=T0 + i)
    assert row["familiarity"] == 12
    assert row["label"] == "acquaintance"
    assert fresh_db.get_relationship("B", "P")["familiarity"] == 12


def test_migration_keeps_points_caps_effective(fresh_db):
    conn = fresh_db.get_db()
    conn.execute("INSERT INTO relationships (bot_name, player_name, familiarity, label)"
                 " VALUES ('Astianon', 'Abril', 15, 'friend')")
    conn.commit()
    conn.close()
    fresh_db.init_db()

    def snap():
        c = fresh_db.get_db()
        r = dict(c.execute("SELECT * FROM relationships WHERE bot_name='Astianon'").fetchone())
        c.close()
        return r
    r = snap()
    assert r["chat_points"] == 15
    assert r["play_points"] == 0
    assert r["familiarity"] == 12
    assert r["label"] == "acquaintance"
    fresh_db.init_db()
    assert snap() == r


def test_play_reaches_friend(fresh_db):
    import friendship
    for i in range(12):
        friendship.add_chat("B", "P", now=T0)
    row = friendship.add_play("B", "P", 13, now=T0)
    assert row["familiarity"] == 25
    assert row["label"] == "friend"


def test_decay_one_point_per_day_play_first(fresh_db):
    import friendship
    for _ in range(12):
        friendship.add_chat("B", "P", now=T0)
    friendship.add_play("B", "P", 13, now=T0)
    row = friendship.apply_decay("B", "P", now=T0 + 3 * DAY + 5)
    assert row["play_points"] == 10
    assert row["chat_points"] == 12
    assert row["familiarity"] == 22
    again = friendship.apply_decay("B", "P", now=T0 + 3 * DAY + 5)
    assert again == row


def test_no_decay_within_a_day_of_play(fresh_db):
    import friendship
    for _ in range(12):
        friendship.add_chat("B", "P", now=T0)
    friendship.add_play("B", "P", 13, now=T0)
    row = friendship.apply_decay("B", "P", now=T0 + DAY - 1)
    assert row["play_points"] == 13 and row["familiarity"] == 25


def test_decay_spills_into_chat_and_floors_at_zero(fresh_db):
    import friendship
    friendship.add_chat("B", "P", 2, now=T0)
    friendship.add_play("B", "P", 1, now=T0)
    row = friendship.apply_decay("B", "P", now=T0 + 30 * DAY)
    assert (row["chat_points"], row["play_points"], row["familiarity"]) == (0, 0, 0)
    assert row["label"] == "stranger"


def test_chat_only_pair_decays(fresh_db):
    import friendship
    friendship.add_chat("B", "P", 8, now=T0)
    row = friendship.apply_decay("B", "P", now=T0 + 5 * DAY)
    assert row["chat_points"] == 3


def test_whisper_eligibility_needs_shared_play(fresh_db):
    import friendship
    import history

    def run(player, bot, n):
        for i in range(n):
            sid = history.open_session(player, bot, "run", now=T0 + i)
            history.close_session(sid, ended_at=T0 + i + 600)

    friendship.add_chat("B", "P", 12, now=T0)
    friendship.add_play("B", "P", 18, now=T0)
    run("P", "B", 1)
    assert friendship.is_whisper_eligible("B", "P", now=T0) is False
    run("P", "B", 1)
    assert friendship.is_whisper_eligible("B", "P", now=T0) is True

    friendship.add_chat("C", "P", 12, now=T0)
    friendship.add_play("C", "P", 18, now=T0)
    assert friendship.is_whisper_eligible("C", "P", now=T0) is False
    sid = history.open_session("P", "C", "group", now=T0)
    history.close_session(sid, ended_at=T0 + 2700)
    assert friendship.is_whisper_eligible("C", "P", now=T0) is True

    friendship.add_chat("D", "P", 12, now=T0)
    friendship.add_play("D", "P", 12, now=T0)
    run("P", "D", 3)
    assert friendship.is_whisper_eligible("D", "P", now=T0) is False


def test_add_play_never_negative(tmp_path, monkeypatch):
    import db
    import friendship
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    row = friendship.add_play("Trean", "Abril", 3, now=1000.0)
    row = friendship.add_play("Trean", "Abril", -10, now=1001.0)
    assert row["play_points"] == 0
