# Shared Memory — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give bots short-term awareness of nearby conversation and a persistent, evolving relationship memory, with a consolidation write-path skeleton, without corrupting eval attribution.

**Architecture:** Approach 1 (sheets + consolidation). The short-term "overheard" layer is caller-passed (brain stateless about it); the relationship layer is brain-owned in SQLite. After a scene, an injectable `summarize` callable consolidates the transcript into durable relationship notes. Scored eval runs with consolidation OFF from a seeded memory fixture so scores stay comparable.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite (stdlib `sqlite3`), httpx, pytest + pytest-bdd. Run tests with `venv/bin/pytest` from repo root. Local Ollama is the default summarizer backend but is never hit in tests (always mocked).

---

## File Structure

- `models.py` — add `RecentLine` + `recent_lines` field on both request models. (modify)
- `memory_prompt.py` — NEW. Pure prompt-section builders (`build_nearby_section`, `build_relationship_section`). No I/O, fully unit-testable.
- `prompts.py` — add `{nearby_section}` to `CHAT_PROMPT` and `TICK_PROMPT`. (modify)
- `db.py` — add `bot_memory` table, `set_relationship_notes`, `upsert_memory`, `get_memory_sheet`. (modify)
- `consolidate.py` — NEW. `parse_consolidation` (pure), `local_summarize` (default backend), `consolidate_scene` (orchestration).
- `main.py` — render nearby + relationship sections in `/chat` and `/tick`; add `/reflect` endpoint. (modify)
- `sim/brain_client.py` — forward `recent_lines`. (modify)
- `sim/scene_runner.py` — pass last-N lines as `recent_lines`; optional post-scene consolidation. (modify)
- `sim/memory_fixture.py` — NEW. `load_memory_fixture` resets memory tables to a checked-in seed.
- `eval/optimizer/memory_fixture.json` — NEW. The seeded relationship/sheet state for scored eval.
- Tests: `tests/test_models_recent_lines.py`, `tests/test_memory_prompt.py`, `tests/test_db_memory.py`, `tests/test_consolidate.py`, `tests/test_brain_client.py`, `tests/test_memory_fixture.py`, and BDD `tests/features/memory.feature` + `tests/test_memory_bdd.py`. Modify `tests/test_scene_runner.py` (FakeBrain gains `recent_lines` kwarg).

---

### Task 1: `recent_lines` on request models

**Files:**
- Modify: `models.py`
- Test: `tests/test_models_recent_lines.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_recent_lines.py
from models import ChatRequest, TickRequest, RecentLine


def test_chat_request_accepts_recent_lines():
    req = ChatRequest(
        bot_name="Geysse", player_name="Gus", message="hi",
        recent_lines=[{"speaker": "Lynea", "text": "anyone running Deadmines?"}],
    )
    assert isinstance(req.recent_lines[0], RecentLine)
    assert req.recent_lines[0].speaker == "Lynea"
    assert req.recent_lines[0].text == "anyone running Deadmines?"


def test_tick_request_recent_lines_defaults_none():
    req = TickRequest(bot_name="Geysse", location="Elwynn Forest")
    assert req.recent_lines is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_models_recent_lines.py -v`
Expected: FAIL — `ImportError: cannot import name 'RecentLine'`.

- [ ] **Step 3: Write minimal implementation**

In `models.py`, add the `RecentLine` model (above `ChatRequest`) and the field on both requests:

```python
class RecentLine(BaseModel):
    speaker: str
    text: str
```

Add to `ChatRequest` (after `nearby_bots`):

```python
    recent_lines: Optional[list[RecentLine]] = None
```

Add the identical field to `TickRequest` (after `bot_guild`):

```python
    recent_lines: Optional[list[RecentLine]] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_models_recent_lines.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models_recent_lines.py
git commit -m "feat(models): recent_lines (short-term overheard) on chat/tick requests"
```

---

### Task 2: Pure prompt-section builders

**Files:**
- Create: `memory_prompt.py`
- Test: `tests/test_memory_prompt.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_prompt.py
from memory_prompt import build_nearby_section, build_relationship_section


def test_nearby_section_empty_when_no_lines():
    assert build_nearby_section(None) == ""
    assert build_nearby_section([]) == ""


def test_nearby_section_renders_lines():
    out = build_nearby_section([
        {"speaker": "Lynea", "text": "anyone running Deadmines?"},
        {"speaker": "Geysse", "text": "nah im broke"},
    ])
    assert "OVERHEARD NEARBY" in out
    assert "don't repeat it" in out
    assert "  Lynea: anyone running Deadmines?" in out
    assert "  Geysse: nah im broke" in out


def test_relationship_section_empty_when_no_notes():
    assert build_relationship_section({"familiarity": 0, "notes": ""}) == ""
    assert build_relationship_section(None) == ""


def test_relationship_section_renders_notes():
    out = build_relationship_section({"familiarity": 12, "notes": "ran Deadmines together, owes you 2g"})
    assert "ran Deadmines together, owes you 2g" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_memory_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'memory_prompt'`.

