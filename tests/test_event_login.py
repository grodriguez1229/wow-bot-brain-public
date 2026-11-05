"""R9 Task 10: login whispers via /event."""
import random
import time

import pytest
from fastapi.testclient import TestClient

import db
import events
import friendship
import history
import login_whisper
import main
import personality
import presence


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    presence.reset_state()
    events.reset_state()
    monkeypatch.setattr(login_whisper, "FRIENDS_ENABLED", True)
    monkeypatch.setattr(login_whisper, "LOGIN_WHISPER_RATE", 1.0)
    monkeypatch.setattr(login_whisper, "SECOND_WHISPER_RATE", 0.0)
    monkeypatch.setattr(login_whisper, "KIND_WEIGHTS", {"callback": 0, "invite": 0, "checkin": 1})
    seen = {"prompts": []}

    async def fake_ollama(system, hist, user, **kw):
        seen["prompts"].append(system)
        return "WHISPER: yo wc again?"

    monkeypatch.setattr(login_whisper, "call_ollama", fake_ollama)

    async def fake_main(system, hist, user, **kw):
        seen["prompts"].append(system)
        return "SAY: sure"

    monkeypatch.setattr(main, "call_ollama", fake_main)
    c = TestClient(main.app)
    c.seen = seen
    yield c
    presence.reset_state()


def _persona(monkeypatch, name, faction="Alliance"):
    monkeypatch.setitem(personality._personality_cache, name, {
        "bot_name": name, "level": 12, "faction": faction, "race": "Night Elf",
        "class_name": "Hunter", "gender": "male", "who": "a college kid who games too much",
        "typing_style": "lowercase, fast", "identity_id": "none", "current_goal": "level up",
        "irl": {"who_core": "a college kid who games too much"}})
    monkeypatch.setitem(personality._level_checked, name, time.monotonic())


def _friend(monkeypatch, bot="Trean", player="Abril", runs=3):
    now = time.time()
    _persona(monkeypatch, bot)
    friendship.add_play(bot, player, 28, now=now - 60)
    for i in range(runs):
        sid = history.open_session(player, bot, "run", instance="Wailing Caverns",
                                   now=now - 7200 + i * 600)
        history.close_session(sid, ended_at=now - 7200 + i * 600 + 400, outcome="cleared")
    presence.note_tick(bot, zone="Darkshore", subzone=None, activity="questing", now=now)


LOGIN = {"type": "login", "player": "Abril", "level": 10, "faction": "Alliance",
         "zone": "Darkshore"}


def test_login_returns_friend_whisper(client, monkeypatch):
    _friend(monkeypatch)
    r = client.post("/event", json=LOGIN)
    assert r.status_code == 200
    ws = r.json()["whispers"]
    assert len(ws) == 1
    w = ws[0]
    assert w["whisper_to"] == "Abril" and w["bot_name"] == "Trean" and w["channel"] == "WHISPER"
    assert 20 <= w["delay_s"] <= 120
    with db.get_db() as conn:
        assert conn.execute("SELECT 1 FROM messages WHERE bot_name='Trean' AND player_name='Abril'"
                            " AND role='assistant'").fetchone()
    assert history.last_event("Abril", "Trean", "login_whisper")


def test_login_stranger_empty(client, monkeypatch):
    _persona(monkeypatch, "Trean")
    friendship.add_chat("Trean", "Abril", 5, now=time.time() - 60)
    presence.note_tick("Trean", zone="Darkshore", subzone=None, activity="questing")
    assert client.post("/event", json=LOGIN).json() == {"whispers": []}


def test_friends_disabled_still_records_history(client, monkeypatch):
    _friend(monkeypatch)
    monkeypatch.setattr(login_whisper, "FRIENDS_ENABLED", False)
    assert client.post("/event", json=LOGIN).json() == {"whispers": []}
    assert history.player_seen("Abril")["last_login"] is not None


