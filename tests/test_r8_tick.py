import random

from fastapi.testclient import TestClient

import ad_templates
import chat_log
import election
import irl_budget
import main
import voice
from prompts import (build_chat_log_section, build_examples_section, build_tick_user_message,
                     TICK_PROMPT)

IRL = {"archetype": "retail_worker", "who_core": "23yo retail worker.", "irl_facts": [],
       "irl_terms": [], "signature": None, "signature_irl": False, "typing_style": "casual",
       "who": "23yo retail worker."}
P = {"bot_name": "Trean", "race": "Orc", "class_name": "Warrior", "level": 20, "gender": "male",
     "faction": "Horde", "identity_id": "retail_worker", "who": IRL["who"], "typing_style": "casual",
     "current_goal": "hit 30", "guild_name": "", "motivation": "farmer", "can_guild_invite": False,
     "irl": IRL}


def _setup(monkeypatch, replies, *, rnd=0.99, shape="fragment", channel="GENERAL"):
    election.reset_state()
    irl_budget.reset_state()
    chat_log.reset_state()
    voice.reset_state()
    ad_templates.reset_state()
    seen = []

    async def fake_ollama(system, history, user, **kw):
        seen.append({"system": system, "user": user, **kw})
        return replies[min(len(seen) - 1, len(replies) - 1)]
    monkeypatch.setattr(main, "call_ollama", fake_ollama)
    monkeypatch.setattr(main, "get_or_create_personality", lambda n: dict(P, bot_name=n))
    monkeypatch.setattr(main, "get_memory_sheet", lambda b, k: [])
    monkeypatch.setattr(main, "known_bot_names", lambda: frozenset({"Trean", "Esterini"}))
    monkeypatch.setattr(main.random, "random", lambda: rnd)
    monkeypatch.setattr(main, "pick_shape", lambda ch, rng=None, reply=False: shape)
    monkeypatch.setattr(main, "pick_tick_activity",
                        lambda *a, **k: {"channel": channel, "prompt": "x"})
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    return seen


def _tick(**kw):
    body = {"bot_name": "Trean", "location": "Durotar"}
    body.update(kw)
    return TestClient(main.app).post("/tick", json=body)


def test_breathe_silence_makes_no_llm_call(monkeypatch, capsys):
    seen = _setup(monkeypatch, ["hi"], rnd=0.0)
    r = _tick()
    assert r.status_code == 200 and r.json()["message"] == ""
    assert seen == []
    assert "(silent, breathe)" in capsys.readouterr().out


def test_ad_shape_is_template_without_llm(monkeypatch, capsys):
    seen = _setup(monkeypatch, ["should not be used"], shape="ad", channel="LFG")
    r = _tick()
    msg = r.json()["message"]
    assert seen == [] and msg and r.json()["channel"] == "LFG"
    out = capsys.readouterr().out
    assert f'[tick] Trean -> LFG [ad]: "{msg}"' in out
    assert chat_log.reply_candidates("Other", faction="Horde", zone="Durotar")[0]["text"] == msg


def test_ad_falls_back_to_llm_question_when_no_dungeon_fits(monkeypatch):
    seen = _setup(monkeypatch, ["any groups around here?"], shape="ad", channel="LFG")
    monkeypatch.setattr(main, "get_or_create_personality", lambda n: dict(P, bot_name=n, level=5))
    r = _tick()
    assert len(seen) == 1 and r.json()["message"] == "any groups around here?"


def test_fragment_uses_examples_and_shape_budget(monkeypatch):
    seen = _setup(monkeypatch, ["word " * 40])
    r = _tick()
    assert len(r.json()["message"]) <= 70
    assert "HOW PEOPLE TYPE IN GENERAL CHAT" in seen[0]["system"]
    assert seen[0]["num_predict"] == voice.SHAPE_NUM_PREDICT["fragment"]
    assert "Type your next message in General chat" in seen[0]["user"]