- [ ] **Step 3: Write minimal implementation**

```python
# memory_prompt.py
"""Pure builders for the memory prompt sections. No I/O — unit-testable.

Both builders accept plain dicts so callers (main.py converts Pydantic
RecentLine via .model_dump(); db rows are sqlite3.Row -> dict) and tests share
one code path. Empty input renders an empty string, preserving prior prompts.
"""
from __future__ import annotations


def build_nearby_section(recent_lines) -> str:
    if not recent_lines:
        return ""
    lines = [f"  {rl['speaker']}: {rl['text']}" for rl in recent_lines]
    return "OVERHEARD NEARBY (react to this, don't repeat it):\n" + "\n".join(lines)


def build_relationship_section(rel) -> str:
    notes = ((rel or {}).get("notes") or "").strip()
    if not notes:
        return ""
    return f"WHAT YOU REMEMBER ABOUT THEM: {notes}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_memory_prompt.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add memory_prompt.py tests/test_memory_prompt.py
git commit -m "feat(memory): pure prompt-section builders for overheard + relationship"
```

---

### Task 3: Add `{nearby_section}` to both prompt templates

**Files:**
- Modify: `prompts.py`
- Test: `tests/test_memory_prompt.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_memory_prompt.py`:

```python
from prompts import CHAT_PROMPT, TICK_PROMPT


def test_both_prompts_have_nearby_placeholder():
    assert "{nearby_section}" in CHAT_PROMPT
    assert "{nearby_section}" in TICK_PROMPT


def test_tick_prompt_formats_with_nearby_section():
    # Every field used by main.py's TICK_PROMPT.format must be present.
    s = TICK_PROMPT.format(
        name="Geysse", level=16, race="Dwarf", class_name="Rogue", faction="Alliance",
        who="a tired night-shift nurse", typing_style="terse", mood="chill",
        current_goal="grind to 17", nearby_section="OVERHEARD NEARBY:\n  Lynea: hey",
    )
    assert "OVERHEARD NEARBY" in s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_memory_prompt.py -k nearby_placeholder -v`
Expected: FAIL — `{nearby_section}` not in templates / `KeyError` on format.

- [ ] **Step 3: Write minimal implementation**

In `prompts.py`, in `CHAT_PROMPT`, add a line immediately after `{memory_section}` (line 10):

```
{memory_section}

{nearby_section}
```

In `TICK_PROMPT`, add a line immediately after `IN-GAME GOAL: {current_goal}` (line 32), before the `RULES:` block:

```
IN-GAME GOAL: {current_goal}

{nearby_section}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_memory_prompt.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add prompts.py tests/test_memory_prompt.py
git commit -m "feat(prompts): nearby_section placeholder in chat + tick templates"
```

---

### Task 4: `bot_memory` table + relationship-notes DB helpers

**Files:**
- Modify: `db.py`
- Test: `tests/test_db_memory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_memory.py
import importlib
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_bot_memory_table_exists(fresh_db):
    conn = fresh_db.get_db()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_memory'"
    ).fetchall()
    conn.close()
    assert rows


def test_set_and_read_relationship_notes(fresh_db):
    fresh_db.update_relationship("Geysse", "Lynea", familiarity_delta=3)
    fresh_db.set_relationship_notes("Geysse", "Lynea", "ran Deadmines together")
    rel = fresh_db.get_relationship("Geysse", "Lynea")
    assert rel["notes"] == "ran Deadmines together"


def test_upsert_memory_is_idempotent_per_key(fresh_db):
    fresh_db.upsert_memory("Geysse", "relationship", "Lynea", "first note")
    fresh_db.upsert_memory("Geysse", "relationship", "Lynea", "updated note", weight=2)
    sheet = fresh_db.get_memory_sheet("Geysse")
    rel_rows = [r for r in sheet if r["kind"] == "relationship" and r["subject"] == "Lynea"]
    assert len(rel_rows) == 1
    assert rel_rows[0]["content"] == "updated note"
    assert rel_rows[0]["weight"] == 2


def test_init_db_idempotent(fresh_db):
    fresh_db.init_db()  # second call must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_db_memory.py -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'set_relationship_notes'`.

- [ ] **Step 3: Write minimal implementation**

In `db.py` `init_db()`, after the `relationships` CREATE TABLE block (before the migration `try` blocks), add:

```python
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_memory (
            bot_name   TEXT NOT NULL,
            kind       TEXT NOT NULL,
            subject    TEXT NOT NULL,
            content    TEXT NOT NULL,
            weight     INTEGER DEFAULT 1,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (bot_name, kind, subject)
        )
    """)
```

Add these functions at the end of `db.py`:

```python
def set_relationship_notes(bot_name: str, player_name: str, notes: str):
    conn = get_db()
    conn.execute("""
        INSERT INTO relationships (bot_name, player_name, notes)
        VALUES (?, ?, ?)
        ON CONFLICT(bot_name, player_name) DO UPDATE SET notes = excluded.notes
    """, (bot_name, player_name, notes))
    conn.commit()
    conn.close()


def upsert_memory(bot_name: str, kind: str, subject: str, content: str, weight: int = 1):
    conn = get_db()
    conn.execute("""
        INSERT INTO bot_memory (bot_name, kind, subject, content, weight)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(bot_name, kind, subject) DO UPDATE SET
            content = excluded.content,
            weight = excluded.weight,
            updated_at = CURRENT_TIMESTAMP
    """, (bot_name, kind, subject, content, weight))
    conn.commit()
    conn.close()


def get_memory_sheet(bot_name: str, kind: str | None = None) -> list[dict]:
    conn = get_db()
    if kind is None:
        rows = conn.execute(
            "SELECT * FROM bot_memory WHERE bot_name = ? ORDER BY updated_at DESC",
            (bot_name,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM bot_memory WHERE bot_name = ? AND kind = ? ORDER BY updated_at DESC",
            (bot_name, kind)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_db_memory.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db_memory.py
git commit -m "feat(db): bot_memory sheet table + relationship-notes helpers"
```

---

### Task 5: Render memory sections in `/chat` and `/tick`

**Files:**
- Modify: `main.py`
- Test: covered by Task 3 format tests + the BDD scene test in Task 10/11 (endpoint wiring is integration, verified end-to-end there). This task has no new unit test; the format-contract is guarded by Task 3.

- [ ] **Step 1: Wire `/chat`**

In `main.py`, add the import at top:

```python
from memory_prompt import build_nearby_section, build_relationship_section
```

In `chat()`, replace the memory-section block (lines 47–52) so the relationship notes are appended:

```python
    # Build memory section (pairwise history + persistent relationship notes)
    if history:
        mem_lines = [f"{'Them' if msg['role'] == 'user' else 'You'}: {msg['content']}" for msg in history[-6:]]
        memory_section = "Recent chat with them:\n" + "\n".join(mem_lines)
    else:
        memory_section = ""
    rel_section = build_relationship_section(rel)
    if rel_section:
        memory_section = (memory_section + "\n" + rel_section).strip()
```

In the `CHAT_PROMPT.format(...)` call, add the nearby section argument:

```python
        memory_section=memory_section,
        nearby_section=build_nearby_section(
            [rl.model_dump() for rl in (req.recent_lines or [])]
        ),
        action_rules=action_rules,
```

- [ ] **Step 2: Wire `/tick`**

In `tick()`, add `nearby_section` to the `TICK_PROMPT.format(...)` call:

```python
        current_goal=p["current_goal"],
        nearby_section=build_nearby_section(
            [rl.model_dump() for rl in (req.recent_lines or [])]
        ),
    )
```

- [ ] **Step 3: Smoke-test the app imports and formats**

Run: `venv/bin/python -c "import main; print('ok')"`
Expected: prints `ok` (no `KeyError`/import errors).

- [ ] **Step 4: Run the full suite to confirm no regression**

Run: `venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat(brain): inject overheard + relationship sections in chat/tick"
```

---

### Task 6: Consolidation output parser (pure)

**Files:**
- Create: `consolidate.py`
- Test: `tests/test_consolidate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_consolidate.py
from consolidate import parse_consolidation


def test_parses_valid_json_list():
    raw = '[{"subject": "Lynea", "note": "ran Deadmines together", "familiarity_delta": 2}]'
    out = parse_consolidation(raw)
    assert out == [{"subject": "Lynea", "note": "ran Deadmines together", "familiarity_delta": 2}]


def test_drops_malformed_entries_and_clamps_delta():
    raw = '''[
        {"subject": "Lynea", "note": "ok", "familiarity_delta": 999},
        {"note": "no subject"},
        {"subject": "Bob", "note": "", "familiarity_delta": 1},
        "garbage"
    ]'''
    out = parse_consolidation(raw)
    assert out == [{"subject": "Lynea", "note": "ok", "familiarity_delta": 5}]


def test_non_json_returns_empty():
    assert parse_consolidation("the model rambled") == []
    assert parse_consolidation("") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_consolidate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'consolidate'`.

