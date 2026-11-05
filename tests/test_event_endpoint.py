"""/event endpoint and the /tick presence hook (R9 Task 6)."""
import time

from fastapi.testclient import TestClient

import db
import events
import history
import main
import presence
from models import BotResponse


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    presence.reset_state()
    events.reset_state()
    return TestClient(main.app)


def test_event_group_roundtrip(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/event", json={"type": "group", "player": "Abril", "level": 10,
                               "zone": "Elwynn Forest", "group": ["Astianon"]})
    assert r.status_code == 200 and r.json() == {"whispers": []}
    r = c.post("/event", json={"type": "logout", "player": "Abril", "group": ["Astianon"]})
    assert r.status_code == 200 and r.json() == {"whispers": []}
    with db.get_db() as conn:
        rows = conn.execute("SELECT * FROM play_sessions").fetchall()
    assert rows and all(row["ended_at"] is not None for row in rows)


def test_unknown_and_ping_events_are_noops(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/event", json={"type": "ping", "player": "Zed"})
    assert r.status_code == 200 and r.json() == {"whispers": []}
    assert history.player_seen("Zed") is None
    r = c.post("/event", json={"type": "teleport", "player": "Zed"})
    assert r.status_code == 200 and r.json() == {"whispers": []}
    assert history.player_seen("Zed") is None
    r = c.post("/event", json={"type": "group", "player": "Zed"})
    assert r.status_code == 200 and r.json() == {"whispers": []}


def test_ingest_error_still_200(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)

    def boom(ev):
        raise RuntimeError("db gone")
    monkeypatch.setattr(main.events, "ingest", boom)
    r = c.post("/event", json={"type": "group", "player": "Abril"})
    assert r.status_code == 200 and r.json() == {"whispers": []}


def test_tick_notes_presence_even_when_silent(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(main.random, "random", lambda: 0.0)
    r = c.post("/tick", json={"bot_name": "Trean", "location": "Elwynn Forest",
                              "activity": "questing", "nearby_players": ["Abril"]})
    assert r.status_code == 200
    assert presence.is_online("Trean")
    assert presence.state("Trean")["zone"] == "Elwynn Forest"


def test_bot_response_whisper_to_optional():
    assert BotResponse(message="x", channel="SAY").whisper_to is None
