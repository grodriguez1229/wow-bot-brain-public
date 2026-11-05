# Heard-Chat Election Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bots react to player messages on say/yell/party/guild/General/Trade/LFG via a tiered election (named = guaranteed, engaged ≈ 60%, candidates ≈ 15% and may decline), replacing the existing blind random rolls.

**Architecture:** The module's once-per-message `OnPlayerCanUseChat` hooks assemble a hearer roster and POST one `/heard` to the brain. The brain elects responders (it owns familiarity/history/personas), runs the existing chat prompt per elected bot, and returns all replies synchronously in the response body; the bridge queues each for `PopResponse` to speak in-game.

**Tech Stack:** Python 3.12 / FastAPI / pytest (wow-bot-brain, repo `~/wow-bot-brain`, branch `evolution-council`); C++20 / boost::beast (mod-playerbots, repo `~/azerothcore/azerothcore-wotlk/modules/mod-playerbots`, branch `master`). Tests run as `venv/bin/python -m pytest` from the wow-bot-brain root.

**Spec:** `docs/superpowers/specs/2026-07-14-heard-chat-election-design.md`

## Global Constraints

- Max **2** responders per message; **named bots exempt** from the cap (and from cooldown).
- Per-bot per-channel reply cooldown: **30s**. Engaged window: **120s** (spoke in channel) / **600s** (recent convo with speaker). Chances: engaged **0.6**, candidate **0.15**.
- Global LLM concurrency: **asyncio.Semaphore(2)** in `llm.call_ollama` (shared by /chat, /tick, /heard).
- Hearer roster capped at **30** (named hearers always retained).
- Kill switch: `AiPlayerbot.LlmHeardEnabled` (default true), env `AC_AI_PLAYERBOT_LLM_HEARD_ENABLED`.
- Whisper path unchanged. Speaker must be a **real player** (never a bot). Worldserver never blocks the world thread (`PostHeard` runs in a detached worker thread, 75s HTTP timeout).
- Candidate-tier silence token: the literal reply `PASS`.
- C++ changes are module-only (no AzerothCore core edits).

---

### Task 1: Brain — election module: named tier + hearer capping

**Files:**
- Create: `election.py`
- Create: `tests/test_election.py`
- Modify: `config.py` (append constants)

**Interfaces:**
- Produces: `election.named_in(message: str, bot_names: list[str]) -> list[str]`;
  `election.cap_hearers(hearers: list[dict], message: str, cap: int = HEARD_MAX_HEARERS) -> list[dict]`
  (hearer dict shape everywhere: `{"bot_name": str, "distance": float, "same_party": bool, "same_guild": bool}`).
- Consumes: nothing.

- [ ] **Step 1: Append election constants to `config.py`**

```python
# ── /heard election (slice 1: heard-chat election) ──────────────────────────
HEARD_ENGAGED_WINDOW_S = 120     # bot spoke in this channel this recently => engaged
HEARD_CONVO_WINDOW_S = 600      # bot<->speaker messages this recent => engaged
HEARD_ENGAGED_CHANCE = 0.6
HEARD_CANDIDATE_CHANCE = 0.15
HEARD_MAX_RESPONDERS = 2        # named bots exempt
HEARD_COOLDOWN_S = 30           # per bot per channel
HEARD_MAX_HEARERS = 30
LLM_MAX_CONCURRENCY = 2
```

- [ ] **Step 2: Write the failing tests**

```python
"""Election for /heard: who answers when a player talks in a channel."""
from election import named_in, cap_hearers


def _h(name, distance=10.0):
    return {"bot_name": name, "distance": distance, "same_party": False, "same_guild": False}


def test_named_full_and_prefix_match():
    bots = ["Esterini", "Brogdurn", "Vivi"]
    assert named_in("hey esterini wanna group?", bots) == ["Esterini"]
    assert named_in("ester you there?", bots) == ["Esterini"]        # >=4-char prefix
    assert named_in("yo brogdurn and esterini!", bots) == ["Brogdurn", "Esterini"] or \
           named_in("yo brogdurn and esterini!", bots) == ["Esterini", "Brogdurn"]


def test_named_short_prefix_and_substring_do_not_match():
    bots = ["Esterini", "Vivi"]
    assert named_in("est is my favorite time zone", bots) == []      # <4 chars
    assert named_in("investing in linen", bots) == []                # substring, not word prefix
    assert named_in("vivi!", bots) == ["Vivi"]                       # exact name shorter than 4 ok


def test_cap_hearers_keeps_named_and_nearest():
    hearers = [_h(f"Bot{i:02d}", distance=float(i)) for i in range(40)]
    hearers.append(_h("Esterini", distance=999.0))
    kept = cap_hearers(hearers, "esterini help!", cap=30)
    names = [h["bot_name"] for h in kept]
    assert len(kept) == 30
    assert "Esterini" in names           # named retained despite max distance
    assert "Bot00" in names and "Bot38" not in names  # nearest fill the rest
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_election.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'election'`

- [ ] **Step 4: Implement `election.py` (named + capping only)**