- [ ] **Step 3: Write minimal implementation**

```python
# consolidate.py
"""Write-path skeleton: turn a finished Scene transcript into durable memory.

Phase 1 wires ONE layer (relationships) end-to-end. `summarize` is an injectable
callable (transcript_text, bot_name) -> raw JSON string, so tests mock it and a
richer backend (Claude / fan-out critique agents) swaps in later behind the same
signature. Parsing is pure and defensive: bad entries are dropped, never raised.
"""
from __future__ import annotations

import json

_DELTA_MIN, _DELTA_MAX = -5, 5


def parse_consolidation(raw: str) -> list[dict]:
    """Parse summarizer output into validated relationship updates.

    Expected shape: a JSON list of {subject:str, note:str, familiarity_delta:int}.
    Entries missing subject/note, or non-dict items, are dropped. Delta is clamped.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject")
        note = item.get("note")
        if not subject or not note:
            continue
        try:
            delta = int(item.get("familiarity_delta", 0))
        except (TypeError, ValueError):
            delta = 0
        delta = max(_DELTA_MIN, min(_DELTA_MAX, delta))
        out.append({"subject": str(subject), "note": str(note), "familiarity_delta": delta})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_consolidate.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add consolidate.py tests/test_consolidate.py
git commit -m "feat(consolidate): defensive parser for relationship updates"
```

---

### Task 7: `consolidate_scene` orchestration + default backend

**Files:**
- Modify: `consolidate.py`
- Test: `tests/test_consolidate.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_consolidate.py`:

```python
import pytest
from sim.transcript import Scene, Turn
from consolidate import consolidate_scene


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_consolidate_scene_persists_relationship(fresh_db):
    scene = Scene(
        scene_id="s1", location="Elwynn Forest", channel="SAY",
        participants=["Geysse", "Lynea"],
        turns=[
            Turn(idx=0, speaker="Geysse", channel="SAY", text="wanna run Deadmines?"),
            Turn(idx=1, speaker="Lynea", channel="SAY", text="yeah lets go"),
        ],
    )

    def fake_summarize(transcript_text, bot_name):
        other = "Lynea" if bot_name == "Geysse" else "Geysse"
        return f'[{{"subject": "{other}", "note": "agreed to run Deadmines", "familiarity_delta": 2}}]'

    updates = consolidate_scene(scene, summarize=fake_summarize, bots=["Geysse", "Lynea"])

    assert len(updates) == 2
    rel = fresh_db.get_relationship("Geysse", "Lynea")
    assert rel["notes"] == "agreed to run Deadmines"
    assert rel["familiarity"] >= 2
    sheet = fresh_db.get_memory_sheet("Geysse", kind="relationship")
    assert any(r["subject"] == "Lynea" for r in sheet)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_consolidate.py::test_consolidate_scene_persists_relationship -v`
Expected: FAIL — `ImportError: cannot import name 'consolidate_scene'`.

- [ ] **Step 3: Write minimal implementation**

Append to `consolidate.py`:

```python
import httpx

import db
from config import OLLAMA_URL, OLLAMA_MODEL


def _transcript_text(scene) -> str:
    return "\n".join(f"{t.speaker}: {t.text}" for t in scene.turns)


def local_summarize(transcript_text: str, bot_name: str) -> str:
    """Default backend: ask the local model, as `bot_name`, for relationship
    updates as a JSON list. Synchronous (consolidation runs outside request
    handling). Never called in tests — they inject a fake summarize."""
    system = (
        f"You are {bot_name}. Read this WoW zone chat you took part in and output ONLY a "
        f"JSON list of relationship updates about OTHER people, each "
        f'{{"subject": name, "note": short memory, "familiarity_delta": -5..5}}. '
        f"No prose, JSON only."
    )
    resp = httpx.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL, "think": False, "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": transcript_text},
        ],
        "options": {"num_predict": 200, "temperature": 0.3},
    }, timeout=60.0)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def consolidate_scene(scene, *, summarize=None, bots=None) -> list[dict]:
    """For each bot participant, derive + persist relationship updates from the
    scene transcript. Returns the flat list of applied updates.

    `summarize` resolves to `local_summarize` at CALL time (not as a default-arg
    value) so monkeypatching `consolidate.local_summarize` in tests takes effect."""
    if summarize is None:
        summarize = local_summarize
    if bots is None:
        bots = list(scene.participants)
    transcript = _transcript_text(scene)
    applied: list[dict] = []
    for bot in bots:
        raw = summarize(transcript, bot)
        for upd in parse_consolidation(raw):
            subject, note, delta = upd["subject"], upd["note"], upd["familiarity_delta"]
            db.set_relationship_notes(bot, subject, note)
            if delta:
                db.update_relationship(bot, subject, familiarity_delta=delta)
            db.upsert_memory(bot, "relationship", subject, note)
            applied.append({"bot": bot, **upd})
    return applied
```

