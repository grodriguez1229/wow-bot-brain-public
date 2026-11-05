from fastapi.testclient import TestClient

import chat_log
import election
import irl_budget
import main
from prompts import IRL_DENIED_RULE
from test_r8_heard import stub_r9_reads

IRL = {"archetype": "retail_worker", "who_core": "23yo retail worker. Plays after work.",
       "irl_facts": ["works at GameStop", "has a cat named Mochi"], "irl_terms": ["gamestop", "mochi"],
       "signature": None, "signature_irl": False, "typing_style": "casual",
       "who": "23yo retail worker. Plays after work. works at GameStop. has a cat named Mochi."}
P = {"bot_name": "Trean", "race": "Orc", "class_name": "Warrior", "level": 20, "gender": "male",
     "faction": "Horde", "identity_id": "retail_worker", "who": IRL["who"], "typing_style": "casual",
     "current_goal": "hit 30", "guild_name": "", "motivation": "farmer", "can_guild_invite": False,
     "irl": IRL}


def _setup(monkeypatch, replies):
    election.reset_state()
    irl_budget.reset_state()
    seen = []

    async def fake_ollama(system, history, user, **kw):
        seen.append(system)
        return replies[min(len(seen) - 1, len(replies) - 1)]
    monkeypatch.setattr(main, "call_ollama", fake_ollama)
    monkeypatch.setattr(main, "get_or_create_personality", lambda n: dict(P, bot_name=n))
    monkeypatch.setattr(main, "get_memory_sheet", lambda b, k: [])
    monkeypatch.setattr(main, "known_bot_names", lambda: frozenset({"Trean", "Esterini"}))
    monkeypatch.setattr(main.random, "random", lambda: 0.99)   # signature off
    # R8 knobs pinned so these R3 checks always reach the LLM with a verbatim line.
    chat_log.reset_state()
    monkeypatch.setattr(main, "pick_shape", lambda *a, **k: "fragment")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    return seen


def _tick(client):
    return client.post("/tick", json={"bot_name": "Trean", "location": "Durotar"})


def test_tick_allowed_shows_facts_and_counts_line(monkeypatch):
    seen = _setup(monkeypatch, ["my cat Mochi is on the keyboard"])
    r = _tick(TestClient(main.app))
    assert r.json()["message"] == "my cat Mochi is on the keyboard"
    assert "works at GameStop" in seen[0]
    assert IRL["who_core"] in seen[0] and "GameStop. has a cat" not in seen[0].split("YOUR LIFE")[0]
    assert irl_budget.share() == 1.0              # counted as IRL (via irl_terms)


def test_tick_denied_when_budget_spent(monkeypatch):
    seen = _setup(monkeypatch, ["murlocs everywhere"])
    for _ in range(10):
        irl_budget.note_ambient_line("my gf says hi")
    _tick(TestClient(main.app))
    assert IRL_DENIED_RULE in seen[0]
    assert "GameStop" not in seen[0]


def test_tick_all_emoji_is_silent(monkeypatch, capsys):
    _setup(monkeypatch, ["😂😂😂"])
    r = _tick(TestClient(main.app))
    assert r.status_code == 200 and r.json()["message"] == ""
    out = capsys.readouterr().out
    assert "(silent)" in out and '-> ' in out and ': ""' not in out
    assert irl_budget.share() == 0.0 and len(irl_budget._window) == 0


def test_tick_persistent_narration_is_silent(monkeypatch):
    _setup(monkeypatch, ["Trean sighs softly", "Trean stretches"])
    r = _tick(TestClient(main.app))
    assert r.json()["message"] == ""


def test_tick_long_line_capped(monkeypatch):
    _setup(monkeypatch, ["word " * 80])
    r = _tick(TestClient(main.app))
    assert len(r.json()["message"]) <= 140


def test_whisper_keeps_full_persona_and_is_not_irl_budgeted(monkeypatch):
    seen = _setup(monkeypatch, ["long day at GameStop honestly " * 10])
    monkeypatch.setattr(main, "get_relationship", lambda b, p: {"label": "stranger", "familiarity": 0, "notes": ""})
    monkeypatch.setattr(main, "describe_relationship", lambda rel: "stranger")
    monkeypatch.setattr(main, "get_memory", lambda b, p: [])
    monkeypatch.setattr(main, "save_message", lambda *a: None)
    stub_r9_reads(monkeypatch)
    monkeypatch.setattr(main, "_maybe_reflect_self", lambda *a: None)
    for _ in range(10):
        irl_budget.note_ambient_line("my gf says hi")
    r = TestClient(main.app).post("/chat", json={"bot_name": "Trean", "player_name": "Gus",
                                                 "message": "how was your day?"})
    assert IRL["who"] in seen[0] and IRL_DENIED_RULE not in seen[0]
    assert "talk about ANYTHING a real person would" in seen[0]
    assert 0 < len(r.json()["message"]) <= main.CHAT_MAX_CHARS   # R9: shape-bound, not run-ons
    assert len(irl_budget._window) == 10                        # not counted