```python
"""Responder election for /heard events.

Pure decision logic + a small in-memory recency state (resets on restart —
acceptable per spec: worst case is one missed 'engaged' window)."""
import random
import re
import time

from config import (HEARD_ENGAGED_WINDOW_S, HEARD_CONVO_WINDOW_S, HEARD_ENGAGED_CHANCE,
                    HEARD_CANDIDATE_CHANCE, HEARD_MAX_RESPONDERS, HEARD_COOLDOWN_S,
                    HEARD_MAX_HEARERS)

_MIN_PREFIX = 4


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def named_in(message: str, bot_names: list[str]) -> list[str]:
    """Bots addressed by name: a message word equals the name or is a >=4-char prefix of it."""
    words = set(_words(message))
    out = []
    for name in bot_names:
        low = name.lower()
        if low in words or any(len(w) >= _MIN_PREFIX and low.startswith(w) for w in words):
            out.append(name)
    return out


def cap_hearers(hearers: list[dict], message: str, cap: int = HEARD_MAX_HEARERS) -> list[dict]:
    """Bound the roster: named hearers always kept, nearest fill the remainder."""
    if len(hearers) <= cap:
        return hearers
    named = set(named_in(message, [h["bot_name"] for h in hearers]))
    keep = [h for h in hearers if h["bot_name"] in named]
    rest = sorted((h for h in hearers if h["bot_name"] not in named),
                  key=lambda h: h.get("distance", 0.0))
    return keep + rest[: max(0, cap - len(keep))]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_election.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add config.py election.py tests/test_election.py
git commit -m "feat(heard): election module — named tier + hearer capping"
```

---

### Task 2: Brain — election tiers, cap, cooldown

**Files:**
- Modify: `election.py`
- Modify: `tests/test_election.py`

**Interfaces:**
- Produces:
  `election.elect(hearers, message, speaker, channel, *, get_familiarity, get_persona_text, recent_convo, now=None, rng=None) -> list[dict]`
  returning `[{"bot_name": str, "tier": "named"|"engaged"|"candidate"}, ...]`.
  `get_familiarity(bot_name) -> int (0-5)`; `get_persona_text(bot_name) -> str`;
  `recent_convo(bot_name) -> bool` (bot↔speaker messages within HEARD_CONVO_WINDOW_S).
  `election.note_bot_spoke(bot_name, channel, now=None)` — call whenever a bot says
  anything in a channel (tick or reply). `election.note_replied(bot_name, channel, now=None)`
  — starts the cooldown. `election.is_pass(text) -> bool` — candidate silence token.
  `election.reset_state()` — test helper clearing recency dicts.
- Consumes: Task 1's `named_in`.

- [ ] **Step 1: Write the failing tests (append to `tests/test_election.py`)**

```python
import election
from election import elect, note_bot_spoke, note_replied, reset_state, is_pass


class FakeRng:
    """random() returns queued values in order (then 1.0 = never fires)."""
    def __init__(self, values):
        self.values = list(values)
    def random(self):
        return self.values.pop(0) if self.values else 1.0


def _deps(fam=None, persona=None, convo=None):
    return dict(
        get_familiarity=lambda b: (fam or {}).get(b, 0),
        get_persona_text=lambda b: (persona or {}).get(b, ""),
        recent_convo=lambda b: (convo or {}).get(b, False),
    )


def setup_function(_):
    reset_state()


def test_named_always_elected_even_on_cooldown():
    note_replied("Esterini", "SAY", now=1000.0)
    out = elect([_h("Esterini")], "esterini hello again", "Abril", "SAY",
                **_deps(), now=1005.0, rng=FakeRng([]))
    assert out == [{"bot_name": "Esterini", "tier": "named"}]


def test_engaged_recent_channel_speaker_elected_on_roll():
    note_bot_spoke("Vivi", "GENERAL", now=1000.0)
    out = elect([_h("Vivi")], "anyone selling bags?", "Abril", "GENERAL",
                **_deps(), now=1060.0, rng=FakeRng([0.5]))   # 0.5 < 0.6 => fires
    assert out == [{"bot_name": "Vivi", "tier": "engaged"}]


def test_engaged_window_expired_falls_through():
    note_bot_spoke("Vivi", "GENERAL", now=1000.0)
    out = elect([_h("Vivi")], "anyone selling bags?", "Abril", "GENERAL",
                **_deps(), now=1200.0, rng=FakeRng([0.5]))   # 200s > 120s window
    assert out == []


def test_recent_convo_counts_as_engaged():
    out = elect([_h("Vivi")], "anyone selling bags?", "Abril", "GENERAL",
                **_deps(convo={"Vivi": True}), now=1000.0, rng=FakeRng([0.5]))
    assert out == [{"bot_name": "Vivi", "tier": "engaged"}]


def test_candidate_scored_by_familiarity_and_keywords_rolls_low_chance():
    deps = _deps(fam={"Esterini": 5}, persona={"Esterini": "run Deadmines or Wailing Caverns"})
    out = elect([_h("Esterini"), _h("Brogdurn")], "who wants deadmines?", "Abril", "GENERAL",
                **deps, now=1000.0, rng=FakeRng([0.1]))      # 0.1 < 0.15 => fires
    assert out == [{"bot_name": "Esterini", "tier": "candidate"}]


def test_zero_score_hearers_are_never_candidates():
    out = elect([_h("Brogdurn")], "who wants deadmines?", "Abril", "GENERAL",
                **_deps(), now=1000.0, rng=FakeRng([0.0]))
    assert out == []


def test_cap_two_non_named_but_named_exempt():
    for b in ("A1", "A2", "A3"):
        note_bot_spoke(b, "SAY", now=1000.0)
    hearers = [_h("A1"), _h("A2"), _h("A3"), _h("Esterini"), _h("Brogdurn")]
    out = elect(hearers, "esterini brogdurn look at this", "Abril", "SAY",
                **_deps(), now=1010.0, rng=FakeRng([0.0, 0.0, 0.0]))
    names = [e["bot_name"] for e in out]
    assert "Esterini" in names and "Brogdurn" in names       # named, exempt
    assert len([e for e in out if e["tier"] != "named"]) == 0  # cap already used by 2 named


def test_cooldown_blocks_non_named():
    note_bot_spoke("Vivi", "GENERAL", now=1000.0)
    note_replied("Vivi", "GENERAL", now=1005.0)
    out = elect([_h("Vivi")], "hello?", "Abril", "GENERAL",
                **_deps(), now=1010.0, rng=FakeRng([0.0]))   # 5s < 30s cooldown
    assert out == []


def test_is_pass():
    assert is_pass("PASS") and is_pass(" pass ") and is_pass("")
    assert not is_pass("PASSing through Deadmines")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_election.py -v`