Note: `db.update_relationship` now floors familiarity at 0 (`MAX(...,0)`) so a negative `familiarity_delta` decrements toward 0 but never below; clamp range remains [-5,5].

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_consolidate.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add consolidate.py tests/test_consolidate.py
git commit -m "feat(consolidate): consolidate_scene persists relationship layer via injectable summarizer"
```

---

### Task 8: `/reflect` endpoint

**Files:**
- Modify: `main.py`, `models.py`
- Test: `tests/test_consolidate.py` (extend with a TestClient call)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_consolidate.py`:

```python
from fastapi.testclient import TestClient


def test_reflect_endpoint_runs_consolidation(fresh_db, monkeypatch):
    import consolidate
    monkeypatch.setattr(
        consolidate, "local_summarize",
        lambda transcript, bot: '[{"subject": "Lynea", "note": "helped me quest", "familiarity_delta": 1}]',
    )
    import main
    client = TestClient(main.app)
    payload = {
        "scene": {
            "scene_id": "s1", "location": "Elwynn Forest", "channel": "SAY",
            "participants": ["Geysse", "Lynea"],
            "turns": [{"idx": 0, "speaker": "Geysse", "channel": "SAY", "text": "ty"}],
        },
        "bots": ["Geysse"],
    }
    r = client.post("/reflect", json=payload)
    assert r.status_code == 200
    assert r.json()["applied"] >= 1
    assert fresh_db.get_relationship("Geysse", "Lynea")["notes"] == "helped me quest"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_consolidate.py::test_reflect_endpoint_runs_consolidation -v`
Expected: FAIL — 404 (no `/reflect` route).

- [ ] **Step 3: Write minimal implementation**

In `models.py`, add request models for the endpoint:

```python
class ReflectTurn(BaseModel):
    idx: int = 0
    speaker: str
    channel: str = "SAY"
    text: str
    actions: list = []

class ReflectScene(BaseModel):
    scene_id: str
    location: str = ""
    channel: str = "SAY"
    participants: list[str] = []
    turns: list[ReflectTurn] = []

class ReflectRequest(BaseModel):
    scene: ReflectScene
    bots: Optional[list[str]] = None
```

In `main.py`, add the import and route:

```python
from consolidate import consolidate_scene
from models import ReflectRequest  # add to existing models import line
from sim.transcript import Scene, Turn


@app.post("/reflect")
def reflect(req: ReflectRequest):
    s = req.scene
    scene = Scene(
        scene_id=s.scene_id, location=s.location, channel=s.channel,
        participants=s.participants,
        turns=[Turn(idx=t.idx, speaker=t.speaker, channel=t.channel,
                    text=t.text, actions=t.actions) for t in s.turns],
    )
    applied = consolidate_scene(scene, bots=req.bots)
    return {"applied": len(applied), "updates": applied}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_consolidate.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add main.py models.py tests/test_consolidate.py
git commit -m "feat(brain): /reflect endpoint runs scene consolidation"
```

---

### Task 9: `brain_client` forwards `recent_lines`

**Files:**
- Modify: `sim/brain_client.py`
- Test: `tests/test_brain_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_brain_client.py
import sim.brain_client as bc


class _Resp:
    status_code = 200
    def raise_for_status(self): pass
    def json(self): return {"message": "ok", "channel": "SAY", "actions": []}


def test_chat_forwards_recent_lines(monkeypatch):
    captured = {}
    def fake_post(url, json, timeout):
        captured["json"] = json
        return _Resp()
    monkeypatch.setattr(bc.httpx, "post", fake_post)

    client = bc.BrainClient()
    client.chat("Geysse", "Gus", "hi", "SAY", "Elwynn Forest",
                recent_lines=[{"speaker": "Lynea", "text": "hey"}])
    assert captured["json"]["recent_lines"] == [{"speaker": "Lynea", "text": "hey"}]


def test_tick_forwards_recent_lines(monkeypatch):
    captured = {}
    monkeypatch.setattr(bc.httpx, "post", lambda url, json, timeout: (captured.update(json=json) or _Resp()))
    client = bc.BrainClient()
    client.tick("Geysse", "Elwynn Forest", [], ["Lynea"],
                recent_lines=[{"speaker": "Lynea", "text": "hey"}])
    assert captured["json"]["recent_lines"] == [{"speaker": "Lynea", "text": "hey"}]


def test_recent_lines_omitted_when_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(bc.httpx, "post", lambda url, json, timeout: (captured.update(json=json) or _Resp()))
    bc.BrainClient().chat("Geysse", "Gus", "hi")
    assert captured["json"].get("recent_lines") in (None, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_brain_client.py -v`