def test_reply_after_opener_sees_it(client, monkeypatch):
    _friend(monkeypatch)
    msg = client.post("/event", json=LOGIN).json()["whispers"][0]["message"]
    client.seen["prompts"].clear()
    r = client.post("/chat", json={"bot_name": "Trean", "player_name": "Abril",
                                   "message": "hey", "channel": "WHISPER"})
    assert r.status_code == 200
    assert any(msg in p for p in client.seen["prompts"])


def test_relog_before_delivery_gets_no_second_plan(client, monkeypatch):
    _friend(monkeypatch)
    assert len(client.post("/event", json=LOGIN).json()["whispers"]) == 1
    client.post("/event", json={"type": "logout", "player": "Abril"})
    assert client.post("/event", json=LOGIN).json() == {"whispers": []}


def test_long_absence_survives_login_ingest(client, monkeypatch):
    _friend(monkeypatch)
    now = time.time()
    history.note_player_seen("Abril", level=10, faction="Alliance", login=True,
                             now=now - 11 * 86400)
    history.note_player_seen("Abril", logout=True, now=now - 10 * 86400)
    captured = {}
    real = login_whisper.plan_login

    def spy(*a, **kw):
        plans = real(*a, **kw)
        captured["plans"] = plans
        return plans

    monkeypatch.setattr(login_whisper, "plan_login", spy)
    client.post("/event", json=LOGIN)
    assert captured["plans"] and captured["plans"][0].long_absence_days >= 10


def test_login_error_returns_empty(client, monkeypatch):
    _friend(monkeypatch)

    def boom(*a, **kw):
        raise RuntimeError("x")

    monkeypatch.setattr(login_whisper, "plan_login", boom)
    r = client.post("/event", json=LOGIN)
    assert r.status_code == 200 and r.json() == {"whispers": []}


def test_opener_error_uses_fallback_whisper(client, monkeypatch):
    _friend(monkeypatch)

    async def boom(*a, **kw):
        raise RuntimeError("x")

    monkeypatch.setattr(login_whisper, "generate_opener", boom)
    r = client.post("/event", json=LOGIN)
    assert r.status_code == 200 and len(r.json()["whispers"]) == 1


def test_cited_moments_marked(client, monkeypatch):
    _friend(monkeypatch)
    mid = history.add_moment("Abril", "Trean", "ran Wailing Caverns", source="event",
                             source_id=1, places=["Wailing Caverns"])
    monkeypatch.setattr(login_whisper, "KIND_WEIGHTS", {"callback": 1, "invite": 0, "checkin": 0})

    async def op(*a, **kw):
        return {"message": "wc again?", "actions": [], "moment_ids": [mid], "fallback": False}

    monkeypatch.setattr(login_whisper, "generate_opener", op)
    assert len(client.post("/event", json=LOGIN).json()["whispers"]) == 1
    assert history.moments_for("Abril", "Trean", limit=1)[0]["cited_at"] is not None


def test_slow_llm_exceeding_budget_returns_fallback(client, monkeypatch):
    import asyncio
    _friend(monkeypatch)
    monkeypatch.setattr(main, "LOGIN_GEN_BUDGET_S", 0.2)

    async def slow(system, hist, user, **kw):
        await asyncio.sleep(5)
        return "WHISPER: too late"

    monkeypatch.setattr(login_whisper, "call_ollama", slow)
    t0 = time.monotonic()
    r = client.post("/event", json=LOGIN)
    assert time.monotonic() - t0 < 2
    ws = r.json()["whispers"]
    assert len(ws) == 1 and ws[0]["message"]
    assert ws[0]["message"] != "too late"


def test_raising_llm_returns_fallback_not_dropped(client, monkeypatch):
    _friend(monkeypatch)

    async def boom(system, hist, user, **kw):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(login_whisper, "call_ollama", boom)
    ws = client.post("/event", json=LOGIN).json()["whispers"]
    assert len(ws) == 1 and ws[0]["message"]