Expected: FAIL with `ImportError: cannot import name 'elect'`

- [ ] **Step 3: Implement (append to `election.py`)**

```python
# ── recency state ────────────────────────────────────────────────────────────
_last_spoke: dict[tuple[str, str], float] = {}    # (bot, channel) -> last line ts
_last_reply: dict[tuple[str, str], float] = {}    # (bot, channel) -> last elected reply ts


def reset_state() -> None:
    _last_spoke.clear()
    _last_reply.clear()


def note_bot_spoke(bot_name: str, channel: str, now: float | None = None) -> None:
    _last_spoke[(bot_name, channel)] = time.time() if now is None else now


def note_replied(bot_name: str, channel: str, now: float | None = None) -> None:
    _last_reply[(bot_name, channel)] = time.time() if now is None else now


def is_pass(text: str) -> bool:
    return (text or "").strip().lower() in ("", "pass", "pass.")


def _keyword_score(message: str, persona_text: str) -> int:
    msg = {w for w in _words(message) if len(w) >= _MIN_PREFIX}
    persona = {w for w in _words(persona_text) if len(w) >= _MIN_PREFIX}
    return len(msg & persona)


def elect(hearers: list[dict], message: str, speaker: str, channel: str, *,
          get_familiarity, get_persona_text, recent_convo,
          now: float | None = None, rng: random.Random | None = None) -> list[dict]:
    """Tiered election. Named: guaranteed (no cap, no cooldown). Engaged: spoke in this
    channel recently or has an open convo with the speaker -> HEARD_ENGAGED_CHANCE.
    Candidate: top-2 by familiarity + persona keyword overlap (score > 0) ->
    HEARD_CANDIDATE_CHANCE. Non-named respect HEARD_MAX_RESPONDERS and HEARD_COOLDOWN_S."""
    now = time.time() if now is None else now
    rng = rng or random
    names = [h["bot_name"] for h in hearers]
    named = set(named_in(message, names))

    elected = [{"bot_name": n, "tier": "named"} for n in names if n in named]
    budget = max(0, HEARD_MAX_RESPONDERS - len(elected))

    def on_cooldown(b: str) -> bool:
        return now - _last_reply.get((b, channel), -1e18) < HEARD_COOLDOWN_S

    pool = [n for n in names if n not in named and not on_cooldown(n)]

    engaged = [b for b in pool
               if now - _last_spoke.get((b, channel), -1e18) <= HEARD_ENGAGED_WINDOW_S
               or recent_convo(b)]
    for b in engaged:
        if budget <= 0:
            break
        if rng.random() < HEARD_ENGAGED_CHANCE:
            elected.append({"bot_name": b, "tier": "engaged"})
            budget -= 1

    taken = {e["bot_name"] for e in elected}
    scored = sorted(((get_familiarity(b) + _keyword_score(message, get_persona_text(b)), b)
                     for b in pool if b not in taken), key=lambda t: -t[0])
    for score, b in scored[:2]:
        if budget <= 0 or score <= 0:
            break
        if rng.random() < HEARD_CANDIDATE_CHANCE:
            elected.append({"bot_name": b, "tier": "candidate"})
            budget -= 1

    return elected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_election.py -v`
Expected: 12 passed

- [ ] **Step 5: Run the whole suite (no regressions)**

Run: `venv/bin/python -m pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add election.py tests/test_election.py
git commit -m "feat(heard): election tiers (engaged/candidate), cap, cooldown"
```

---

### Task 3: Brain — `/heard` models, `run_chat` refactor with decline, LLM semaphore

**Files:**
- Modify: `models.py` (append)
- Modify: `main.py` (refactor `chat` body into `run_chat`)
- Modify: `llm.py` (semaphore)
- Create: `tests/test_heard_models.py`