Expected: FAIL — `chat() got an unexpected keyword argument 'recent_lines'`.

- [ ] **Step 3: Write minimal implementation**

In `sim/brain_client.py`, update both methods to accept and forward `recent_lines`:

```python
    def chat(self, bot_name, player_name, message, channel="SAY", location="", recent_lines=None):
        payload = {
            "bot_name": bot_name, "player_name": player_name,
            "message": message, "channel": channel, "location": location,
        }
        if recent_lines:
            payload["recent_lines"] = recent_lines
        r = httpx.post(f"{self.base_url}/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        d = r.json()
        return {"message": d.get("message", ""), "channel": d.get("channel", channel),
                "actions": d.get("actions", [])}

    def tick(self, bot_name, location="", nearby_players=None, nearby_bots=None, recent_lines=None):
        payload = {
            "bot_name": bot_name, "location": location,
            "nearby_players": nearby_players or [], "nearby_bots": nearby_bots or [],
        }
        if recent_lines:
            payload["recent_lines"] = recent_lines
        r = httpx.post(f"{self.base_url}/tick", json=payload, timeout=self.timeout)
        r.raise_for_status()
        d = r.json()
        return {"message": d.get("message", ""), "channel": d.get("channel", "SAY"),
                "actions": d.get("actions", [])}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_brain_client.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add sim/brain_client.py tests/test_brain_client.py
git commit -m "feat(sim): brain_client forwards recent_lines"
```

---

### Task 10: `scene_runner` passes `recent_lines` + optional consolidation

**Files:**
- Modify: `sim/scene_runner.py`, `tests/test_scene_runner.py` (FakeBrain signatures)
- Test: existing `tests/features/scene_runner.feature` must stay green; new behavior covered in Task 11.

- [ ] **Step 1: Update FakeBrain in existing test to accept the new kwarg**

In `tests/test_scene_runner.py`, change `FakeBrain.chat`/`tick` signatures so they tolerate `recent_lines` (keeps existing scenarios valid after the runner change):

```python
    def chat(self, bot, player, msg, ch, loc, recent_lines=None):
        self.chat_calls += 1
        return {"message": f"{bot} says hi #{self.chat_calls}", "channel": ch, "actions": []}

    def tick(self, bot, loc, np_, nb, recent_lines=None):
        self.tick_calls += 1
        return {"message": f"{bot} emotes #{self.tick_calls}", "channel": "SAY", "actions": []}
```

- [ ] **Step 2: Run existing scene_runner tests to confirm they still pass (no behavior change yet)**

Run: `venv/bin/pytest tests/test_scene_runner.py -v`
Expected: PASS (the kwarg is unused for now).

- [ ] **Step 3: Implement recent_lines pass-through + optional consolidation in `run_scene`**

In `sim/scene_runner.py`, add a parameter and a constant near the top of `run_scene`'s signature:

```python
def run_scene(brain, scene_id, location, channel, bots, player="Gus",
              turns=8, seed=0, tick_prob=0.25, player_followup_prob=0.2,
              nearby_window=4, consolidate=False):
```

Build the overheard lines just before each brain call. Replace the `force_tick`/chat/tick block with:

```python
        recent_lines = [{"speaker": t.speaker, "text": t.text} for t in recorded[-nearby_window:]]

        force_tick = not recorded and not last_text
        if force_tick or not player or r.random() < tick_prob:
            resp = brain.tick(bot, location, [player] if player else [], nearby_bots,
                              recent_lines=recent_lines)
        else:
            resp = brain.chat(bot, player, last_text, channel, location,
                             recent_lines=recent_lines)
```

At the end of `run_scene`, before `return Scene(...)`, build the scene then optionally consolidate:

```python
    scene = Scene(scene_id=scene_id, location=location, channel=channel,
                  participants=participants, turns=recorded)
    if consolidate:
        from consolidate import consolidate_scene
        consolidate_scene(scene, bots=list(bots))
    return scene
```

(Remove the old inline `return Scene(...)`.)

- [ ] **Step 4: Run the suite**

Run: `venv/bin/pytest tests/test_scene_runner.py -v`
Expected: PASS — determinism + ordering scenarios unaffected (recent_lines is deterministic from the seeded transcript; `consolidate` defaults False).

- [ ] **Step 5: Commit**

```bash
git add sim/scene_runner.py tests/test_scene_runner.py
git commit -m "feat(sim): scene_runner passes recent_lines; opt-in post-scene consolidation"
```

---

