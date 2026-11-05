# Chatter Diversity + Heard-Model Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ambient bot chatter read as many distinct people (not one model repeating itself) and let player-facing `/heard` replies run on a stronger, separately-configurable model — all brain-only, no worldserver rebuild.

**Architecture:** Three independent levers on the existing LLM path in `wow-bot-brain`. (1) Sampling: `call_ollama` gains config-driven anti-repetition knobs (`repeat_penalty`, `min_p`, `top_p`, `repeat_last_n`) instead of only `temperature`. (2) Model routing: `call_ollama` resolves its model from the `lane` — the `heard` lane uses `OLLAMA_HEARD_MODEL` (defaults to the base model, so no behavior change until set). (3) Fleet dedup: `election.py` keeps a short in-memory window of recently-emitted lines fleet-wide; `tick()` and the `heard` lane of `run_chat()` re-roll once when a generated line is too similar to a recent one. Direct `/chat` whispers are left byte-for-byte unchanged.

**Tech Stack:** Python 3.12, FastAPI + Pydantic, httpx → Ollama `/api/chat`. Tests: `venv/bin/python -m pytest -q`. Stdlib only — no new dependencies.

## Global Constraints

- **Brain-only.** Every change is in `~/wow-bot-brain` on branch `evolution-council`. It hot-reloads under uvicorn `--reload`; **no worldserver image rebuild** is involved.
- **Backward-compatible defaults.** `OLLAMA_HEARD_MODEL` defaults to `OLLAMA_MODEL` — routing is a no-op until the operator sets the env var. Sampling defaults intentionally enable *modest* anti-repetition (this changes output character on purpose — that is the point of the slice — but `temperature` stays `0.9`).
- **`/chat` (direct whispers) is untouched.** Fleet dedup applies only to ambient `tick()` and the `heard` lane of `run_chat()`. A direct whisper (`lane == "default"`) must produce byte-for-byte the current behavior.
- **All new tunables are env-overridable config constants** (so they can be tuned and A/B'd via the existing `model=` eval harness without code edits). Read from `os.getenv` with the documented default.
- **In-memory state, resets on restart** — matches the existing `election.py` recency-state pattern (`_last_spoke`/`_last_reply`). Worst case on restart is a brief dedup-window warm-up. Every test that touches election state calls `election.reset_state()` in setup to avoid cross-test pollution.
- **Ollama ignores unknown `options` keys** — safe to send sampling knobs the backend model may not use.
- Interfaces to keep stable: `call_ollama(system_prompt, history, user_message, *, num_predict=50, max_sentences=2, model=None, lane="default")`; `parse_response(raw, incoming_channel)`; `election.reset_state()`.

---

### Task 1: Config-driven sampling knobs in call_ollama (anti-repetition)

**Files:**
- Modify: `config.py` (append sampling constants)
- Modify: `llm.py` (add `build_llm_options`, use it in `call_ollama`)
- Test: `tests/test_llm_options.py` (create)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `build_llm_options(num_predict: int) -> dict` in `llm.py`, returning the Ollama `options` dict. Used only inside `call_ollama`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm_options.py`:

```python
from llm import build_llm_options


def test_options_carry_num_predict_and_temperature():
    opts = build_llm_options(50)
    assert opts["num_predict"] == 50
    assert opts["temperature"] == 0.9  # preserved from the pre-slice behavior


def test_options_include_antirepetition_knobs():
    opts = build_llm_options(160)
    assert opts["repeat_penalty"] >= 1.1          # punishes recycled phrasing
    assert 0.0 < opts["min_p"] < 1.0              # tail cutoff for coherence
    assert 0.0 < opts["top_p"] <= 1.0
    assert opts["repeat_last_n"] >= 64            # window the penalty looks back over
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_llm_options.py -q`
Expected: FAIL (`cannot import name 'build_llm_options' from 'llm'`).

- [ ] **Step 3: Add the config constants**

In `config.py`, append (after the `OLLAMA_MODEL` line region is fine; keep near the top LLM config):

```python
# ── LLM sampling (anti-repetition; env-overridable for tuning + A/B) ─────────
LLM_TEMPERATURE = float(os.getenv("WBB_LLM_TEMPERATURE", "0.9"))
LLM_TOP_P = float(os.getenv("WBB_LLM_TOP_P", "0.9"))
LLM_MIN_P = float(os.getenv("WBB_LLM_MIN_P", "0.05"))
LLM_REPEAT_PENALTY = float(os.getenv("WBB_LLM_REPEAT_PENALTY", "1.2"))
LLM_REPEAT_LAST_N = int(os.getenv("WBB_LLM_REPEAT_LAST_N", "256"))
```

- [ ] **Step 4: Add `build_llm_options` and wire it into `call_ollama`**

In `llm.py`, update the config import line to add the new names:

```python
from config import (OLLAMA_URL, OLLAMA_MODEL, LLM_MAX_CONCURRENCY, LLM_HEARD_CONCURRENCY,
                    LLM_TEMPERATURE, LLM_TOP_P, LLM_MIN_P, LLM_REPEAT_PENALTY,
                    LLM_REPEAT_LAST_N)
```

Add this module-level function (place it just above `call_ollama`):

```python
def build_llm_options(num_predict: int) -> dict:
    """Ollama sampling options. Anti-repetition knobs (repeat_penalty/min_p) fight the
    fleet-wide sameness that makes ambient chatter read as one bot. All values come from
    config so they can be tuned via env and A/B'd without code changes."""
    return {
        "num_predict": num_predict,
        "temperature": LLM_TEMPERATURE,
        "top_p": LLM_TOP_P,
        "min_p": LLM_MIN_P,
        "repeat_penalty": LLM_REPEAT_PENALTY,
        "repeat_last_n": LLM_REPEAT_LAST_N,
    }
```

In `call_ollama`, replace the inline `"options": {...}` with:

```python
                "options": build_llm_options(num_predict),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_llm_options.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `venv/bin/python -m pytest -q`
Expected: PASS — existing tests mock/replace `call_ollama` or don't hit Ollama, so the new options are transparent. Two pre-existing FastAPI `on_event` deprecation warnings are expected; no new warnings.

- [ ] **Step 7: Commit**

```bash
git add config.py llm.py tests/test_llm_options.py
git commit -m "feat(chatter): config-driven anti-repetition sampling knobs"
```

---

### Task 2: Lane-aware model routing (/heard can use a stronger model)

**Files:**
- Modify: `config.py` (add `OLLAMA_HEARD_MODEL`)
- Modify: `llm.py` (add `pick_model`, use it in `call_ollama`)
- Test: `tests/test_llm_model_routing.py` (create)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `pick_model(model: str | None, lane: str) -> str` in `llm.py`. `call_ollama` uses it, so no call-site changes are needed — the existing `lane="heard"` flowing into `run_chat`'s `call_ollama` automatically selects the heard model.

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm_model_routing.py`:

```python
import importlib


def test_default_lane_uses_base_model(monkeypatch):
    monkeypatch.setenv("WBB_OLLAMA_MODEL", "base-model")
    monkeypatch.delenv("WBB_OLLAMA_HEARD_MODEL", raising=False)
    import config, llm
    importlib.reload(config); importlib.reload(llm)
    assert llm.pick_model(None, "default") == "base-model"
    # heard defaults to the base model when its own env is unset (backward-compatible)
    assert llm.pick_model(None, "heard") == "base-model"


def test_heard_lane_uses_heard_model_when_set(monkeypatch):
    monkeypatch.setenv("WBB_OLLAMA_MODEL", "base-model")
    monkeypatch.setenv("WBB_OLLAMA_HEARD_MODEL", "big-model")
    import config, llm
    importlib.reload(config); importlib.reload(llm)
    assert llm.pick_model(None, "heard") == "big-model"
    assert llm.pick_model(None, "default") == "base-model"


def test_explicit_model_arg_always_wins(monkeypatch):
    # the A/B harness passes model= explicitly; that must override lane routing
    import llm
    assert llm.pick_model("ab-candidate", "heard") == "ab-candidate"
    assert llm.pick_model("ab-candidate", "default") == "ab-candidate"
```

> Note for the implementer: reload the config/llm modules AFTER importlib.reload above so any earlier import in this task's process doesn't pin stale env. Add `importlib.reload(config); importlib.reload(llm)` at the end of the third test's setup too if it runs after a reload — or keep the tests order-independent as written (the third test doesn't depend on env).

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_llm_model_routing.py -q`
Expected: FAIL (`cannot import name 'pick_model' from 'llm'`).

- [ ] **Step 3: Add the config constant**

In `config.py`, right after the `OLLAMA_MODEL` line:

```python
OLLAMA_HEARD_MODEL = os.getenv("WBB_OLLAMA_HEARD_MODEL", OLLAMA_MODEL)
```

- [ ] **Step 4: Add `pick_model` and wire it into `call_ollama`**

In `llm.py`, add `OLLAMA_HEARD_MODEL` to the config import, then add:

```python
def pick_model(model: str | None, lane: str) -> str:
    """Explicit model (from the A/B harness) always wins. Otherwise the heard lane —
    the player-facing replies people actually read — gets OLLAMA_HEARD_MODEL, which
    defaults to the base model so this is a no-op until an operator sets it."""
    if model:
        return model
    return OLLAMA_HEARD_MODEL if lane == "heard" else OLLAMA_MODEL
```

In `call_ollama`, change the model field:

```python
                "model": pick_model(model, lane),
```

(Remove the old `model or OLLAMA_MODEL` expression — `pick_model` subsumes it.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_llm_model_routing.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Run the full suite**

Run: `venv/bin/python -m pytest -q`
Expected: PASS, no new warnings.

- [ ] **Step 7: Commit**

```bash
git add config.py llm.py tests/test_llm_model_routing.py
git commit -m "feat(chatter): lane-aware model routing (configurable /heard model)"
```

---

### Task 3: Fleet-wide recent-line dedup state in election.py

**Files:**
- Modify: `config.py` (dedup constants)
- Modify: `election.py` (state, `note_fleet_line`, `is_duplicate_line`, clear in `reset_state`)
- Test: `tests/test_fleet_dedup.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `note_fleet_line(text: str, now: float | None = None) -> None` and `is_duplicate_line(text: str, now: float | None = None) -> bool` in `election.py`. Consumed by Task 4. `reset_state()` also clears the new state.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fleet_dedup.py`:

```python
import election


def setup_function():
    election.reset_state()


def test_exact_repeat_is_duplicate():
    election.note_fleet_line("anyone up for Deadmines?", now=100.0)
    assert election.is_duplicate_line("Anyone up for Deadmines?", now=101.0) is True


def test_distinct_line_is_not_duplicate():
    election.note_fleet_line("anyone up for Deadmines?", now=100.0)
    assert election.is_duplicate_line("this kobold nearly had me, close one", now=101.0) is False


def test_high_overlap_is_duplicate():
    election.note_fleet_line("lf healer for deadmines run", now=100.0)
    # same request, trivially reworded -> high token overlap
    assert election.is_duplicate_line("lf a healer for deadmines run pls", now=101.0) is True


def test_expired_lines_do_not_count():
    election.note_fleet_line("anyone up for Deadmines?", now=100.0)
    # beyond the window -> no longer compared
    assert election.is_duplicate_line("anyone up for Deadmines?", now=100.0 + 10_000) is False


def test_empty_text_is_never_duplicate():
    election.note_fleet_line("", now=100.0)
    assert election.is_duplicate_line("", now=101.0) is False


def test_reset_state_clears_fleet_window():
    election.note_fleet_line("anyone up for Deadmines?", now=100.0)
    election.reset_state()
    assert election.is_duplicate_line("anyone up for Deadmines?", now=101.0) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_fleet_dedup.py -q`
Expected: FAIL (`module 'election' has no attribute 'note_fleet_line'`).

- [ ] **Step 3: Add the config constants**

In `config.py`, append:

```python
# ── fleet-wide anti-repetition (ambient chatter dedup) ──────────────────────
FLEET_DEDUP_WINDOW_S = int(os.getenv("WBB_FLEET_DEDUP_WINDOW_S", "180"))
FLEET_DEDUP_MAXLEN = int(os.getenv("WBB_FLEET_DEDUP_MAXLEN", "200"))
FLEET_DEDUP_THRESHOLD = float(os.getenv("WBB_FLEET_DEDUP_THRESHOLD", "0.6"))
```

- [ ] **Step 4: Add the dedup state and functions**

In `election.py`: add `from collections import deque` at the top (alongside the existing imports), and add the config names to the existing `from config import (...)` block:

```python
from config import (HEARD_ENGAGED_WINDOW_S, HEARD_CONVO_WINDOW_S, HEARD_ENGAGED_CHANCE,
                    HEARD_CANDIDATE_CHANCE, HEARD_MAX_RESPONDERS, HEARD_COOLDOWN_S,
                    HEARD_MAX_HEARERS, HEARD_MAX_NAMED,
                    FLEET_DEDUP_WINDOW_S, FLEET_DEDUP_MAXLEN, FLEET_DEDUP_THRESHOLD)
```

Extend the recency-state section (right after `_last_reply` is declared):

```python
# Fleet-wide window of recently-emitted lines (token sets + timestamps) so 150 bots
# don't converge on the same phrasing. In-memory, bounded, resets on restart.
_fleet_lines: deque = deque(maxlen=FLEET_DEDUP_MAXLEN)   # (ts, frozenset[str])
```

Update `reset_state`:

```python
def reset_state() -> None:
    _last_spoke.clear()
    _last_reply.clear()
    _fleet_lines.clear()
```

Add the two functions (reusing the existing `_words` tokenizer):

```python
def _line_tokens(text: str) -> frozenset:
    return frozenset(_words(text))


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def note_fleet_line(text: str, now: float | None = None) -> None:
    """Record an emitted ambient line for cross-bot dedup."""
    toks = _line_tokens(text)
    if toks:
        _fleet_lines.append((time.time() if now is None else now, toks))


def is_duplicate_line(text: str, now: float | None = None) -> bool:
    """True if `text` closely matches a still-fresh fleet line (token Jaccard >= threshold)."""
    toks = _line_tokens(text)
    if not toks:
        return False
    now = time.time() if now is None else now
    for ts, prev in _fleet_lines:
        if now - ts > FLEET_DEDUP_WINDOW_S:
            continue
        if _jaccard(toks, prev) >= FLEET_DEDUP_THRESHOLD:
            return True
    return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_fleet_dedup.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Run the full suite**

Run: `venv/bin/python -m pytest -q`
Expected: PASS, no new warnings.

- [ ] **Step 7: Commit**

```bash
git add config.py election.py tests/test_fleet_dedup.py
git commit -m "feat(chatter): fleet-wide recent-line dedup state (token Jaccard, TTL window)"
```

---

### Task 4: Wire dedup + one re-roll into tick() and the heard lane

**Files:**
- Modify: `main.py` (import the dedup fns; add `FRESH_NUDGE` + `generate_deduped`; wire `tick()` and `run_chat()`)
- Test: `tests/test_dedup_wiring.py` (create)

**Interfaces:**
- Consumes: `election.is_duplicate_line`, `election.note_fleet_line` (Task 3).
- Produces: `generate_deduped(gen, *, dedupe, allow_silence=False, decline=None)` in `main.py` — a pure async orchestrator that generates a line, optionally re-rolls once on a fleet duplicate, records the emitted line, and can return `None`. Used by both `tick()` and `run_chat()`.

**Design note (intentional):** `generate_deduped` is the single tested seam. `gen` is an `async` callable `gen(extra_system: str) -> dict` that runs one `call_ollama` + `parse_response`; the caller injects its own prompt/params via the closure. This keeps DB and HTTP out of the helper's tests. The `decline` hook folds in `run_chat`'s existing PASS behavior so both concerns compose in one place.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dedup_wiring.py`:

```python
import asyncio

import election
import main


def setup_function():
    election.reset_state()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_dedupe_rerolls_once_on_duplicate_then_emits_fresh():
    # Seed the fleet window with a line the first generation will collide with.
    election.note_fleet_line("anyone up for Deadmines?", now=1.0)
    calls = []

    async def gen(extra):
        calls.append(extra)
        # first call returns the duplicate; the re-roll (extra != "") returns something fresh
        msg = "this fight is brutal, low hp" if extra else "anyone up for Deadmines?"
        return {"message": msg, "channel": "SAY", "emote": None, "actions": []}

    result = _run(main.generate_deduped(gen, dedupe=True))
    assert result["message"] == "this fight is brutal, low hp"
    assert len(calls) == 2                      # re-rolled exactly once
    assert calls[1] == main.FRESH_NUDGE          # re-roll carried the nudge
    assert election.is_duplicate_line("this fight is brutal, low hp", now=2.0)  # recorded


def test_no_reroll_when_line_is_novel():
    calls = []

    async def gen(extra):
        calls.append(extra)
        return {"message": "the road to Westfall is long", "channel": "SAY",
                "emote": None, "actions": []}

    result = _run(main.generate_deduped(gen, dedupe=True))
    assert result["message"] == "the road to Westfall is long"
    assert len(calls) == 1                        # no duplicate -> no re-roll


def test_dedupe_false_never_rerolls_or_records():
    election.note_fleet_line("anyone up for Deadmines?", now=1.0)
    calls = []

    async def gen(extra):
        calls.append(extra)
        return {"message": "anyone up for Deadmines?", "channel": "SAY",
                "emote": None, "actions": []}

    result = _run(main.generate_deduped(gen, dedupe=False))
    assert result["message"] == "anyone up for Deadmines?"
    assert len(calls) == 1                        # dedupe off (e.g. direct /chat)
    # not recorded into the fleet window
    election.reset_state()
    assert not election.is_duplicate_line("anyone up for Deadmines?", now=2.0)


def test_decline_short_circuits_to_none():
    async def gen(extra):
        return {"message": "PASS", "channel": "SAY", "emote": None, "actions": []}

    result = _run(main.generate_deduped(
        gen, dedupe=True, decline=lambda r: r["message"] == "PASS"))
    assert result is None


def test_persistent_duplicate_with_allow_silence_returns_none():
    election.note_fleet_line("anyone up for Deadmines?", now=1.0)

    async def gen(extra):
        return {"message": "anyone up for Deadmines?", "channel": "SAY",
                "emote": None, "actions": []}   # always the duplicate

    result = _run(main.generate_deduped(gen, dedupe=True, allow_silence=True))
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_dedup_wiring.py -q`
Expected: FAIL (`module 'main' has no attribute 'generate_deduped'`).

- [ ] **Step 3: Add the import, `FRESH_NUDGE`, and `generate_deduped` to main.py**

In `main.py`, extend the existing election import (currently `from election import is_pass, cap_hearers, note_bot_spoke, note_replied`):

```python
from election import (is_pass, cap_hearers, note_bot_spoke, note_replied,
                      is_duplicate_line, note_fleet_line)
```

Add near the top of `main.py` (module level, after imports):

```python
FRESH_NUDGE = ("\n\nSay something clearly different from what everyone else is saying — "
               "your own wording and angle, not the usual phrasing.")


async def generate_deduped(gen, *, dedupe: bool, allow_silence: bool = False, decline=None):
    """Generate one line via `gen("")`. If `decline` fires on it, return None. When
    `dedupe` is on and the line duplicates a recent fleet line, re-roll once with
    FRESH_NUDGE; if the re-roll is still a duplicate and `allow_silence`, return None.
    Records the finally-emitted line in the fleet window (only when `dedupe`)."""
    result = await gen("")
    if decline is not None and decline(result):
        return None
    if dedupe and result.get("message") and is_duplicate_line(result["message"]):
        result = await gen(FRESH_NUDGE)
        if allow_silence and result.get("message") and is_duplicate_line(result["message"]):
            return None
    if dedupe and result and result.get("message"):
        note_fleet_line(result["message"])
    return result
```

- [ ] **Step 4: Wire `tick()`**

In `tick()`, replace the current generation block:

```python
    # Ambient broadcast stays tight — one short line.
    raw = await call_ollama(system, [], activity["prompt"], num_predict=50, max_sentences=2)
    result = parse_response(raw, activity["channel"])
    result["channel"] = activity["channel"]
```

with:

```python
    # Ambient broadcast stays tight — one short line, de-duplicated across the fleet.
    async def gen(extra):
        raw = await call_ollama(system + extra, [], activity["prompt"],
                                num_predict=50, max_sentences=2)
        return parse_response(raw, activity["channel"])

    result = await generate_deduped(gen, dedupe=True)
    result["channel"] = activity["channel"]
```

(Leave the `print(...)` and `note_bot_spoke(...)` lines below unchanged.)

- [ ] **Step 5: Wire the heard lane in `run_chat()`**

In `run_chat()`, replace the current tail generation + PASS block:

```python
    raw = await call_ollama(system, [], req.message, num_predict=160, max_sentences=4, lane=lane)
    result = parse_response(raw, req.channel)

    if may_decline and is_pass(result["message"]):                    # NEW
        print(f"[heard] {req.bot_name} stayed silent")                # NEW
        return None                                                   # NEW
```

with:

```python
    async def gen(extra):
        raw = await call_ollama(system + extra, [], req.message,
                                num_predict=160, max_sentences=4, lane=lane)
        return parse_response(raw, req.channel)

    # Fleet dedup applies to ambient overheard replies (heard lane), not direct whispers.
    result = await generate_deduped(
        gen, dedupe=(lane == "heard"),
        decline=(lambda r: is_pass(r["message"])) if may_decline else None)

    if result is None:
        print(f"[heard] {req.bot_name} stayed silent")
        return None
```

(Everything below — logging, `save_message`, `update_relationship`, `_maybe_reflect_self`, `return result` — stays unchanged.)

- [ ] **Step 6: Run the wiring tests, then the focused paths**

Run: `venv/bin/python -m pytest tests/test_dedup_wiring.py -q`
Expected: PASS (5 passed).

- [ ] **Step 7: Run the full suite (no regressions)**

Run: `venv/bin/python -m pytest -q`
Expected: PASS. In particular the `/chat` and `/heard` endpoint tests still pass — `/chat` uses `lane="default"` so `dedupe=False` leaves it byte-for-byte, and the heard PASS/decline behavior is preserved through the `decline` hook. Two pre-existing FastAPI `on_event` warnings expected; no new warnings.

- [ ] **Step 8: Commit**

```bash
git add main.py tests/test_dedup_wiring.py
git commit -m "feat(chatter): dedup + one re-roll for tick and heard lanes"
```

---

## Deploy & tuning (after all tasks reviewed)

1. **No rebuild.** Brain hot-reloads under uvicorn `--reload`. Confirm health after reload: `curl -s localhost:5000/health`.
2. **Turn on a stronger heard model (optional):** set `WBB_OLLAMA_HEARD_MODEL` (e.g. a 14B or an MoE like `qwen3:30b-a3b`) in the brain's environment / `start.sh`, then restart the sidecar. Ambient `tick()` stays on the fast base model; only player-facing `/heard` replies use the bigger one. Pull the model into Ollama on the desktop first (`ollama pull ...`).
3. **Tune diversity without code edits** via env: `WBB_LLM_REPEAT_PENALTY` (try 1.15–1.35), `WBB_LLM_MIN_P`, `WBB_FLEET_DEDUP_THRESHOLD` (lower = more aggressive dedup), `WBB_FLEET_DEDUP_WINDOW_S`.
4. **Measure it, don't guess:** use the existing evolution-judge / A/B harness (the `model=` override on `call_ollama`) to score a candidate model or sampling profile against the base on the taste-calibrated rubric before committing to it.
5. **Live sanity:** watch `brain.log` — ambient `[tick]` lines should visibly vary across bots; `/heard` and `/tick` stay 200 OK with no 500s; direct whispers (`/chat`) unchanged.

## Notes for the executor
- Single repo: brain = `~/wow-bot-brain`, branch `evolution-council`. Push after review: `git push origin evolution-council` (personal repo `grodriguez1229/wow-bot-brain`). If merging to `master`, fast-forward is clean.
- Do NOT push to any non-personal remote.
- No worldserver / mod-playerbots changes in this slice.
