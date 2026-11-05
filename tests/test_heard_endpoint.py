"""/heard endpoint: election wiring with a stubbed LLM pipeline."""
from fastapi.testclient import TestClient

import election
import main


def setup_function(_):
    election.reset_state()


def _post(client, message, hearers, channel="SAY"):
    return client.post("/heard", json={
        "speaker": "Abril", "channel": channel, "message": message,
        "location": "Elwynn Forest",
        "hearers": [{"bot_name": h} for h in hearers],
    })


def test_named_bot_reply_comes_back_in_body(monkeypatch):
    async def fake_run_chat(req, may_decline=False, *, lane="default"):
        return {"message": f"hi {req.player_name}", "channel": req.channel,
                "emote": None, "actions": []}
    monkeypatch.setattr(main, "run_chat", fake_run_chat)
    monkeypatch.setattr(main, "_heard_familiarity", lambda s, b: 0)
    monkeypatch.setattr(main, "_heard_persona_text", lambda b: "")
    monkeypatch.setattr(main, "_heard_recent_convo", lambda s, b: False)

    client = TestClient(main.app)
    r = _post(client, "esterini you there?", ["Esterini", "Brogdurn"])
    assert r.status_code == 200
    body = r.json()["responses"]
    assert len(body) == 1
    assert body[0]["bot_name"] == "Esterini"
    assert body[0]["message"] == "hi Abril"


def test_pass_decline_yields_empty_responses(monkeypatch):
    async def fake_run_chat(req, may_decline=False, *, lane="default"):
        return None                      # candidate declined (run_chat returns None on PASS)
    monkeypatch.setattr(main, "run_chat", fake_run_chat)
    monkeypatch.setattr(main, "_heard_familiarity", lambda s, b: 5)
    monkeypatch.setattr(main, "_heard_persona_text", lambda b: "deadmines runner")
    monkeypatch.setattr(main, "_heard_recent_convo", lambda s, b: False)
    monkeypatch.setattr(main.election_mod, "elect",
                        lambda *a, **k: [{"bot_name": "Esterini", "tier": "candidate"}])

    client = TestClient(main.app)
    r = _post(client, "who wants deadmines", ["Esterini"], channel="GENERAL")
    assert r.status_code == 200
    assert r.json()["responses"] == []


def test_elected_replier_gets_cooldown_and_spoke_note(monkeypatch):
    async def fake_run_chat(req, may_decline=False, *, lane="default"):
        return {"message": "yo", "channel": req.channel, "emote": None, "actions": []}
    monkeypatch.setattr(main, "run_chat", fake_run_chat)
    monkeypatch.setattr(main, "_heard_familiarity", lambda s, b: 0)
    monkeypatch.setattr(main, "_heard_persona_text", lambda b: "")
    monkeypatch.setattr(main, "_heard_recent_convo", lambda s, b: False)

    client = TestClient(main.app)
    _post(client, "esterini hello", ["Esterini"])
    assert ("Esterini", "SAY") in election._last_reply
    assert ("Esterini", "SAY") in election._last_spoke


def test_one_bot_failure_does_not_sink_others(monkeypatch):
    async def flaky_run_chat(req, may_decline=False, *, lane="default"):
        if req.bot_name == "Brogdurn":
            raise RuntimeError("ollama timeout")
        return {"message": "im fine", "channel": req.channel, "emote": None, "actions": []}
    monkeypatch.setattr(main, "run_chat", flaky_run_chat)
    monkeypatch.setattr(main, "_heard_familiarity", lambda s, b: 0)
    monkeypatch.setattr(main, "_heard_persona_text", lambda b: "")
    monkeypatch.setattr(main, "_heard_recent_convo", lambda s, b: False)

    client = TestClient(main.app)
    r = _post(client, "esterini and brogdurn hello", ["Esterini", "Brogdurn"])
    assert r.status_code == 200
    body = r.json()["responses"]
    assert [x["bot_name"] for x in body] == ["Esterini"]