### Task 11: BDD — overheard awareness + consolidation behavior

**Files:**
- Create: `tests/features/memory.feature`, `tests/test_memory_bdd.py`

- [ ] **Step 1: Write the feature file**

```gherkin
# tests/features/memory.feature
Feature: Shared memory shapes bot behavior
  As the world-sim
  I want bots to hear nearby chatter and remember people
  So that scenes read as conversation, not broadcast

  Scenario: A bot's request carries the lines said just before it
    Given a recording fake brain
    And bots "Geysse" and "Lynea"
    When I run a 4-turn no-player scene with seed 2
    Then at least one brain call received non-empty recent_lines

  Scenario: Consolidation records a relationship note from a transcript
    Given a fresh memory db
    And a two-bot transcript where they agree to group up
    When I consolidate the scene with a canned summarizer
    Then "Geysse" remembers a note about "Lynea"
```

- [ ] **Step 2: Write the step definitions (failing)**

```python
# tests/test_memory_bdd.py
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.scene_runner import run_scene
from sim.transcript import Scene, Turn

scenarios("features/memory.feature")


class RecordingBrain:
    def __init__(self):
        self.recent_seen = []
    def chat(self, bot, player, msg, ch, loc, recent_lines=None):
        self.recent_seen.append(recent_lines or [])
        return {"message": f"{bot} replies", "channel": ch, "actions": []}
    def tick(self, bot, loc, np_, nb, recent_lines=None):
        self.recent_seen.append(recent_lines or [])
        return {"message": f"{bot} mutters", "channel": "SAY", "actions": []}


@pytest.fixture
def context():
    return {}


@given("a recording fake brain")
def _rec_brain(context):
    context["brain"] = RecordingBrain()


@given(parsers.parse('bots "{a}" and "{b}"'))
def _bots(context, a, b):
    context["bots"] = [a, b]


@when(parsers.parse("I run a {turns:d}-turn no-player scene with seed {seed:d}"))
def _run(context, turns, seed):
    context["scene"] = run_scene(
        brain=context["brain"], scene_id="m1", location="Elwynn Forest",
        channel="SAY", bots=context["bots"], player=None, turns=turns, seed=seed,
    )


@then("at least one brain call received non-empty recent_lines")
def _saw_recent(context):
    assert any(len(r) > 0 for r in context["brain"].recent_seen)


@given("a fresh memory db")
def _fresh(context, tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    context["db"] = db


@given("a two-bot transcript where they agree to group up")
def _transcript(context):
    context["scene"] = Scene(
        scene_id="m2", location="Elwynn Forest", channel="SAY",
        participants=["Geysse", "Lynea"],
        turns=[
            Turn(idx=0, speaker="Geysse", channel="SAY", text="group up?"),
            Turn(idx=1, speaker="Lynea", channel="SAY", text="sure"),
        ],
    )


@when("I consolidate the scene with a canned summarizer")
def _consolidate(context):
    from consolidate import consolidate_scene
    canned = lambda transcript, bot: '[{"subject": "Lynea", "note": "grouped up in Elwynn", "familiarity_delta": 2}]'
    consolidate_scene(context["scene"], summarize=canned, bots=["Geysse"])


@then(parsers.parse('"{bot}" remembers a note about "{subject}"'))
def _remembers(context, bot, subject):
    rel = context["db"].get_relationship(bot, subject)
    assert rel["notes"]
    sheet = context["db"].get_memory_sheet(bot, kind="relationship")
    assert any(r["subject"] == subject for r in sheet)
```

- [ ] **Step 3: Run to verify it fails, then passes after Tasks 1–10 are in**

Run: `venv/bin/pytest tests/test_memory_bdd.py -v`
Expected: PASS once Tasks 1–10 are implemented (this task adds only tests). If RED, the failing assertion points at the gap.

- [ ] **Step 4: Run the full suite**

Run: `venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/features/memory.feature tests/test_memory_bdd.py
git commit -m "test(memory): BDD for overheard awareness + consolidation"
```

---

### Task 12: Seeded eval memory fixture (attribution guard)

**Files:**
- Create: `sim/memory_fixture.py`, `eval/optimizer/memory_fixture.json`
- Test: `tests/test_memory_fixture.py`

- [ ] **Step 1: Write the fixture JSON**

