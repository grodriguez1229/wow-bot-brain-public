import asyncio

import election
import main
from models import ChatRequest
from test_r8_heard import _stub_chat_deps
from test_r8_tick import _setup, _tick


def _r(msg):
    return {"message": msg, "channel": "SAY", "emote": None, "actions": []}


def _seq(*msgs):
    calls = []

    async def gen(extra):
        calls.append(extra)
        return _r(msgs[min(len(calls) - 1, len(msgs) - 1)])
    return gen, calls


def _level20(text):
    from knowledge import find_violations
    return find_violations(text, 20)


def _seq_ollama(monkeypatch, *replies):
    seen = []

    async def fake(system, history, user, **kw):
        seen.append(system)
        return replies[min(len(seen) - 1, len(replies) - 1)]
    monkeypatch.setattr(main, "call_ollama", fake)
    return seen


# ── generate_deduped ──────────────────────────────────────────────────────────

def test_knowledge_violation_rerolled_once_with_nudge():
    election.reset_state()
    gen, calls = _seq("anyone for MC?", "these murlocs man")
    out = asyncio.run(main.generate_deduped(gen, dedupe=True, knowledge=_level20,
                                            silence_on_narration=True))
    assert out["message"] == "these murlocs man"
    assert calls == ["", main.KNOWLEDGE_NUDGE]


def test_persistent_violation_silences_ambient():
    election.reset_state()
    gen, calls = _seq("anyone for MC?", "doing dailies")
    out = asyncio.run(main.generate_deduped(gen, dedupe=True, knowledge=_level20,
                                            silence_on_narration=True))
    assert out is None and len(calls) == 2


def test_persistent_violation_in_whisper_is_kept():
    election.reset_state()
    gen, calls = _seq("anyone for MC?", "MC tonight?")
    out = asyncio.run(main.generate_deduped(gen, dedupe=False, knowledge=_level20))
    assert out["message"] == "MC tonight?"


def test_no_knowledge_check_by_default():
    election.reset_state()
    gen, calls = _seq("anyone for MC?")
    out = asyncio.run(main.generate_deduped(gen, dedupe=True))
    assert out["message"] == "anyone for MC?" and len(calls) == 1


# ── endpoints ─────────────────────────────────────────────────────────────────

def test_tick_prompt_has_knowledge_section_and_filters(monkeypatch, capsys):
    seen = _setup(monkeypatch, ["MC was rough last night", "murlocs everywhere"])
    r = _tick()
    assert r.json()["message"] == "murlocs everywhere"
    assert "WHAT YOUR LEVEL 20 CHARACTER KNOWS" in seen[0]["system"]
    assert "[filter] Trean knowledge mc" in capsys.readouterr().out


def test_heard_reply_may_echo_what_was_said(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    seen = _seq_ollama(monkeypatch, "never been to MC lol")
    out = asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus",
                                                message="anyone been to MC?", channel="SAY"),
                                    lane="heard"))
    assert out["message"] == "never been to MC lol" and len(seen) == 1
    assert "WHAT YOUR LEVEL 20 CHARACTER KNOWS" in seen[0]


def test_heard_reply_with_unprompted_raid_talk_goes_silent(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    seen = _seq_ollama(monkeypatch, "lets do onyxia", "bwl later?")
    out = asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus",
                                                message="hey all", channel="SAY"), lane="heard"))
    assert out is None and len(seen) == 2


def test_whisper_gets_knowledge_section(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    seen = _seq_ollama(monkeypatch, "sup")
    asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus", message="hi")))
    assert "WHAT YOUR LEVEL 20 CHARACTER KNOWS" in seen[0]