**Interfaces:**
- Consumes: `election.is_pass` (Task 2).
- Produces: `models.HeardHearer{bot_name, distance=0.0, same_party=False, same_guild=False}`;
  `models.HeardRequest{speaker, channel="SAY", message, location=None, hearers=[]}`;
  `models.HeardReply(BotResponse + bot_name)`; `models.HeardResponse{responses: list[HeardReply]}`;
  `main.run_chat(req: ChatRequest, may_decline: bool = False) -> dict | None` (None = stayed silent;
  dict has keys `message, channel, emote, actions` exactly as today's `parse_response` output).

- [ ] **Step 1: Write the failing test**

```python
"""/heard wire models."""
from models import HeardHearer, HeardRequest, HeardReply, HeardResponse


def test_heard_request_defaults():
    req = HeardRequest(speaker="Abril", message="hi all",
                       hearers=[{"bot_name": "Vivi"}])
    assert req.channel == "SAY" and req.location is None
    assert req.hearers[0].distance == 0.0 and req.hearers[0].same_party is False


def test_heard_response_shape():
    r = HeardResponse(responses=[HeardReply(bot_name="Vivi", message="yo", channel="SAY")])
    d = r.model_dump()
    assert d["responses"][0]["bot_name"] == "Vivi"
    assert d["responses"][0]["emote"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_heard_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'HeardHearer'`

- [ ] **Step 3: Append models to `models.py`**

```python
class HeardHearer(BaseModel):
    bot_name: str
    distance: float = 0.0
    same_party: bool = False
    same_guild: bool = False


class HeardRequest(BaseModel):
    speaker: str
    channel: str = "SAY"
    message: str
    location: Optional[str] = None
    hearers: list[HeardHearer] = []


class HeardReply(BotResponse):
    bot_name: str


class HeardResponse(BaseModel):
    responses: list[HeardReply]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_heard_models.py -v`
Expected: 2 passed

- [ ] **Step 5: Refactor `main.chat` into `run_chat` (behavior-preserving + decline option)**

In `main.py`, rename the body of `chat()` to a new function and make the endpoint a wrapper.
The only new lines are marked `# NEW`; everything else is moved verbatim from today's `chat()`:

```python
from election import is_pass                                          # NEW (top of file)

async def run_chat(req: ChatRequest, may_decline: bool = False) -> dict | None:
    p = get_or_create_personality(req.bot_name)
    # ... [existing chat() body verbatim: rel, history, identity, mood, context,
    #      memory_section, caps, action_rules, system = CHAT_PROMPT.format(...)] ...

    if may_decline:                                                   # NEW
        system += ("\n\nThis message wasn't addressed to you. Reply ONLY if your character "
                   "genuinely has something to add. If not, reply with exactly: PASS")  # NEW

    raw = await call_ollama(system, [], req.message, num_predict=160, max_sentences=4)
    result = parse_response(raw, req.channel)

    if may_decline and is_pass(result["message"]):                    # NEW
        print(f"[heard] {req.bot_name} stayed silent")                # NEW
        return None                                                   # NEW

    # ... [existing logging, save_message x2, update_relationship, _maybe_reflect_self] ...
    return result


@app.post("/chat", response_model=BotResponse)
async def chat(req: ChatRequest):
    result = await run_chat(req)
    return BotResponse(**result)
```

- [ ] **Step 6: Add the global semaphore in `llm.py`**

At module level (after imports), and wrap the existing HTTP call inside `call_ollama`:

```python
from config import OLLAMA_URL, OLLAMA_MODEL, LLM_MAX_CONCURRENCY

_llm_sem = asyncio.Semaphore(LLM_MAX_CONCURRENCY)
```

Inside `call_ollama`, wrap the `client.post(...)` call:

```python
    async with _llm_sem:
        resp = await client.post(OLLAMA_URL, json={ ... })   # existing call, indented one level
```

(`llm.py` already imports `asyncio` or add `import asyncio` if missing. Keep every existing
parameter and the rest of the function untouched.)

- [ ] **Step 7: Run the whole suite (refactor must not regress)**

Run: `venv/bin/python -m pytest -q`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add models.py main.py llm.py tests/test_heard_models.py
git commit -m "feat(heard): wire models, run_chat refactor with PASS decline, LLM semaphore"
```

---

### Task 4: Brain — `POST /heard` endpoint

**Files:**
- Modify: `main.py`
- Create: `tests/test_heard_endpoint.py`

**Interfaces:**
- Consumes: `election.cap_hearers/elect/note_bot_spoke/note_replied` (Tasks 1–2),
  `main.run_chat` (Task 3), models (Task 3), `db.get_relationship`,
  `db.get_db` (for recent-convo check), `personality.get_or_create_personality`.
- Produces: `POST /heard` → `HeardResponse` — the JSON contract the C++ `PostHeard`
  (Task 5) parses: `{"responses":[{"bot_name","message","channel","emote","actions"},...]}`.

- [ ] **Step 1: Write the failing test**

```python
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
    async def fake_run_chat(req, may_decline=False):
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
    async def fake_run_chat(req, may_decline=False):
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
    async def fake_run_chat(req, may_decline=False):
        return {"message": "yo", "channel": req.channel, "emote": None, "actions": []}
    monkeypatch.setattr(main, "run_chat", fake_run_chat)
    monkeypatch.setattr(main, "_heard_familiarity", lambda s, b: 0)
    monkeypatch.setattr(main, "_heard_persona_text", lambda b: "")
    monkeypatch.setattr(main, "_heard_recent_convo", lambda s, b: False)

    client = TestClient(main.app)
    _post(client, "esterini hello", ["Esterini"])
    assert ("Esterini", "SAY") in election._last_reply
    assert ("Esterini", "SAY") in election._last_spoke
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_heard_endpoint.py -v`
Expected: FAIL (404 from TestClient — `/heard` route doesn't exist; `_heard_familiarity` missing)

- [ ] **Step 3: Implement the endpoint in `main.py`**

Add imports near the top:

```python
import election as election_mod
from election import cap_hearers, note_bot_spoke, note_replied
from models import HeardRequest, HeardReply, HeardResponse
from config import HEARD_CONVO_WINDOW_S
```

Add the DB-touching helpers (module level — kept separate so tests can monkeypatch them):

```python
def _heard_familiarity(speaker: str, bot_name: str) -> int:
    return get_relationship(bot_name, speaker).get("familiarity", 0)


def _heard_persona_text(bot_name: str) -> str:
    p = get_or_create_personality(bot_name)
    return f"{p.get('who', '')} {p.get('current_goal', '')}"


def _heard_recent_convo(speaker: str, bot_name: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM messages WHERE bot_name = ? AND player_name = ? "
        "AND created_at >= datetime('now', ?) LIMIT 1",
        (bot_name, speaker, f"-{HEARD_CONVO_WINDOW_S} seconds")).fetchone()
    conn.close()
    return row is not None
```

(Check the `messages` schema in `db.py` first: if the timestamp column is named something
other than `created_at`, use the actual column name.)

Add the endpoint:

```python
@app.post("/heard", response_model=HeardResponse)
async def heard(req: HeardRequest):
    hearers = cap_hearers([h.model_dump() for h in req.hearers], req.message)
    elected = election_mod.elect(
        hearers, req.message, req.speaker, req.channel,
        get_familiarity=lambda b: _heard_familiarity(req.speaker, b),
        get_persona_text=_heard_persona_text,
        recent_convo=lambda b: _heard_recent_convo(req.speaker, b),
    )
    if elected:
        print(f"[heard] {req.speaker} @{req.channel}: elected "
              f"{[(e['bot_name'], e['tier']) for e in elected]}")

    async def one(e):
        creq = ChatRequest(bot_name=e["bot_name"], player_name=req.speaker,
                           message=req.message, channel=req.channel, location=req.location)
        return e["bot_name"], await run_chat(creq, may_decline=(e["tier"] == "candidate"))

    results = await asyncio.gather(*(one(e) for e in elected))
    responses = []
    for bot_name, r in results:
        if r is None:
            continue
        note_replied(bot_name, req.channel)
        note_bot_spoke(bot_name, req.channel)
        responses.append(HeardReply(bot_name=bot_name, **r))
    return HeardResponse(responses=responses)
```

Also make ambient chatter count as "engaged": in the existing `tick()` endpoint, right after
`print(f"[tick] ...")`, add:

```python
    note_bot_spoke(req.bot_name, result["channel"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_heard_endpoint.py -v`
Expected: 3 passed

- [ ] **Step 5: Full suite + live smoke against the running brain**

Run: `venv/bin/python -m pytest -q`
Expected: all pass

Then (brain auto-reloads via `--reload`; it runs from this working tree):

```bash
curl -sS -X POST http://localhost:5000/heard -H 'Content-Type: application/json' \
  -d '{"speaker":"Abril","channel":"SAY","message":"esterini you there?","location":"Elwynn Forest","hearers":[{"bot_name":"Esterini"}]}'
```

Expected: JSON with one entry in `responses`, `bot_name: "Esterini"`, an in-character message
(takes 5–20s — real LLM call). Check `brain.log` shows `[heard] Abril @SAY: elected ...`.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_heard_endpoint.py
git commit -m "feat(heard): POST /heard endpoint — election + concurrent chat runs"
```

---

### Task 5: C++ — `LlmBridge::PostHeard` + multi-response parsing

**Files:**
- Modify: `src/Bot/LlmBridge.h` (repo `~/azerothcore/azerothcore-wotlk/modules/mod-playerbots`)
- Modify: `src/Bot/LlmBridge.cpp`

**Interfaces:**
- Consumes: `POST /heard` contract from Task 4.
- Produces: `struct HeardHearer { std::string botName; float distance; bool sameParty; bool sameGuild; };`
  `void LlmBridge::PostHeard(const std::string& speaker, const std::string& channel, const std::string& message, const std::string& location, const std::vector<HeardHearer>& hearers);`
  — used by Task 6. Replies enter the existing `responseQueue_` (no `PopResponse` changes).

- [ ] **Step 1: Extend `LlmBridge.h`**

After the `LlmAction` struct, add:

```cpp
struct HeardHearer
{
    std::string botName;
    float distance = 0.0f;
    bool sameParty = false;
    bool sameGuild = false;
};
```

In the public section, after `PostTick(...)`, add:

```cpp
    // Fire-and-forget: POST /heard — one event per player message, roster of hearing bots.
    // Response body carries ALL elected replies; each is queued for PopResponse.
    void PostHeard(const std::string& speaker, const std::string& channel,
                   const std::string& message, const std::string& location,
                   const std::vector<HeardHearer>& hearers);
```

Change the private `HttpPost` declaration to take a timeout:

```cpp
    std::string HttpPost(const std::string& path, const std::string& jsonBody,
                         uint32_t timeoutSecs = 30);
```

- [ ] **Step 2: Update `HttpPost` in `LlmBridge.cpp`**

Change the signature to match, and replace the fixed expiry line:

```cpp
std::string LlmBridge::HttpPost(const std::string& path, const std::string& jsonBody,
                                 uint32_t timeoutSecs)
```

```cpp
        stream.expires_after(std::chrono::seconds(timeoutSecs));
```

- [ ] **Step 3: Add a string-safe object-array extractor in `LlmBridge.cpp`**

`JsonExtractActions`' naive `find('}')` can't handle nested objects; replies contain nested
`actions` arrays and free-text messages. Add below `JsonExtractActions` (file-static):

```cpp
// Extract each top-level object of the array under `key`, brace-depth aware and
// string-aware (braces/brackets inside JSON strings are ignored).
static std::vector<std::string> JsonExtractObjectArray(const std::string& json,
                                                       const std::string& key)
{
    std::vector<std::string> objects;
    std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos)
        return objects;
    pos = json.find('[', pos + needle.size());
    if (pos == std::string::npos)
        return objects;

    int depth = 0;
    bool inString = false;
    size_t objStart = 0;
    for (size_t i = pos + 1; i < json.size(); ++i)
    {
        char c = json[i];
        if (inString)
        {
            if (c == '\\') { ++i; continue; }
            if (c == '"') inString = false;
            continue;
        }
        if (c == '"') { inString = true; continue; }
        if (c == '{')
        {
            if (depth == 0) objStart = i;
            ++depth;
        }
        else if (c == '}')
        {
            --depth;
            if (depth == 0)
                objects.push_back(json.substr(objStart, i - objStart + 1));
        }
        else if (c == ']' && depth == 0)
            break;
    }
    return objects;
}
```

- [ ] **Step 4: Implement `PostHeard` in `LlmBridge.cpp`**

Add after `PostTick`:

```cpp
void LlmBridge::PostHeard(const std::string& speaker, const std::string& channel,
                           const std::string& message, const std::string& location,
                           const std::vector<HeardHearer>& hearers)
{
    if (!enabled_ || hearers.empty())
        return;

    // Serialize the roster on the caller's thread (Player pointers must not cross threads).
    std::ostringstream hearersJson;
    hearersJson << "[";
    for (size_t i = 0; i < hearers.size(); ++i)
    {
        if (i) hearersJson << ",";
        hearersJson << "{\"bot_name\":\"" << hearers[i].botName << "\""
                    << ",\"distance\":" << hearers[i].distance
                    << ",\"same_party\":" << (hearers[i].sameParty ? "true" : "false")
                    << ",\"same_guild\":" << (hearers[i].sameGuild ? "true" : "false") << "}";
    }
    hearersJson << "]";
    std::string hearersArr = hearersJson.str();

    std::thread([this, speaker, channel, message, location, hearersArr]()
    {
        // BuildJson escapes speaker/message/location; hearers array appended raw
        // (bot names come from the server, not from user input).
        std::string base = BuildJson({
            {"speaker", speaker},
            {"channel", channel},
            {"message", message},
            {"location", location}
        });
        base.pop_back();  // strip trailing '}'
        std::string json = base + ",\"hearers\":" + hearersArr + "}";

        // Up to HEARD_MAX_RESPONDERS LLM calls behind the brain's semaphore.
        std::string responseJson = HttpPost("/heard", json, 75);
        if (responseJson.empty())
            return;

        for (const std::string& obj : JsonExtractObjectArray(responseJson, "responses"))
        {
            std::string botName = JsonExtractString(obj, "bot_name");
            if (botName.empty())
                continue;
            LlmResponse resp = ParseResponse(obj, botName, speaker);
            if (resp.message.empty())
                continue;
            std::lock_guard<std::mutex> lock(responseMutex_);
            responseQueue_.push(std::move(resp));
            LOG_INFO("playerbots", "LlmBridge: queued heard-reply for {} in {}", botName, channel);
        }
    }).detach();
}
```

- [ ] **Step 5: Syntax-check the module sources (no full build yet)**

```bash
cd ~/azerothcore/azerothcore-wotlk/modules/mod-playerbots
g++ -std=c++20 -fsyntax-only -I src -I src/Bot src/Bot/LlmBridge.cpp 2>&1 | head -20
```

Expected: errors ONLY about missing AzerothCore headers (`Log.h` etc.) are acceptable if g++
can't find them — in that case skip this step; the real gate is the image build in Task 7.
No errors mentioning `PostHeard`, `JsonExtractObjectArray`, or `HeardHearer`.

- [ ] **Step 6: Commit**

```bash
git add src/Bot/LlmBridge.h src/Bot/LlmBridge.cpp
git commit -m "feat(LlmBridge): PostHeard — one heard-event per message, multi-reply parse"
```

---

### Task 6: C++ — rewire chat hooks to PostHeard (say/yell, channels; add party, guild)

**Files:**
- Modify: `src/Script/Playerbots.cpp:229-247` (group overload), `:249-273` (guild overload),
  `:276-331` (say/yell overload), `:333-386` (channel overload)

**Interfaces:**
- Consumes: `LlmBridge::PostHeard` + `HeardHearer` (Task 5); existing
  `PlayerbotsMgr::instance().GetPlayerbotAI(...)`, `sConfigMgr` (`Config.h`),
  `ObjectAccessor::GetPlayers()` (`ObjectAccessor.h`).
- Produces: nothing new for later tasks — this is the last code task.

- [ ] **Step 1: Add shared helpers near the top of the hook section**

Confirm `#include "Config.h"` and `#include "ObjectAccessor.h"` are present in
`Playerbots.cpp` includes (add if missing). Then add file-static helpers above the
`OnPlayerCanUseChat` overloads:

```cpp
static bool LlmHeardEnabled()
{
    return sLlmBridge.IsEnabled() &&
           sConfigMgr->GetOption<bool>("AiPlayerbot.LlmHeardEnabled", true);
}

static std::string LlmZoneName(Player* player)
{
    if (!player->GetMap())
        return "";
    if (AreaTableEntry const* zone = sAreaTableStore.LookupEntry(
            player->GetMap()->GetZoneId(player->GetPhaseMask(),
                player->GetPositionX(), player->GetPositionY(), player->GetPositionZ())))
        return zone->area_name[sWorld->GetDefaultDbcLocale()];
    return "";
}
```

- [ ] **Step 2: Rewrite the say/yell overload's LLM block**

In `OnPlayerCanUseChat(Player* player, uint32 type, uint32, std::string& msg)` (line ~276),
replace everything from `// Only pick ONE random nearby bot to respond` through the
closing brace of the `if (!nearbyBots.empty())` block (lines ~304-328) with:

```cpp
        std::vector<HeardHearer> hearers;
        for (auto& ref : player->GetMap()->GetPlayers())
        {
            Player* other = ref.GetSource();
            if (!other || other == player)
                continue;
            if (!PlayerbotsMgr::instance().GetPlayerbotAI(other))
                continue;
            float dist = player->GetDistance(other);
            if (dist <= range)
                hearers.push_back({other->GetName(), dist, false, false});
        }
        sLlmBridge.PostHeard(playerName, channelStr, msg, location, hearers);
```

And change the early `if (!sLlmBridge.IsEnabled())` gate at the top of this overload to
`if (!LlmHeardEnabled())`.

- [ ] **Step 3: Rewrite the channel overload's LLM block**

In the `Channel*` overload (line ~333): change the gate
`if (sLlmBridge.IsEnabled() && !PlayerbotsMgr...)` to
`if (LlmHeardEnabled() && !PlayerbotsMgr::instance().GetPlayerbotAI(player))`, keep the
channel-name mapping, and replace everything from `// ~20% chance a bot responds...`
(`if (urand(0, 99) < 20)` through its closing brace, lines ~352-382) with:

```cpp
            std::string playerName = player->GetName();
            std::string location = LlmZoneName(player);
            std::vector<HeardHearer> hearers;
            for (auto& ref : player->GetMap()->GetPlayers())
            {
                Player* other = ref.GetSource();
                if (!other || other == player)
                    continue;
                if (!PlayerbotsMgr::instance().GetPlayerbotAI(other))
                    continue;
                hearers.push_back({other->GetName(), player->GetDistance(other), false, false});
            }
            sLlmBridge.PostHeard(playerName, channelStr, msg, location, hearers);
```

(Zone-scoped hearers, same as the old behavior; the brain caps the roster at 30 by nearest.)

- [ ] **Step 4: Add the LLM block to the group overload**

In `OnPlayerCanUseChat(..., Group* group)` (line ~229), after the existing
`HandleCommand` member loop, add:

```cpp
        if (LlmHeardEnabled() && (type == CHAT_MSG_PARTY || type == CHAT_MSG_RAID) &&
            !PlayerbotsMgr::instance().GetPlayerbotAI(player))
        {
            std::vector<HeardHearer> hearers;
            for (GroupReference* itr = group->GetFirstMember(); itr != nullptr; itr = itr->next())
            {
                Player* const member = itr->GetSource();
                if (!member || member == player)
                    continue;
                if (!PlayerbotsMgr::instance().GetPlayerbotAI(member))
                    continue;
                float dist = member->GetMap() == player->GetMap()
                                 ? player->GetDistance(member) : 0.0f;
                hearers.push_back({member->GetName(), dist, true, false});
            }
            sLlmBridge.PostHeard(player->GetName(), "PARTY", msg, LlmZoneName(player), hearers);
        }
```

- [ ] **Step 5: Add the LLM block to the guild overload**

In `OnPlayerCanUseChat(..., Guild* guild)` (line ~249) — first change the ignored parameter
name from `Guild* /*guild*/` to `Guild* guild` if needed (check the actual signature at the
line; the current code shows `Guild* /*guild*/`). Add before the final `return true;`:

```cpp
        if (LlmHeardEnabled() && !PlayerbotsMgr::instance().GetPlayerbotAI(player))
        {
            std::vector<HeardHearer> hearers;
            for (auto const& itr : ObjectAccessor::GetPlayers())
            {
                Player* other = itr.second;
                if (!other || other == player || !other->IsInWorld())
                    continue;
                if (other->GetGuildId() != player->GetGuildId())
                    continue;
                if (!PlayerbotsMgr::instance().GetPlayerbotAI(other))
                    continue;
                hearers.push_back({other->GetName(), 0.0f, false, true});
            }
            sLlmBridge.PostHeard(player->GetName(), "GUILD", msg, LlmZoneName(player), hearers);
        }
```

- [ ] **Step 6: Commit**

```bash
cd ~/azerothcore/azerothcore-wotlk/modules/mod-playerbots
git add src/Script/Playerbots.cpp
git commit -m "feat(heard): route say/yell/party/guild/channel chat through PostHeard election"
```

---

### Task 7: Deploy — rebuild worldserver image, recreate, live checklist

**Files:** none created — build + verify.

**Interfaces:**
- Consumes: all previous tasks; `docker-compose.override.yml` already carries
  `AC_AI_PLAYERBOT_RANDOM_BOT_ACCOUNT_COUNT: "170"` (uncommitted earlier fix — commit it here).

- [ ] **Step 1: Commit the pending compose fix in the core repo**

```bash
cd ~/azerothcore/azerothcore-wotlk
git add docker-compose.override.yml
git commit -m "conf: RandomBotAccountCount 150->170 (7 accounts short at MaxRandomBots=150)"
```

- [ ] **Step 2: Rebuild the worldserver image (long — run in background, possibly hours)**

```bash
cd ~/azerothcore/azerothcore-wotlk
docker compose build ac-worldserver
```

Expected: image builds cleanly. Compile errors here bounce back to Task 5/6.

- [ ] **Step 3: Warn the user, then recreate the container (kicks players ~2 min)**

Ask the user before this step if they may be logged in.

```bash
docker compose up -d ac-worldserver
docker logs -f ac-worldserver 2>&1 | grep -m1 "worldserver-daemon) ready"
```

Expected: `AzerothCore rev. ... (worldserver-daemon) ready...`

- [ ] **Step 4: Live checklist (user in-game; watch `brain.log` + worldserver logs)**

In a terminal: `tail -f ~/wow-bot-brain/brain.log` and
`docker logs -f ac-worldserver 2>&1 | grep -i llmbridge`. Verify with the user:

1. Whisper a bot → reply arrives (regression check; `[chat]` in brain.log).
2. `/say` near bots naming one ("esterini …") → that bot answers (`[heard] ... elected [('Esterini', 'named')]`).
3. `/say` near bots without naming → sometimes an answer, never more than 2.
4. Trade channel message naming a bot → named bot answers in Trade.
5. Party with a bot, party chat → bot answers in party.
6. Repeat the same /say twice within 30s → second time the same non-named bot does NOT answer (cooldown).
7. Ask Esterini (whisper) to guild-invite you → `LlmBridge: ... guild-invited ...` in logs and an in-game invite (needs `WBB_GUILD_ACTIONS=1` on the brain — export it in the brain's environment if unset, it's checked at request time).
8. `AiPlayerbot.LlmHeardEnabled` kill switch: `AC_AI_PLAYERBOT_LLM_HEARD_ENABLED=0` documented as rollback (no need to exercise live unless something misbehaves).

- [ ] **Step 5: Push both repos to the private mirrors**

```bash
cd ~/azerothcore/azerothcore-wotlk/modules/mod-playerbots && git push personal master
cd ~/wow-bot-brain && git push origin evolution-council 2>/dev/null || true
```

(wow-bot-brain has no `personal` remote — check `git remote -v`; if none, skip the push and
tell the user.)

---

## Self-review notes

- **Spec coverage:** channels (T6), tiers/caps/cooldowns (T2), stay-silent (T3), semaphore (T3),
  roster cap (T1/T4), sync response contract (T4/T5), kill switch (T6), whisper untouched
  (no task modifies the whisper path), guildinvite + account-count ship via rebuild (T7),
  manual checklist (T7). Engaged "recent convo" uses `messages` timestamps (T4 — column name
  verified against `db.py` at implementation time, flagged in the step).
- **Type consistency:** hearer dict/model field names (`bot_name/distance/same_party/same_guild`)
  identical across election.py, models.py, endpoint, and C++ JSON. `run_chat -> dict | None`
  consumed as such in T4. `HttpPost(path, body, timeoutSecs)` default 30 keeps /chat & /tick
  call sites valid.
- **Known judgment calls:** party/raid both map to channel string `PARTY` (PopResponse routes
  PARTY → `SayToParty`, correct for both); guild roster iterates online players via
  `ObjectAccessor::GetPlayers()` (cross-map, no distance).
