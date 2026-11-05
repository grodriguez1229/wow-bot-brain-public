import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

import chat_log
import election
import irl_budget
import main
import personality
from models import ChatRequest


def _stub_chat_deps(monkeypatch, reply):
    election.reset_state()
    irl_budget.reset_state()
    chat_log.reset_state()
    seen = []

    async def fake_ollama(system, history, user, **kw):
        seen.append(system)
        return reply
    p = {"bot_name": "Trean", "race": "Orc", "class_name": "Warrior", "level": 20,
         "faction": "Horde", "identity_id": "retail_worker", "who": "w", "typing_style": "casual",
         "current_goal": "g", "guild_name": "Wolves", "motivation": "", "irl": {}}
    monkeypatch.setattr(main, "call_ollama", fake_ollama)
    monkeypatch.setattr(main, "get_or_create_personality", lambda n: dict(p, bot_name=n))
    monkeypatch.setattr(main, "get_memory_sheet", lambda b, k: [])
    monkeypatch.setattr(main, "known_bot_names", lambda: frozenset({"Trean"}))
    monkeypatch.setattr(main, "get_relationship", lambda b, pl: {"label": "stranger", "familiarity": 0, "notes": ""})
    monkeypatch.setattr(main, "describe_relationship", lambda rel: "stranger")
    monkeypatch.setattr(main, "get_memory", lambda b, pl: [])
    monkeypatch.setattr(main, "save_message", lambda *a: None)
    stub_r9_reads(monkeypatch)
    monkeypatch.setattr(main, "_maybe_reflect_self", lambda *a: None)
    monkeypatch.setattr(main.random, "random", lambda: 0.99)
    return seen


def stub_r9_reads(monkeypatch):
    """R9: run_chat reads/writes friendship + shared history; keep tests off the DB."""
    monkeypatch.setattr(main, "friendship", SimpleNamespace(
        apply_decay=lambda *a, **k: None, add_chat=lambda *a, **k: None))
    monkeypatch.setattr(main, "shared_history", SimpleNamespace(moments_for=lambda *a, **k: []))


def _capture_transform(monkeypatch):
    calls = []

    def fake(text, bot, **kw):
        calls.append(kw)
        return text + " <t>"
    monkeypatch.setattr(main, "VOICE_TRANSFORM", True)
    monkeypatch.setattr(main, "transform", fake)
    return calls


def test_heard_lane_gets_full_transform(monkeypatch):
    _stub_chat_deps(monkeypatch, "ya murlocs suck")
    monkeypatch.setattr(main, "pick_shape", lambda *a, **k: "fragment")
    calls = _capture_transform(monkeypatch)
    out = asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus",
                                                message="murlocs", channel="SAY"), lane="heard"))
    assert out["message"] == "ya murlocs suck <t>"
    assert calls[0]["light"] is False and "Gus" in calls[0]["protect"]
    assert calls[0]["max_len"] == min(main.shape_budget("fragment"), main.HEARD_MAX_CHARS)


def test_whisper_gets_light_transform(monkeypatch):
    _stub_chat_deps(monkeypatch, "hey whats up")
    monkeypatch.setattr(main, "pick_shape", lambda *a, **k: "fragment")
    calls = _capture_transform(monkeypatch)
    out = asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus",
                                                message="hi")))
    assert out["message"] == "hey whats up <t>"
    assert calls[0]["light"] is True
    assert calls[0]["max_len"] == min(main.shape_budget("fragment"), main.CHAT_MAX_CHARS)


def test_transform_off_leaves_line(monkeypatch):
    _stub_chat_deps(monkeypatch, "Hey There.")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    out = asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus", message="hi")))
    assert out["message"] == "Hey There."


def test_heard_records_incoming_and_replies_in_chat_log(monkeypatch):
    chat_log.reset_state()

    async def fake_run_chat(req, may_decline=False, *, lane="default"):
        return {"message": "ya", "channel": req.channel, "emote": None, "actions": []}
    monkeypatch.setattr(main, "run_chat", fake_run_chat)
    monkeypatch.setattr(main.election_mod, "elect",
                        lambda *a, **k: [{"bot_name": "Esterini", "tier": "named"}])
    monkeypatch.setitem(personality._personality_cache, "Esterini",
                        {"faction": "Alliance", "guild_name": "Lions"})
    r = TestClient(main.app).post("/heard", json={
        "speaker": "Gus", "channel": "GUILD", "message": "anyone on?", "location": "Elwynn Forest",
        "hearers": [{"bot_name": "Esterini", "same_guild": True}]})
    assert r.status_code == 200
    root, reply = list(chat_log._log)
    assert (root["speaker"], root["text"], root["faction"], root["guild"]) == ("Gus", "anyone on?", None, "Lions")
    assert reply["speaker"] == "Esterini" and reply["reply_to"] == root["id"]
    assert reply["faction"] == "Alliance"
    # a guildmate ticking later can join the thread
    cands = chat_log.reply_candidates("Other", faction="Alliance", zone="Elwynn Forest", guild="Lions")
    assert {c["id"] for c in cands} == {root["id"], reply["id"]}


def test_heard_uncached_hearer_does_not_touch_db(monkeypatch):
    chat_log.reset_state()

    async def fake_run_chat(req, may_decline=False, *, lane="default"):
        return None
    monkeypatch.setattr(main, "run_chat", fake_run_chat)
    monkeypatch.setattr(main.election_mod, "elect", lambda *a, **k: [])
    monkeypatch.setattr(main, "get_or_create_personality",
                        lambda n: (_ for _ in ()).throw(AssertionError("db")))
    r = TestClient(main.app).post("/heard", json={
        "speaker": "Gus", "channel": "GUILD", "message": "hi", "location": "Elwynn Forest",
        "hearers": [{"bot_name": "Nobody", "same_guild": True}]})
    assert r.status_code == 200 and chat_log._log[-1]["guild"] == ""