def test_reply_path(monkeypatch, capsys):
    seen = _setup(monkeypatch, ["by the bank"], rnd=0.3)       # >silence, <reply rate
    root = chat_log.record_line("Esterini", "GENERAL", "where is the inn", faction="Horde",
                                zone="Durotar")
    r = _tick()
    assert r.json() == {**r.json(), "message": "by the bank", "channel": "GENERAL"}
    assert "Esterini: where is the inn" in seen[0]["system"]
    assert "Type your reply to Esterini" in seen[0]["user"]
    assert "HOW PEOPLE ANSWER EACH OTHER" in seen[0]["system"]
    assert '[tick] Trean -> GENERAL [fragment] (re Esterini): "by the bank"' in capsys.readouterr().out
    reply = chat_log._log[-1]
    assert reply["reply_to"] == root and reply["depth"] == 1
    assert chat_log.get(root)["replies"] == 1


def test_no_reply_from_other_faction_or_mid_fight(monkeypatch, capsys):
    _setup(monkeypatch, ["ugh"], rnd=0.3)
    chat_log.record_line("Ally", "GENERAL", "where is the inn", faction="Alliance", zone="Durotar")
    _tick()
    chat_log.record_line("Esterini", "GENERAL", "where is the inn", faction="Horde", zone="Durotar")
    _tick(activity="in_combat", target="Boar")
    assert "(re " not in capsys.readouterr().out


def test_example_copy_rerolls(monkeypatch):
    seen = _setup(monkeypatch, ["anyone know where to turn this in", "where do i sell wolf pelts"])
    monkeypatch.setattr(main, "sample_examples",
                        lambda *a, **k: ["anyone know where to turn this in"])
    r = _tick()
    assert len(seen) == 2 and r.json()["message"] == "where do i sell wolf pelts"


def test_transform_applied_with_protected_names(monkeypatch):
    _setup(monkeypatch, ["Hello There"], rnd=0.3)
    chat_log.record_line("Esterini", "GENERAL", "yo", faction="Horde", zone="Durotar")
    calls = []

    def fake_transform(text, bot, **kw):
        calls.append(kw)
        return text.lower()
    monkeypatch.setattr(main, "VOICE_TRANSFORM", True)
    monkeypatch.setattr(main, "transform", fake_transform)
    r = _tick()
    assert r.json()["message"] == "hello there"
    assert {"Esterini", "Trean"} <= calls[0]["protect"]
    assert chat_log._log[-1]["text"] == "hello there"


def test_sim_recent_lines_still_render_as_overheard(monkeypatch):
    seen = _setup(monkeypatch, ["ya"])
    _tick(recent_lines=[{"speaker": "Lynea", "text": "anyone running Deadmines?"}])
    assert "Lynea: anyone running Deadmines?" in seen[0]["system"]


def test_situation_line():
    rng = random.Random(0)
    s = main.build_tick_situation("in_combat", "Boar", "Durotar", "SAY", ["Gus"], rng=rng)
    assert s.startswith("You're fighting Boar in Durotar.") and "Gus standing near you" in s
    assert "Maybe:" not in s
    assert "Maybe:" in main.build_tick_situation(None, None, "Durotar", "GENERAL", rng=rng)
    assert "Maybe:" not in main.build_tick_situation(None, None, "Durotar", "GENERAL",
                                                     topic=False, rng=rng)


def test_prompt_builders():
    assert "{examples_section}" in TICK_PROMPT
    s = build_examples_section("LFG", ["inv pls", "lf1m heals"], [("need a tank?", "yes pls")])
    assert "LOOKINGFORGROUP" in s and "  inv pls" in s and "need a tank?  ->  yes pls" in s
    assert build_examples_section("SAY", []) == ""
    assert build_chat_log_section("GUILD", [("A", "hi"), ("B", "yo")]).endswith("  B: yo")
    assert build_chat_log_section("GUILD", []) == ""
    u = build_tick_user_message("TRADE", "a quick reaction, 1-3 words", "You're in Org.",
                                reply_to=("Bob", "wts ore"))
    assert "Bob just said: wts ore" in u and "reply to Bob in Trade chat" in u
