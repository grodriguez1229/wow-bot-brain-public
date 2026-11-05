"""R9 Task 8: whisper / heard reply lane voice fix."""
import asyncio
import random
import statistics

import pytest
from fastapi.testclient import TestClient

import main
import voice
from models import ChatRequest
from postfilter import is_self_intro
from prompts import build_action_rules, build_moments_section
from test_r8_heard import _stub_chat_deps
from vanilla_guard import find_banned
from voice_examples import WHISPER_PAIRS


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def _seq_ollama(monkeypatch, *replies):
    calls = []

    async def fake(system, history, user, **kw):
        calls.append({"system": system, "user": user, **kw})
        return replies[min(len(calls) - 1, len(replies) - 1)]
    monkeypatch.setattr(main, "call_ollama", fake)
    return calls


def _whisper(message="hi", **kw):
    return asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus",
                                                 message=message, **kw)))


def _heard(message="murlocs suck"):
    return asyncio.run(main.run_chat(ChatRequest(bot_name="Trean", player_name="Gus",
                                                 message=message, channel="SAY"), lane="heard"))


# ── is_self_intro ────────────────────────────────────────────────────────────

MATH = dict(bot_name="Mathalleas", race="Night Elf", class_name="Hunter", level=60)


def test_is_self_intro_cases():
    for t in ("im mathalleas by the way level 60 night elf hunter", "my name is bob",
              "lvl 60 hunter here", "I'm Mathalleas", "name's math", "Mathalleas here",
              "i am a level 60", "just a night elf hunter lol", "im lvl 60 now",
              "level 60 hunter, cant help sorry"):
        assert is_self_intro(t, **MATH), t
    for t in ("lol ya", "wc again?", "ur a rogue right", "lvl 10 rogue?", "sure omw",
              "what lvl r u", "level 20 orc warrior?", "hunter pets are dumb"):
        assert not is_self_intro(t, **MATH), t


def test_is_self_intro_level_only_counts_own_level():
    assert is_self_intro("im level 20", bot_name="Trean", race="Orc", class_name="Warrior", level=20)
    assert not is_self_intro("im level 30 soon", bot_name="Trean", race="Orc",
                             class_name="Warrior", level=20)


# ── prompt pieces ────────────────────────────────────────────────────────────

def test_action_rules_no_longer_offer_emotes():
    assert "[ACTION:emote" not in build_action_rules("Gus", caps={"party_invite"})
    assert build_action_rules("Gus", caps=set()) == ""


def test_build_moments_section():
    assert build_moments_section([], []) == ""
    s = build_moments_section(["ran Wailing Caverns together"], ["a", "b", "c", "d"])
    assert s.startswith("THINGS YOU TWO ACTUALLY DID (only these happened; never make up others):")
    assert "- ran Wailing Caverns together" in s
    assert "THINGS THEY SAID TO YOU BEFORE (their exact words):" in s
    assert '"b"' in s and '"d"' in s and '"a"' not in s          # last 3 only
    only_said = build_moments_section([], ["sup"])
    assert "ACTUALLY DID" not in only_said and '"sup"' in only_said


# ── run_chat wiring ──────────────────────────────────────────────────────────