def test_heard_lane_is_gated_and_counted(monkeypatch):
    seen = _setup(monkeypatch, ["ya murlocs are rough here"])
    monkeypatch.setattr(main, "get_relationship", lambda b, p: {"label": "stranger", "familiarity": 0, "notes": ""})
    monkeypatch.setattr(main, "describe_relationship", lambda rel: "stranger")
    monkeypatch.setattr(main, "get_memory", lambda b, p: [])
    monkeypatch.setattr(main, "save_message", lambda *a: None)
    stub_r9_reads(monkeypatch)
    monkeypatch.setattr(main, "_maybe_reflect_self", lambda *a: None)
    for _ in range(10):
        irl_budget.note_ambient_line("my gf says hi")
    import asyncio
    from models import ChatRequest
    out = asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus",
                                                message="murlocs suck", channel="SAY"), lane="heard"))
    assert out["message"] == "ya murlocs are rough here"
    assert IRL_DENIED_RULE in seen[0] and "GameStop" not in seen[0]
    assert len(irl_budget._window) == 11


def test_heard_all_emoji_is_silent(monkeypatch):
    _setup(monkeypatch, ["😂😂😂"])
    monkeypatch.setattr(main, "get_relationship", lambda b, p: {"label": "stranger", "familiarity": 0, "notes": ""})
    monkeypatch.setattr(main, "describe_relationship", lambda rel: "stranger")
    monkeypatch.setattr(main, "get_memory", lambda b, p: [])
    monkeypatch.setattr(main, "save_message", lambda *a: None)
    stub_r9_reads(monkeypatch)
    monkeypatch.setattr(main, "_maybe_reflect_self", lambda *a: None)
    import asyncio
    from models import ChatRequest
    out = asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus",
                                                message="murlocs suck", channel="SAY"), lane="heard"))
    assert out is None and len(irl_budget._window) == 0


def test_known_bot_names_survives_db_error(monkeypatch):
    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(main, "get_bot_names", boom)
    monkeypatch.setattr(main, "_names_cache", {"ts": float("-inf"), "names": frozenset({"Old"})})
    assert main.known_bot_names() == frozenset({"Old"})
    assert main.known_bot_names() == frozenset({"Old"})


def test_heard_persona_text_uses_who_core(monkeypatch):
    p = dict(P, who="23yo retail worker. Plays after work. lives with their girlfriend Jess.",
             irl=dict(IRL, who_core="23yo retail worker. Plays after work."))
    monkeypatch.setattr(main, "get_or_create_personality", lambda n: p)
    t = main._heard_persona_text("X")
    assert "Jess" not in t and "lives" not in t
    assert "23yo retail worker. Plays after work." in t


def test_heard_persona_text_falls_back_to_who(monkeypatch):
    p = dict(P, who="plain who", irl={"pinned": True})
    monkeypatch.setattr(main, "get_or_create_personality", lambda n: p)
    assert "plain who" in main._heard_persona_text("X")


def _heard_prompt(monkeypatch, lane, spend):
    seen = _setup(monkeypatch, ["ya murlocs are rough here"])
    monkeypatch.setattr(main, "get_relationship", lambda b, p: {"label": "stranger", "familiarity": 0, "notes": ""})
    monkeypatch.setattr(main, "describe_relationship", lambda rel: "stranger")
    monkeypatch.setattr(main, "get_memory", lambda b, p: [])
    monkeypatch.setattr(main, "save_message", lambda *a: None)
    stub_r9_reads(monkeypatch)
    monkeypatch.setattr(main, "_maybe_reflect_self", lambda *a: None)
    if spend:
        for _ in range(10):
            irl_budget.note_ambient_line("my gf says hi")
    import asyncio
    from models import ChatRequest
    asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus",
                                          message="murlocs suck", channel="SAY"), lane=lane))
    return seen[0]


def test_heard_budget_spent_drops_real_life_bullet(monkeypatch):
    s = _heard_prompt(monkeypatch, "heard", True)
    assert "talk about ANYTHING a real person would" not in s and IRL_DENIED_RULE in s


def test_heard_budget_open_keeps_real_life_bullet(monkeypatch):
    s = _heard_prompt(monkeypatch, "heard", False)
    assert "talk about ANYTHING a real person would" in s