```json
{
  "relationships": [
    {"bot_name": "Geysse", "player_name": "Lynea", "familiarity": 12, "label": "acquaintance", "notes": "duo partner, ran Deadmines last week"},
    {"bot_name": "Lynea", "player_name": "Geysse", "familiarity": 12, "label": "acquaintance", "notes": "rogue buddy, always broke"}
  ],
  "bot_memory": [
    {"bot_name": "Geysse", "kind": "relationship", "subject": "Lynea", "content": "duo partner, ran Deadmines last week", "weight": 2},
    {"bot_name": "Lynea", "kind": "relationship", "subject": "Geysse", "content": "rogue buddy, always broke", "weight": 2}
  ]
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_memory_fixture.py
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_fixture_load_is_deterministic(fresh_db):
    from sim.memory_fixture import load_memory_fixture
    path = "eval/optimizer/memory_fixture.json"

    load_memory_fixture(path)
    rel1 = fresh_db.get_relationship("Geysse", "Lynea")
    sheet1 = fresh_db.get_memory_sheet("Geysse")

    load_memory_fixture(path)  # second load must reset to the same state
    rel2 = fresh_db.get_relationship("Geysse", "Lynea")
    sheet2 = fresh_db.get_memory_sheet("Geysse")

    assert rel1 == rel2
    assert rel1["notes"] == "duo partner, ran Deadmines last week"
    assert rel1["familiarity"] == 12
    assert [(r["kind"], r["subject"], r["content"]) for r in sheet1] == \
           [(r["kind"], r["subject"], r["content"]) for r in sheet2]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_memory_fixture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.memory_fixture'`.

- [ ] **Step 4: Write minimal implementation**

```python
# sim/memory_fixture.py
"""Restore bot memory to a fixed, checked-in state before a scored eval run.

Persistent memory would make eval runs incomparable; loading this fixture (and
running scored generation with consolidation OFF) makes the relationship layer
contribute identically across candidates, preserving attribution.
"""
from __future__ import annotations

import json
from pathlib import Path

import db


def load_memory_fixture(path: str) -> None:
    data = json.loads(Path(path).read_text())
    conn = db.get_db()
    conn.execute("DELETE FROM relationships")
    conn.execute("DELETE FROM bot_memory")
    for r in data.get("relationships", []):
        conn.execute(
            """INSERT INTO relationships (bot_name, player_name, familiarity, label, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (r["bot_name"], r["player_name"], r["familiarity"], r["label"], r["notes"]),
        )
    for m in data.get("bot_memory", []):
        conn.execute(
            """INSERT INTO bot_memory (bot_name, kind, subject, content, weight)
               VALUES (?, ?, ?, ?, ?)""",
            (m["bot_name"], m["kind"], m["subject"], m["content"], m.get("weight", 1)),
        )
    conn.commit()
    conn.close()
```

- [ ] **Step 5: Run test to verify it passes, then commit**

Run: `venv/bin/pytest tests/test_memory_fixture.py -v`
Expected: PASS.

```bash
git add sim/memory_fixture.py eval/optimizer/memory_fixture.json tests/test_memory_fixture.py
git commit -m "feat(eval): seeded memory fixture for attributable scored runs"
```

---

### Task 13: Full-suite green + Phase 1 done check

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `venv/bin/pytest -q`
Expected: all green (existing optimizer/judge/sim tests + the new memory tests).

- [ ] **Step 2: Smoke-test the brain still boots**

Run: `venv/bin/python -c "import main; print(main.app.title)"`
Expected: prints `wow-bot-brain`.

- [ ] **Step 3: Confirm Definition-of-Done items**

Verify against the spec's "Definition of done":
- `recent_lines` plumbed request→prompt for `/chat` and `/tick` (Tasks 1,3,5).
- `bot_memory` + relationship notes injected (Tasks 4,5).
- `consolidate_scene` via injectable summarizer + `/reflect` (Tasks 7,8).
- sim passes `recent_lines`; scored eval path leaves consolidation OFF (Task 10 default) and a seeded fixture exists (Task 12).
- BDD + unit tests green (this task).

- [ ] **Step 4: Commit any final docs/notes (if needed)**

```bash
git add -A && git commit -m "chore(memory): Phase 1 complete — full suite green" || echo "nothing to commit"
```

- [ ] **Step 5: Hand back for the believability bake-off**

After this plan, the next (separate) action is a bake-off-harness eval run from the seeded fixture (qwen, consolidation OFF) to compare against the 2.163 baseline — does Phase 1 lift the no-player ambient scenes? That run is human-gated; promotion stays the user's call; nothing pushes to any remote.

---

## Notes for the implementer

- Always run tests with `venv/bin/pytest` from the repo root (conftest adds root to `sys.path`).
- The local model (`call_ollama` / `local_summarize`) is **never** hit in tests — every test injects a fake summarizer or a fake brain. Keep it that way.
- SQLite tests isolate via `monkeypatch.setattr(db, "DB_PATH", ...)` + `db.init_db()`. Do not touch the real `memory.db`.
- This is a private, local-only repo (no git remotes). Do not add or push to any remote.