def test_whisper_prompt_has_no_emote_and_no_long_cue(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    calls = _seq_ollama(monkeypatch, "sup")
    _whisper()
    s = calls[0]["system"]
    assert "[ACTION:emote" not in s and "2-4 sentences" not in s
    assert "Never introduce yourself" in s
    assert "No *actions*, no emotes" in s


def test_whisper_budget_from_shape(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "pick_shape", lambda *a, **k: "reaction")
    calls = _seq_ollama(monkeypatch, "honestly " * 9)          # 81 chars
    out = _whisper("hows it going")
    assert len(out["message"]) <= 25
    # every whisper can invite -> token floor so a tag never stops mid-way (review fix 1)
    assert calls[0]["num_predict"] == main.ACTION_TAG_TOKENS and calls[0]["lane"] == "chat"
    assert calls[0]["max_sentences"] == voice.SHAPE_MAX_SENTENCES["reaction"]


def test_whisper_shape_uses_whisper_weights(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    seen = []

    def fake_pick(channel, rng=None, *, reply=False, whisper=False):
        seen.append((reply, whisper))
        return "fragment"
    monkeypatch.setattr(main, "pick_shape", fake_pick)
    _seq_ollama(monkeypatch, "sup")
    _whisper()
    _heard()
    assert seen == [(True, True), (True, False)]


def test_pick_shape_whisper_weights():
    assert voice.WHISPER_SHAPE_WEIGHTS == {"reaction": 35, "question": 15, "fragment": 40,
                                           "ramble": 10}
    rng = random.Random(1)
    shapes = {voice.pick_shape("WHISPER", rng, reply=True, whisper=True) for _ in range(300)}
    assert shapes == set(voice.WHISPER_SHAPE_WEIGHTS)


def test_invite_request_gets_tag_headroom(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "pick_shape", lambda *a, **k: "reaction")
    calls = _seq_ollama(monkeypatch, "sure\n[ACTION:invite Gus]")
    out = _whisper("can u invite me")
    assert calls[0]["num_predict"] >= 32
    assert out["actions"] == [{"type": "invite", "target": "Gus"}]


def test_heard_reaction_keeps_shape_tokens(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "pick_shape", lambda *a, **k: "reaction")
    calls = _seq_ollama(monkeypatch, "lol")
    _heard()
    assert calls[0]["num_predict"] == 12           # no invite caps on the heard lane


def test_unterminated_action_tag_never_leaks():
    from llm import parse_response
    for raw in ("sure [ACTION:invite Gu", "ok\n[ACTION:inv", "lol [EMOTE:wa"):
        r = parse_response(raw, "WHISPER")
        assert "[" not in r["message"] and r["message"], raw


def test_intro_from_a_later_reroll_is_silenced(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    p = main.get_or_create_personality("Trean")
    monkeypatch.setattr(main, "get_or_create_personality", lambda n: dict(p, level=10))
    calls = _seq_ollama(monkeypatch, "molten core tonight?", "im trean lvl 10 lol")
    assert _whisper("hey") is None and len(calls) == 2
    calls = _seq_ollama(monkeypatch, "molten core tonight?", "im trean lvl 10 lol")
    assert _heard("hey") is None


def test_wanna_group_pair_does_not_agree_without_tag():
    for theirs, mine in WHISPER_PAIRS:
        if "group" in theirs or "inv" in theirs:
            assert not mine.startswith(("sure", "ya", "yes", "ok")), (theirs, mine)


def test_friendship_error_never_breaks_chat(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)

    def boom(*a, **k):
        raise RuntimeError("db locked")
    monkeypatch.setattr(main, "friendship", type("F", (), {"apply_decay": staticmethod(boom),
                                                           "add_chat": staticmethod(boom)}))
    monkeypatch.setattr(main, "get_relationship", boom)
    _seq_ollama(monkeypatch, "sup")
    assert _whisper()["message"] == "sup"
    assert _heard()["message"] == "sup"


def test_silent_heard_reply_touches_no_relationship(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    log = []
    monkeypatch.setattr(main, "friendship", type("F", (), {
        "apply_decay": staticmethod(lambda *a, **k: log.append("decay")),
        "add_chat": staticmethod(lambda *a, **k: log.append("chat"))}))
    _seq_ollama(monkeypatch, "im trean", "im trean")
    assert _heard() is None and log == []
    _seq_ollama(monkeypatch, "ya murlocs suck")
    _heard()
    assert log == ["chat"]


def test_heard_budget_from_shape(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    monkeypatch.setattr(main, "pick_shape", lambda *a, **k: "fragment")
    calls = _seq_ollama(monkeypatch, "word " * 40)
    out = _heard()
    assert len(out["message"]) <= 70
    assert calls[0]["num_predict"] == voice.SHAPE_NUM_PREDICT["fragment"]
    assert calls[0]["lane"] == "heard"


def test_self_intro_rerolls_then_silences(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    calls = _seq_ollama(monkeypatch, "im trean lvl 20 orc warrior", "im trean lol")
    assert _whisper("sup") is None and len(calls) == 2
    assert calls[1]["system"].endswith(main.SELF_INTRO_NUDGE)
    calls = _seq_ollama(monkeypatch, "im trean lvl 20 orc warrior", "ya im down")
    out = _whisper("wanna quest")
    assert out["message"] == "ya im down" and len(calls) == 2


def test_self_intro_silences_heard_too(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    calls = _seq_ollama(monkeypatch, "im trean", "trean here")
    assert _heard() is None and len(calls) == 2


def test_silent_whisper_endpoint_returns_empty_message(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    _seq_ollama(monkeypatch, "im trean", "im trean")
    r = TestClient(main.app).post("/chat", json={"bot_name": "Trean", "player_name": "Gus",
                                                 "message": "sup"})
    assert r.status_code == 200 and r.json()["message"] == ""


def test_self_intro_allowed_when_asked(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    calls = _seq_ollama(monkeypatch, "im lvl 20")
    out = _whisper("what lvl r u")
    assert out["message"] == "im lvl 20" and len(calls) == 1


def test_moments_in_whisper_prompt_only(monkeypatch, fresh_db):
    import history
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "shared_history", history)
    history.add_moment("Gus", "Trean", "ran Wailing Caverns together, 2026-11-05",
                       source="fixture", source_id=1, places=["Wailing Caverns"])
    monkeypatch.setattr(main, "get_memory", lambda b, pl: [
        {"role": "user", "content": "thx for the heals"},
        {"role": "assistant", "content": "np"}])
    calls = _seq_ollama(monkeypatch, "sup")
    _whisper()
    _heard()
    assert "ran Wailing Caverns together, 2026-11-05" in calls[0]["system"]
    assert '"thx for the heals"' in calls[0]["system"]
    assert "THINGS YOU TWO ACTUALLY DID" not in calls[1]["system"]
    assert "Wailing Caverns together" not in calls[1]["system"]


def test_moments_read_failure_does_not_break_whisper(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)

    class Boom:
        @staticmethod
        def moments_for(*a, **k):
            raise RuntimeError("db locked")
    monkeypatch.setattr(main, "shared_history", Boom)
    _seq_ollama(monkeypatch, "sup")
    assert _whisper()["message"] == "sup"


def test_knowledge_filter_still_applies(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    p = main.get_or_create_personality("Trean")
    monkeypatch.setattr(main, "get_or_create_personality", lambda n: dict(p, level=10))
    calls = _seq_ollama(monkeypatch, "molten core tonight?", "sure")
    out = _whisper("hey")
    assert len(calls) == 2 and out["message"] == "sure"


def test_whisper_relationship_via_friendship(monkeypatch, capsys):
    _stub_chat_deps(monkeypatch, "x")
    monkeypatch.setattr(main, "VOICE_TRANSFORM", False)
    monkeypatch.setattr(main, "pick_shape", lambda *a, **k: "fragment")
    log = []

    class F:
        @staticmethod
        def apply_decay(bot, player, **k):
            log.append(("decay", bot, player))

        @staticmethod
        def add_chat(bot, player, *a, **k):
            log.append(("chat", bot, player))
    monkeypatch.setattr(main, "friendship", F)
    _seq_ollama(monkeypatch, "sup")
    _whisper()
    assert log == [("decay", "Trean", "Gus"), ("chat", "Trean", "Gus")]
    out = capsys.readouterr().out
    assert "[chat:chat] Gus -> Trean (" in out and "rel=stranger, shape=fragment)" in out


# ── whisper pair bank ────────────────────────────────────────────────────────

def test_whisper_pairs_bank():
    assert len(WHISPER_PAIRS) >= 40
    personas = [dict(bot_name="Trean", race="Orc", class_name="Warrior", level=20),
                dict(bot_name="Mathalleas", race="Night Elf", class_name="Hunter", level=60),
                dict(bot_name="Esterini", race="Human", class_name="Priest", level=35)]
    for theirs, mine in WHISPER_PAIRS:
        assert find_banned(theirs) == [] and find_banned(mine) == [], (theirs, mine)
        for pp in personas:
            assert not is_self_intro(mine, **pp), mine
    assert statistics.median(len(m) for _t, m in WHISPER_PAIRS) <= 30


def test_sample_whisper_pairs():
    got = voice.sample_whisper_pairs(4, rng=random.Random(3))
    assert len(got) == 4 and all(g in WHISPER_PAIRS for g in got)
    assert len(set(got)) == 4


def test_whisper_prompt_shows_whisper_pairs(monkeypatch):
    _stub_chat_deps(monkeypatch, "x")
    calls = _seq_ollama(monkeypatch, "sup")
    _whisper()
    s = calls[0]["system"]
    assert sum(f"{a}  ->  {b}" in s for a, b in WHISPER_PAIRS) >= 3


# ── carry-over: /tick survives a presence error ──────────────────────────────

def test_tick_survives_presence_error(monkeypatch, capsys):
    from test_r8_tick import _setup, _tick

    def boom(*a, **k):
        raise RuntimeError("db locked")
    _setup(monkeypatch, ["murlocs everywhere"])
    monkeypatch.setattr(main.presence, "note_tick", boom)
    r = _tick()
    assert r.status_code == 200 and r.json()["message"] == "murlocs everywhere"
    assert "[presence] error" in capsys.readouterr().out


# ── llm: sentence truncation keeps action tags ───────────────────────────────

def test_truncation_keeps_action_tag(monkeypatch):
    import llm

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "sure thing buddy. sending it now. [ACTION:invite Gus]"}}

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return Resp()
    monkeypatch.setattr(llm.httpx, "AsyncClient", Client)
    raw = asyncio.run(llm.call_ollama("s", [], "u", num_predict=12, max_sentences=1, lane="chat"))
    assert raw.startswith("sure thing buddy.") and "sending" not in raw
    assert "[ACTION:invite Gus]" in raw
