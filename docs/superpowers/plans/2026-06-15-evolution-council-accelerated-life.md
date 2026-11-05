# Bot Evolution Slice 1 — Accelerated-Life + Council Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline harness that compresses many simulated "days" of one bot's life into a minutes-long run, driven by a diverse 3-persona council that pushes the bot's identity to drift, so we can watch a bot visibly evolve.

**Architecture:** A new `kind='identity'` layer in `bot_memory` holds a bot's accumulating, drifting self (augmenting the frozen template). `council.py` is the engine: three diverse persona "lenses" PROPOSE nudges (Ollama, injectable seam), a SYNTHESIS step reconciles them into identity edits, applied to the writable layer. `sim/accelerated_life.py` runs `day = live a scene + reflect` for N days against an experiment brain, writing identity facets directly to the shared `/tmp` DB (the brain reads them into its prompts). Verification is eyeball: day-0-vs-day-N identity diff + fixed-probe transcripts.

**Tech Stack:** Python 3, SQLite (`db.py`), FastAPI brain (`main.py`), httpx → Ollama on `<ollama-host>`, pytest + pytest-bdd. No network in tests (model seams are injected fakes).

**Spec:** `docs/superpowers/specs/2026-06-15-evolution-council-accelerated-life-design.md`

**Conventions in this repo (follow exactly):**
- DB tests use this fixture (the module-global `DB_PATH` is read by `db.get_db()` at call time):
  ```python
  @pytest.fixture
  def fresh_db(tmp_path, monkeypatch):
      import db
      monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
      db.init_db()
      return db
  ```
- BDD: a `features/<name>.feature` file + a `tests/test_<name>_bdd.py` with `scenarios("features/<name>.feature")` and `@given/@when/@then` using `parsers.parse(...)`. A shared `context` dict fixture carries state.
- Pure parsers mirror `consolidate.parse_consolidation` / `self_memory.parse_self_notes`: defensive, never raise, drop bad entries.
- Model-calling functions mirror `consolidate.local_summarize`: thin httpx wrappers, "never called in tests."
- Run tests with `venv/bin/pytest`. Commit after each task. Branch is `evolution-council` (already created).

---

## File Structure

- **`db.py`** (modify): add `delete_memory`, `prune_memory_by_weight`, `get_who`.
- **`memory_prompt.py`** (modify): add `build_identity_section`.
- **`prompts.py`** (modify): add `{identity_section}` to both prompts; relax "2005 person" framing to game-locked / person-open.
- **`main.py`** (modify): fill `identity_section` in `/chat` and `/tick`; import the builder.
- **`council.py`** (create): personas, pure parsers (`parse_nudges`, `parse_edits`, `merge_nudges`), digest builders, `apply_edits`, `run_reflection`, and the Ollama seams `local_propose`/`local_synthesize`.
- **`sim/accelerated_life.py`** (create): `day_plan`, `run_day`, `run_accelerated_life`, probe + report rendering, `__main__`.
- **Tests:** `tests/test_db_identity.py`, `tests/test_identity_section.py`, `tests/test_prompts_identity.py`, `tests/test_council.py`, `tests/features/council_reflection.feature` + `tests/test_council_reflection_bdd.py`, `tests/features/accelerated_life.feature` + `tests/test_accelerated_life_bdd.py`.

---

## Task 1: DB helpers for the identity layer

**Files:**
- Modify: `db.py`
- Test: `tests/test_db_identity.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db_identity.py
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_delete_memory_removes_one_subject(fresh_db):
    fresh_db.upsert_memory("Bot", "identity", "outlook", "cynical", weight=3)
    fresh_db.upsert_memory("Bot", "identity", "pugs", "done with them", weight=2)
    fresh_db.delete_memory("Bot", "identity", "outlook")
    rows = fresh_db.get_memory_sheet("Bot", "identity")
    assert {r["subject"] for r in rows} == {"pugs"}


def test_prune_by_weight_keeps_strongest(fresh_db):
    fresh_db.upsert_memory("Bot", "identity", "a", "x", weight=5)
    fresh_db.upsert_memory("Bot", "identity", "b", "x", weight=1)
    fresh_db.upsert_memory("Bot", "identity", "c", "x", weight=3)
    fresh_db.prune_memory_by_weight("Bot", "identity", keep=2)
    rows = fresh_db.get_memory_sheet("Bot", "identity")
    assert {r["subject"] for r in rows} == {"a", "c"}  # weakest (b) pruned


def test_prune_by_weight_other_kinds_untouched(fresh_db):
    fresh_db.upsert_memory("Bot", "identity", "a", "x", weight=1)
    fresh_db.upsert_memory("Bot", "self", "mood", "tired", weight=1)
    fresh_db.prune_memory_by_weight("Bot", "identity", keep=0)
    assert fresh_db.get_memory_sheet("Bot", "identity") == []
    assert len(fresh_db.get_memory_sheet("Bot", "self")) == 1


def test_get_who_returns_persona_or_empty(fresh_db):
    assert fresh_db.get_who("Nobody") == ""
    conn = fresh_db.get_db()
    conn.execute(
        """INSERT INTO bot_personalities
           (bot_name, race, class_name, level, gender, faction, identity_id, who,
            typing_style, current_goal)
           VALUES ('Bot','Dwarf','Rogue',16,'male','Alliance','retail_worker',
                   'a tired retail worker who games to unwind','terse','hit 20')""")
    conn.commit(); conn.close()
    assert "retail worker" in fresh_db.get_who("Bot")
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/pytest tests/test_db_identity.py -v`
Expected: FAIL (`AttributeError: module 'db' has no attribute 'delete_memory'`).

- [ ] **Step 3: Implement the helpers**

Add to `db.py` (after `prune_memory`):

```python
def delete_memory(bot_name: str, kind: str, subject: str):
    conn = get_db()
    conn.execute(
        "DELETE FROM bot_memory WHERE bot_name = ? AND kind = ? AND subject = ?",
        (bot_name, kind, subject))
    conn.commit()
    conn.close()


def prune_memory_by_weight(bot_name: str, kind: str, keep: int):
    """Keep the `keep` STRONGEST memories of `kind` (highest weight, ties broken by most
    recent), delete the rest. Identity prunes by conviction so a strongly-held trait
    survives a flurry of weak new ones (unlike prune_memory, which is recency-only)."""
    conn = get_db()
    conn.execute("""
        DELETE FROM bot_memory
        WHERE bot_name = ? AND kind = ?
          AND rowid NOT IN (
            SELECT rowid FROM bot_memory
            WHERE bot_name = ? AND kind = ?
            ORDER BY weight DESC, updated_at DESC, rowid DESC LIMIT ?
          )
    """, (bot_name, kind, bot_name, kind, keep))
    conn.commit()
    conn.close()


def get_who(bot_name: str) -> str:
    """The frozen IRL persona text seeded at creation; '' if the bot has no row yet."""
    conn = get_db()
    row = conn.execute(
        "SELECT who FROM bot_personalities WHERE bot_name = ?", (bot_name,)).fetchone()
    conn.close()
    return row["who"] if row else ""
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_db_identity.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db_identity.py
git commit -m "feat(db): identity-layer helpers (delete_memory, prune_by_weight, get_who)"
```

---

## Task 2: `build_identity_section` prompt builder

**Files:**
- Modify: `memory_prompt.py`
- Test: `tests/test_identity_section.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_identity_section.py
from memory_prompt import build_identity_section


def test_empty_returns_blank():
    assert build_identity_section(None) == ""
    assert build_identity_section([]) == ""


def test_renders_facets_strongest_first():
    facets = [
        {"subject": "pugs", "content": "done with pugs after getting ninja-looted", "weight": 2},
        {"subject": "outlook", "content": "weirdly into late-night philosophy tangents", "weight": 4},
    ]
    out = build_identity_section(facets)
    assert out.startswith("WHO YOU'VE BECOME")
    # strongest (weight 4) listed before weaker (weight 2)
    assert out.index("philosophy") < out.index("ninja-looted")
    assert "- done with pugs" in out


def test_skips_blank_content():
    facets = [{"subject": "x", "content": "  ", "weight": 3}]
    assert build_identity_section(facets) == ""
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/bin/pytest tests/test_identity_section.py -v`
Expected: FAIL (`ImportError: cannot import name 'build_identity_section'`).

- [ ] **Step 3: Implement**

Add to `memory_prompt.py` (after `build_self_section`):

```python
def build_identity_section(identity_facets: list[dict] | None) -> str:
    """The bot's accumulated, drifting identity (kind='identity' rows), strongest first.
    Empty -> '' so a never-reflected bot prompts exactly as before."""
    if not identity_facets:
        return ""
    facets = sorted(identity_facets, key=lambda f: -int(f.get("weight", 1) or 1))
    lines = [f"- {c}" for f in facets if (c := (f.get("content") or "").strip())]
    if not lines:
        return ""
    return ("WHO YOU'VE BECOME (this grew out of your time on the server — let it color "
            "how you talk, what you care about, who you like):\n" + "\n".join(lines))
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_identity_section.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add memory_prompt.py tests/test_identity_section.py
git commit -m "feat(prompt): build_identity_section for the drifting identity layer"
```

---

## Task 3: Wire `{identity_section}` into the prompts + relax framing

**Files:**
- Modify: `prompts.py`
- Test: `tests/test_prompts_identity.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_prompts_identity.py
import prompts


def test_both_prompts_have_identity_placeholder():
    assert "{identity_section}" in prompts.CHAT_PROMPT
    assert "{identity_section}" in prompts.TICK_PROMPT


def test_chat_prompt_allows_real_world_topics():
    # person-open framing: modern/real-world topics are explicitly permitted
    assert "wider world" in prompts.CHAT_PROMPT


def test_game_world_still_locked_vanilla():
    assert "no expansions" in prompts.CHAT_PROMPT
    assert "no expansions" in prompts.TICK_PROMPT


def test_chat_prompt_formats_with_identity_section():
    # all placeholders fillable, including the new one
    out = prompts.CHAT_PROMPT.format(
        who="a tired dwarf", typing_style="terse", mood="chill", name="Bot",
        level=16, race="Dwarf", class_name="Rogue", faction="Alliance",
        current_goal="hit 20", motivation_line="", self_section="",
        identity_section="WHO YOU'VE BECOME:\n- cynical about pugs",
        context_section="", memory_section="", nearby_section="", action_rules="")
    assert "cynical about pugs" in out
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/bin/pytest tests/test_prompts_identity.py -v`
Expected: FAIL (placeholder/text not present).

- [ ] **Step 3: Replace both prompt strings**

Replace the entire `CHAT_PROMPT = """..."""` assignment in `prompts.py` with:

```python
CHAT_PROMPT = """You're a real person at your computer, playing on a vanilla-era World of Warcraft server (original WoW — level cap 60, no expansions). The character is just who you play — YOU are the person behind the keyboard.

YOU (the real person): {who}
TYPING STYLE: {typing_style}
MOOD RIGHT NOW: {mood}
YOUR CHARACTER: {name}, level {level} {race} {class_name} ({faction})
IN-GAME GOAL: {current_goal}
{motivation_line}
{self_section}
{identity_section}
{context_section}

{memory_section}

{nearby_section}

HOW TO TALK:
- You're a REAL PERSON. Type like one — casual, messy, lowercase is fine. No paragraphs, no eloquent prose, no narrating actions with asterisks.
- Length follows the conversation: a quick "lol yeah" for small talk, but 2-4 sentences when it's personal or you actually have something to say. NEVER write essays.
- If they ask about YOU — your day, your life, who you are — answer as the real person: your job or school, what kind of day you had, your mood, what's going on IRL. That's what real players do in whispers. Don't just recite your character's level and grind.
- You can talk about ANYTHING a real person would: your real life (work, school, food, music, being tired), the wider world (news, history, whatever's on your mind), opinions about the game, other players, jokes, random tangents, plans — not just quests and grinding.
- React to what they actually SAID. Ask them stuff back. Be a person having a conversation, not an NPC reading quest text.
- Be short or dismissive if you're not in the mood — that's human too.
- NEVER just repeat or paraphrase what someone already said.

KEEPING THE GAME WORLD VANILLA (this is about the GAME, not you the person):
- No emojis, ever. In-game, never name an expansion (Burning Crusade, Wrath/WotLK, Outland) or anything post-vanilla — that content doesn't exist on this server.
- Your CHARACTER's game knowledge matches your level. A level 12 hasn't been to Molten Core.
- You are the class shown above — only mention abilities, spells, or roles YOUR class actually has. A Paladin doesn't cast Mage spells.
- You're in the location shown above right now. Don't claim to be in a different zone, or in a dungeon when you're standing in a city.
- NEVER reveal you're an AI. You're a person.
- You can suggest doing things together — grouping up, running a dungeon, questing. That's what real players do.
{action_rules}"""
```

Replace the entire `TICK_PROMPT = """..."""` assignment with:

```python
TICK_PROMPT = """You're a real person playing on a vanilla-era World of Warcraft server (original WoW, level cap 60, no expansions). The character is who you play — YOU are the person behind the keyboard.

YOU (the real person): {who}
TYPING STYLE: {typing_style}
MOOD RIGHT NOW: {mood}
YOUR CHARACTER: {name}, level {level} {race} {class_name} ({faction})
IN-GAME GOAL: {current_goal}
{motivation_line}
{self_section}
{identity_section}

{nearby_section}

RULES:
- Type like a real person. ONE short line. 5-15 words max. That's it.
- Not everything is an errand. Sometimes it's a real-life aside (tired from work, this song, something on your mind), a reaction, an opinion, or a joke — not just LFG/WTS/quests.
- If you can see OVERHEARD lines, react to them or do your own thing — NEVER repeat or paraphrase what was just said.
- Keep the GAME WORLD vanilla: never mention anything that doesn't exist in vanilla WoW in-game (no Outland, no Argus, no flying mounts, no achievements, no dungeon finder).
- No emojis, ever. In-game, never name an expansion (Wrath/WotLK, Burning Crusade) — this is the original game.
- Your gold and experience should be realistic for your level. A level 15 has maybe 50 silver, not thousands of gold.
- NEVER reveal you're an AI.
- Your CHARACTER's game knowledge MUST match your level. You only know zones and dungeons you've actually been to.
"""
```

(Leave `build_action_rules`, `_MOTIVATION_LINES`, `build_motivation_line` unchanged.)

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_prompts_identity.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add prompts.py tests/test_prompts_identity.py
git commit -m "feat(prompts): {identity_section} + game-locked/person-open framing"
```

---

## Task 4: Fill `identity_section` in the brain (`main.py`)

**Files:**
- Modify: `main.py` (import line ~22; `/chat` `.format` kwargs ~line 112; `/tick` `.format` kwargs ~line 179)

This task has no isolated unit test (it requires the running app + Ollama); it is covered by the live verification run. Keep the change surgical and verified by `python -c` import + the existing suite still passing.

- [ ] **Step 1: Add the import**

In `main.py`, change:
```python
from memory_prompt import build_nearby_section, build_relationship_section, build_self_section
```
to:
```python
from memory_prompt import build_nearby_section, build_relationship_section, build_self_section, build_identity_section
```

- [ ] **Step 2: Fill identity_section in `/chat`**

Find the `CHAT_PROMPT.format(...)` call in the `/chat` handler. Immediately after the line:
```python
        self_section=build_self_section(get_memory_sheet(req.bot_name, "self")),
```
add:
```python
        identity_section=build_identity_section(get_memory_sheet(req.bot_name, "identity")),
```

- [ ] **Step 3: Fill identity_section in `/tick`**

Find the `TICK_PROMPT.format(...)` call in the `/tick` handler. Immediately after its:
```python
        self_section=build_self_section(get_memory_sheet(req.bot_name, "self")),
```
add:
```python
        identity_section=build_identity_section(get_memory_sheet(req.bot_name, "identity")),
```

- [ ] **Step 4: Verify the module imports and the suite is green**

Run: `venv/bin/python -c "import main; print('ok')"`
Expected: `ok` (no KeyError/format errors at import).
Run: `venv/bin/pytest -q`
Expected: PASS (whole suite green).

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat(brain): inject identity_section into /chat and /tick prompts"
```

---

## Task 5: `council.py` — pure parsers + deterministic merge

**Files:**
- Create: `council.py`
- Test: `tests/test_council.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_council.py
import json
from council import parse_nudges, parse_edits, merge_nudges


# ── parse_nudges ─────────────────────────────────────────────────────────────

def test_parse_nudges_valid_and_clamped():
    raw = json.dumps([
        {"subject": "Pugs", "content": "done with pugs", "weight_delta": 9},
        {"subject": "mood", "content": "lighter lately", "weight_delta": -1},
    ])
    out = parse_nudges(raw)
    assert out == [
        {"subject": "pugs", "content": "done with pugs", "weight_delta": 3},   # clamped, lowercased
        {"subject": "mood", "content": "lighter lately", "weight_delta": -1},
    ]


def test_parse_nudges_drops_bad():
    raw = json.dumps([{"subject": "x"}, {"content": "y"}, "garbage",
                      {"subject": "ok", "content": "good"}])
    assert parse_nudges(raw) == [{"subject": "ok", "content": "good", "weight_delta": 1}]


def test_parse_nudges_bad_json():
    assert parse_nudges("nope") == []
    assert parse_nudges(json.dumps({"not": "a list"})) == []


# ── parse_edits ──────────────────────────────────────────────────────────────

def test_parse_edits_valid_and_clamped():
    raw = json.dumps([{"subject": "Outlook", "content": "cynical", "weight": 99}])
    assert parse_edits(raw) == [{"subject": "outlook", "content": "cynical", "weight": 5}]


def test_parse_edits_weight_zero_is_drop_content_optional():
    raw = json.dumps([{"subject": "gone", "weight": 0}])
    assert parse_edits(raw) == [{"subject": "gone", "content": "", "weight": 0}]


def test_parse_edits_drops_contentless_positive():
    raw = json.dumps([{"subject": "x", "weight": 3}])  # positive weight needs content
    assert parse_edits(raw) == []


# ── merge_nudges (deterministic fallback) ────────────────────────────────────

def test_merge_adds_new_and_strengthens_existing():
    current = [{"subject": "pugs", "content": "wary of pugs", "weight": 2}]
    nudges = [
        {"subject": "pugs", "content": "done with pugs", "weight_delta": 2},  # 2+2 -> 4
        {"subject": "music", "content": "into metal lately", "weight_delta": 1},  # new
    ]
    edits = {e["subject"]: e for e in merge_nudges(current, nudges)}
    assert edits["pugs"]["weight"] == 4
    assert edits["pugs"]["content"] == "done with pugs"
    assert edits["music"] == {"subject": "music", "content": "into metal lately", "weight": 1}


def test_merge_negative_delta_can_drop_to_zero():
    current = [{"subject": "grind", "content": "obsessed with grinding", "weight": 1}]
    nudges = [{"subject": "grind", "content": "", "weight_delta": -3}]  # 1-3 -> 0
    edits = merge_nudges(current, nudges)
    assert edits == [{"subject": "grind", "content": "obsessed with grinding", "weight": 0}]
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/bin/pytest tests/test_council.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'council'`).

- [ ] **Step 3: Create `council.py` with the pure layer**

```python
"""The council engine: diverse-personality reflection that drives a bot's identity drift.

Repurposes the project's `summarize`-style seam from CRITIC to ENGINE. Three diverse
persona "lenses" PROPOSE nudges to the bot's identity; a SYNTHESIS step reconciles the
(deliberately conflicting) nudges into concrete identity edits, applied to the writable
`kind='identity'` layer. Pure parsing/merge + injectable model seams (propose/synthesize),
mirroring consolidate.py / self_memory.py. No Ollama in tests — they inject fakes. A Claude
backend can swap in later behind the same signatures.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

_MAX_IDENTITY = 16
_WD_MIN, _WD_MAX = -3, 3      # weight_delta clamp (nudges)
_W_MIN, _W_MAX = 0, 5         # absolute facet weight clamp (edits); 0 == drop


def parse_nudges(raw: str) -> list[dict]:
    """One persona's output -> validated nudges [{subject, content, weight_delta}].
    Subject lowercased; weight_delta coerced+clamped; bad/empty entries dropped. Never raises."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject, content = item.get("subject"), item.get("content")
        if not subject or not content:
            continue
        try:
            wd = int(item.get("weight_delta", 1))
        except (TypeError, ValueError):
            wd = 1
        out.append({"subject": str(subject).strip().lower(),
                    "content": str(content).strip(),
                    "weight_delta": max(_WD_MIN, min(_WD_MAX, wd))})
    return out


def parse_edits(raw: str) -> list[dict]:
    """Synthesis output -> validated edits [{subject, content, weight}]. weight clamped
    [0,5]; weight 0 = DROP (content optional). Positive weight requires content. Never raises."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject")
        if not subject:
            continue
        try:
            w = int(item.get("weight", 1))
        except (TypeError, ValueError):
            w = 1
        w = max(_W_MIN, min(_W_MAX, w))
        content = (item.get("content") or "").strip()
        if not content and w > 0:
            continue
        out.append({"subject": str(subject).strip().lower(), "content": content, "weight": w})
    return out


def merge_nudges(current: list[dict], nudges: list[dict]) -> list[dict]:
    """Deterministic fallback synthesis (no LLM). Same-subject nudges sum weight_delta; last
    non-empty content wins. new_weight = clamp(old_weight + summed_delta, 0, 5). Returns edits.
    Used when the synthesis model returns nothing parseable, so a cycle never silently no-ops."""
    cur = {str(f["subject"]).strip().lower():
           {"content": (f.get("content") or "").strip(), "weight": int(f.get("weight", 1) or 1)}
           for f in current}
    agg: dict[str, dict] = {}
    for n in nudges:
        a = agg.setdefault(n["subject"], {"delta": 0, "content": ""})
        a["delta"] += n["weight_delta"]
        if n["content"]:
            a["content"] = n["content"]
    edits = []
    for s, a in agg.items():
        old_w = cur.get(s, {}).get("weight", 0)
        new_w = max(_W_MIN, min(_W_MAX, old_w + a["delta"]))
        content = a["content"] or cur.get(s, {}).get("content", "")
        if new_w > 0 and not content:
            continue
        edits.append({"subject": s, "content": content, "weight": new_w})
    return edits
```

- [ ] **Step 4: Run to verify pass**

Run: `venv/bin/pytest tests/test_council.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add council.py tests/test_council.py
git commit -m "feat(council): pure nudge/edit parsers + deterministic merge fallback"
```

---

## Task 6: `council.py` — personas, digest, apply, `run_reflection` (BDD)

**Files:**
- Modify: `council.py` (append personas, digest builders, `apply_edits`, `run_reflection`, Ollama seams)
- Create: `tests/features/council_reflection.feature`
- Create: `tests/test_council_reflection_bdd.py`

- [ ] **Step 1: Write the feature file**

```gherkin
# tests/features/council_reflection.feature
Feature: The council drives a bot's identity drift
  As the evolution engine
  I want diverse personas' nudges synthesized into identity edits
  So that a bot grows beyond its template across reflections

  Scenario: A reflection adds synthesized facets to a blank identity
    Given a fresh memory db with bot "Geysse" who has said a few things
    When the council reflects with fakes that synthesize "pugs:done with pugs:3" and "music:into metal:2"
    Then bot "Geysse" identity has facet "pugs" with weight 3
    And bot "Geysse" identity has facet "music" with weight 2

  Scenario: Identity accumulates and strengthens across two reflections
    Given a fresh memory db with bot "Geysse" who has said a few things
    And bot "Geysse" already has identity facet "pugs" content "wary" weight 2
    When the council reflects with a fake that proposes nudge "pugs:done with pugs:2" and falls back to merge
    Then bot "Geysse" identity has facet "pugs" with weight 4

  Scenario: A reflection prunes weak facets beyond the cap
    Given a fresh memory db with bot "Geysse" who has said a few things
    And bot "Geysse" has 16 weak identity facets at weight 1
    When the council reflects with fakes that synthesize "anchor:a strong new thing:5"
    Then bot "Geysse" has at most 16 identity facets
    And bot "Geysse" identity has facet "anchor" with weight 5
```

- [ ] **Step 2: Write the step file**

```python
# tests/test_council_reflection_bdd.py
import json
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

import council

scenarios("features/council_reflection.feature")


@pytest.fixture
def context():
    return {}


@given(parsers.parse('a fresh memory db with bot "{bot}" who has said a few things'))
def _fresh(context, tmp_path, monkeypatch, bot):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    db.save_message(bot, "Gus", "user", "rough day?")
    db.save_message(bot, "Gus", "assistant", "ugh these pugs keep ninja looting")
    context["db"] = db
    context["bot"] = bot


@given(parsers.parse('bot "{bot}" already has identity facet "{subj}" content "{content}" weight {w:d}'))
def _seed_facet(context, bot, subj, content, w):
    context["db"].upsert_memory(bot, "identity", subj, content, weight=w)


@given(parsers.parse('bot "{bot}" has 16 weak identity facets at weight 1'))
def _seed_many(context, bot):
    for i in range(16):
        context["db"].upsert_memory(bot, "identity", f"w{i}", f"weak thing {i}", weight=1)


def _edits_from_spec(spec):
    # "subj:content:weight;subj:content:weight"
    out = []
    for part in spec.split(";"):
        s, c, w = part.split(":")
        out.append({"subject": s, "content": c, "weight": int(w)})
    return out


@when(parsers.parse('the council reflects with fakes that synthesize "{a}" and "{b}"'))
def _reflect_synth(context, a, b):
    edits = _edits_from_spec(f"{a};{b}")
    context["applied"] = council.run_reflection(
        context["bot"],
        propose=lambda *args, **kw: "[]",
        synthesize=lambda *args, **kw: json.dumps(edits),
        council=[council.Persona("X", "x")],
    )


@when(parsers.parse('the council reflects with fakes that synthesize "{a}"'))
def _reflect_synth_one(context, a):
    edits = _edits_from_spec(a)
    context["applied"] = council.run_reflection(
        context["bot"],
        propose=lambda *args, **kw: "[]",
        synthesize=lambda *args, **kw: json.dumps(edits),
        council=[council.Persona("X", "x")],
    )


@when(parsers.parse('the council reflects with a fake that proposes nudge "{subj}:{content}:{wd:d}" and falls back to merge'))
def _reflect_merge(context, subj, content, wd):
    nudge = [{"subject": subj, "content": content, "weight_delta": wd}]
    context["applied"] = council.run_reflection(
        context["bot"],
        propose=lambda *args, **kw: json.dumps(nudge),
        synthesize=lambda *args, **kw: "garbage-not-json",  # forces merge fallback
        council=[council.Persona("X", "x")],
    )


@then(parsers.parse('bot "{bot}" identity has facet "{subj}" with weight {w:d}'))
def _has_facet(context, bot, subj, w):
    rows = {r["subject"]: r for r in context["db"].get_memory_sheet(bot, "identity")}
    assert subj in rows, f"{subj} not in {list(rows)}"
    assert rows[subj]["weight"] == w


@then(parsers.parse('bot "{bot}" has at most {n:d} identity facets'))
def _at_most(context, bot, n):
    assert len(context["db"].get_memory_sheet(bot, "identity")) <= n
```

- [ ] **Step 3: Run to verify fail**

Run: `venv/bin/pytest tests/test_council_reflection_bdd.py -v`
Expected: FAIL (`AttributeError: module 'council' has no attribute 'Persona'`).

- [ ] **Step 4: Append the engine to `council.py`**

```python
import httpx

import db
from config import OLLAMA_URL, OLLAMA_MODEL


@dataclass(frozen=True)
class Persona:
    name: str
    lens: str   # the system-prompt that gives this council member its distinct taste


COUNCIL: list[Persona] = [
    Persona("Edge",
            "You are The Edge, on a council that shapes who a WoW player is becoming. "
            "Push them toward SHARPER, more SPECIFIC opinions, tastes, grudges, and "
            "in-jokes — the little stances that make a person not generic. Don't make "
            "them mean; make them particular."),
    Persona("Heart",
            "You are The Heart, on a council that shapes who a WoW player is becoming. "
            "Push their RELATIONSHIPS forward — who they bond with, clash with, drift "
            "from — and how those people change them. Root changes in who they spend "
            "time with."),
    Persona("Arc",
            "You are The Arc, on a council that shapes who a WoW player is becoming. Your "
            "job is NARRATIVE CONTINUITY — a believable through-line over time (burnout, a "
            "comeback, getting hooked on something, a mood that trends) that stays "
            "consistent with who they've been becoming."),
]


def build_life_digest(bot_name: str, *, recent_limit: int = 20) -> str:
    """The 'recent life' the council reads: recent chat across everyone + relationship notes."""
    msgs = db.get_recent_messages(bot_name, limit=recent_limit)
    convo = "\n".join(
        f"{'You' if m['role'] == 'assistant' else m['player_name']}: {m['content']}"
        for m in msgs) or "(quiet stretch — not much said)"
    rels = db.get_memory_sheet(bot_name, "relationship")
    rel_txt = "; ".join(f"{r['subject']}: {r['content']}" for r in rels) or "(no one in particular yet)"
    return f"RECENT CHAT:\n{convo}\n\nPEOPLE YOU KNOW: {rel_txt}"


def _format_identity(facets: list[dict]) -> str:
    if not facets:
        return "(blank slate — they haven't grown into anyone specific yet)"
    return "; ".join(f"{f['subject']} (w{f.get('weight', 1)}): {f['content']}" for f in facets)


def apply_edits(bot_name: str, edits: list[dict]) -> list[dict]:
    """Apply edits to the writable identity layer, then prune to the strongest _MAX_IDENTITY.
    weight 0 deletes the facet. Returns the edits applied."""
    for e in edits:
        if e["weight"] <= 0:
            db.delete_memory(bot_name, "identity", e["subject"])
        else:
            db.upsert_memory(bot_name, "identity", e["subject"], e["content"], e["weight"])
    db.prune_memory_by_weight(bot_name, "identity", keep=_MAX_IDENTITY)
    return edits


def local_propose(persona: Persona, digest: str, current_identity: str, who: str) -> str:
    """Default backend: one Ollama call per persona. Never called in tests."""
    system = (
        f"{persona.lens}\n\nThe person at their core: {who}\n"
        f"Who they've been becoming: {current_identity}\n\n"
        "Propose 1-3 nudges to who they are, as ONLY a JSON list, each "
        '{"subject": one-or-two-word key, "content": a short first-person line, '
        '"weight_delta": -3..3}. Positive = lean into it; negative = it\'s fading. Ground '
        "every nudge in the recent life below. No prose, JSON only.")
    resp = httpx.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL, "think": False, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": digest}],
        "options": {"num_predict": 220, "temperature": 0.7},
    }, timeout=60.0)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def local_synthesize(current_identity: str, all_nudges: list[dict], who: str) -> str:
    """Default backend: one Ollama call reconciling the council's competing nudges. Never
    called in tests."""
    system = (
        "You reconcile a council's competing suggestions about who a WoW player is becoming "
        "into a final, coherent identity update. They disagree on purpose — keep what's "
        "true, let real tensions stand as part of the person, drop what no longer fits. "
        "Output ONLY a JSON list of facets to set, each {\"subject\": key, \"content\": "
        "short first-person line, \"weight\": 1..5}. Use weight 0 to DROP a facet. Keep it "
        f"human and specific, not a committee average.\n\nAt their core: {who}\n"
        f"Current identity: {current_identity}")
    user = "COUNCIL SUGGESTIONS:\n" + json.dumps(all_nudges, indent=2)
    resp = httpx.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL, "think": False, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "options": {"num_predict": 320, "temperature": 0.5},
    }, timeout=90.0)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def run_reflection(bot_name: str, *, who: str = "", propose=None, synthesize=None,
                   recent_limit: int = 20, council: list[Persona] | None = None) -> list[dict]:
    """One council reflection cycle for one bot. propose/synthesize resolve at CALL time so
    tests inject fakes. Returns the applied identity edits.

    propose(persona, digest, current_identity_str, who) -> raw JSON str (nudges)
    synthesize(current_identity_str, all_nudges, who)    -> raw JSON str (edits)
    """
    if propose is None:
        propose = local_propose
    if synthesize is None:
        synthesize = local_synthesize
    if council is None:
        council = COUNCIL
    if not who:
        who = db.get_who(bot_name)

    facets = db.get_memory_sheet(bot_name, "identity")
    digest = build_life_digest(bot_name, recent_limit=recent_limit)
    cur_str = _format_identity(facets)

    all_nudges: list[dict] = []
    for persona in council:
        all_nudges.extend(parse_nudges(propose(persona, digest, cur_str, who)))

    edits = parse_edits(synthesize(cur_str, all_nudges, who))
    if not edits:
        edits = merge_nudges(facets, all_nudges)
    return apply_edits(bot_name, edits)
```

- [ ] **Step 5: Run to verify pass**

Run: `venv/bin/pytest tests/test_council_reflection_bdd.py -v`
Expected: PASS (3 scenarios passed).

- [ ] **Step 6: Commit**

```bash
git add council.py tests/features/council_reflection.feature tests/test_council_reflection_bdd.py
git commit -m "feat(council): personas + digest + run_reflection engine (BDD)"
```

---

## Task 7: `sim/accelerated_life.py` — the day loop + observation (BDD)

**Files:**
- Create: `sim/accelerated_life.py`
- Create: `tests/features/accelerated_life.feature`
- Create: `tests/test_accelerated_life_bdd.py`

- [ ] **Step 1: Write the feature file**

```gherkin
# tests/features/accelerated_life.feature
Feature: Accelerated-life harness compresses days of evolution
  As the evolution lab
  I want N days of (live a scene -> reflect) run offline against a fake brain
  So that I can watch identity accumulate without waiting real days

  Scenario: Running K days writes K trail records and accumulates identity
    Given a fresh memory db
    And a fake brain and a fake reflection that adds one facet per day
    When I run accelerated life for bot "Geysse" for 3 days
    Then the trail has 3 day records
    And bot "Geysse" has 3 identity facets

  Scenario: day_plan rotates and never pairs a bot with itself
    When I build day plans for bot "Geysse" for days 0 1 2 3 4
    Then no day plan has partner "Geysse"
    And at least two distinct locations appear
```

- [ ] **Step 2: Write the step file**

```python
# tests/test_accelerated_life_bdd.py
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.accelerated_life import run_accelerated_life, day_plan
from sim.transcript import Scene, Turn

scenarios("features/accelerated_life.feature")


@pytest.fixture
def context():
    return {}


class FakeBrain:
    def chat(self, bot, player, msg, ch="SAY", loc="", recent_lines=None):
        return {"message": f"{bot}: hi {player}", "channel": ch, "actions": []}
    def tick(self, bot, loc="", nearby_players=None, nearby_bots=None, recent_lines=None):
        return {"message": f"{bot} mutters", "channel": "SAY", "actions": []}


@given("a fresh memory db")
def _fresh(context, tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    context["db"] = db


@given("a fake brain and a fake reflection that adds one facet per day")
def _fakes(context):
    context["brain"] = FakeBrain()
    calls = {"n": 0}
    def fake_reflect(bot, **kw):
        calls["n"] += 1
        i = calls["n"]
        context["db"].upsert_memory(bot, "identity", f"day{i}", f"thing {i}", weight=i)
        return [{"subject": f"day{i}", "content": f"thing {i}", "weight": i}]
    context["reflect"] = fake_reflect


@when(parsers.parse('I run accelerated life for bot "{bot}" for {days:d} days'))
def _run(context, tmp_path, bot, days):
    context["summary"] = run_accelerated_life(
        context["brain"], bot, days, run_dir=tmp_path / "run", reflect=context["reflect"])


@then(parsers.parse("the trail has {n:d} day records"))
def _trail(context, n):
    assert len(context["summary"]["trail"]) == n


@then(parsers.parse('bot "{bot}" has {n:d} identity facets'))
def _facets(context, bot, n):
    assert len(context["db"].get_memory_sheet(bot, "identity")) == n


@when(parsers.parse('I build day plans for bot "{bot}" for days {a:d} {b:d} {c:d} {d:d} {e:d}'))
def _plans(context, bot, a, b, c, d, e):
    context["plans"] = [day_plan(bot, i) for i in (a, b, c, d, e)]


@then(parsers.parse('no day plan has partner "{bot}"'))
def _no_self(context, bot):
    assert all(p.partner != bot for p in context["plans"])


@then("at least two distinct locations appear")
def _locs(context):
    assert len({p.location for p in context["plans"]}) >= 2
```

- [ ] **Step 3: Run to verify fail**

Run: `venv/bin/pytest tests/test_accelerated_life_bdd.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'sim.accelerated_life'`).

- [ ] **Step 4: Create `sim/accelerated_life.py`**

```python
"""Accelerated-life harness: compress many simulated 'days' of a bot's life into a fast,
offline run so we can watch its identity drift under the council engine.

A "day" = LIVE a rotating scene (sim.scene_runner) against an experiment brain, then
REFLECT (council.run_reflection). State persists across days in the brain's DB; identity +
relationships accumulate. Verification is eyeball: a per-day trail, a fixed before/after
probe, and a day-0-vs-day-N identity diff.

Run (the harness process MUST point db at the same file the brain uses):
    WBB_DB_PATH=/tmp/wbb-evo.db venv/bin/python -m sim.accelerated_life \\
        --bot Geysse --days 10 --brain-url http://127.0.0.1:5001 --run geysse1
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import db
from sim.scene_runner import run_scene


@dataclass(frozen=True)
class DayScene:
    location: str
    channel: str
    partner: str
    player: str | None


# (location, channel, player) rotation — varied days, some ambient (no player).
_LOCATIONS = [
    ("Stormwind", "SAY", "Gus"),
    ("Westfall", "GENERAL", "Gus"),
    ("Elwynn Forest", "SAY", None),
    ("Stormwind", "GENERAL", "Gus"),
    ("Goldshire", "SAY", "Gus"),
]
_PARTNER_POOL = ["Lynea", "Geysse"]


def day_plan(bot: str, day_idx: int) -> DayScene:
    """A varied scene for `day_idx`; partner is always someone other than `bot`."""
    loc, channel, player = _LOCATIONS[day_idx % len(_LOCATIONS)]
    partner = next(p for p in _PARTNER_POOL if p != bot)
    return DayScene(location=loc, channel=channel, partner=partner, player=player)


PROBE_QUESTIONS = [
    "hey, tell me about yourself",
    "what have you been up to lately?",
    "got any strong opinions these days?",
]


def probe_bot(brain, bot: str, questions=PROBE_QUESTIONS) -> list[dict]:
    out = []
    for q in questions:
        resp = brain.chat(bot, "Gus", q, "SAY", "Stormwind")
        out.append({"q": q, "a": (resp.get("message") or "").strip()})
    return out


def run_day(brain, bot: str, day_idx: int, *, reflect=None) -> dict:
    """Live one rotating scene, then run one council reflection. Returns a trail record."""
    plan = day_plan(bot, day_idx)
    run_scene(brain, scene_id=f"evo-d{day_idx}", location=plan.location,
              channel=plan.channel, bots=[bot, plan.partner], player=plan.player,
              turns=8, seed=1000 + day_idx, consolidate=True)
    if reflect is None:
        from council import run_reflection
        reflect = run_reflection
    edits = reflect(bot)
    facets = db.get_memory_sheet(bot, "identity")
    return {"day": day_idx, "applied_edits": edits, "identity_facets": facets}


def _diff_identity(day0: list[dict], dayN: list[dict]) -> dict:
    a = {f["subject"]: f for f in day0}
    b = {f["subject"]: f for f in dayN}
    added = [b[s] for s in b if s not in a]
    dropped = [a[s] for s in a if s not in b]
    changed = [{"subject": s, "from": a[s]["content"], "to": b[s]["content"]}
               for s in b if s in a and a[s]["content"] != b[s]["content"]]
    return {"added": added, "dropped": dropped, "changed": changed}


def _render_report(bot, baseline_probe, final_probe, day0, dayN, diff) -> str:
    L = [f"# Evolution run — {bot}", "", "## Identity diff (day 0 → day N)", ""]
    L.append(f"**Added ({len(diff['added'])}):**")
    L += [f"- {f['subject']} (w{f['weight']}): {f['content']}" for f in diff["added"]] or ["- (none)"]
    L.append(f"\n**Changed ({len(diff['changed'])}):**")
    L += [f"- {c['subject']}: \"{c['from']}\" → \"{c['to']}\"" for c in diff["changed"]] or ["- (none)"]
    L.append(f"\n**Dropped ({len(diff['dropped'])}):**")
    L += [f"- {f['subject']}: {f['content']}" for f in diff["dropped"]] or ["- (none)"]
    L.append("\n## Fixed probe — day 0 vs day N\n")
    for b0, bn in zip(baseline_probe, final_probe):
        L += [f"**Q: {b0['q']}**", f"- day 0: {b0['a']}", f"- day N: {bn['a']}", ""]
    return "\n".join(L)


def run_accelerated_life(brain, bot: str, n_days: int, *, run_dir, reflect=None) -> dict:
    """Probe (baseline) → N days of (live + reflect), trailing each day → probe (final) →
    write trail.jsonl + probe/report. Returns {trail, diff, ...}. `reflect` is injectable."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    baseline_probe = probe_bot(brain, bot)
    day0 = db.get_memory_sheet(bot, "identity")

    trail = []
    with (run_dir / "trail.jsonl").open("w") as fh:
        for d in range(1, n_days + 1):
            rec = run_day(brain, bot, d, reflect=reflect)
            trail.append(rec)
            fh.write(json.dumps(rec, default=str) + "\n")

    dayN = db.get_memory_sheet(bot, "identity")
    final_probe = probe_bot(brain, bot)
    diff = _diff_identity(day0, dayN)

    (run_dir / "REPORT.md").write_text(
        _render_report(bot, baseline_probe, final_probe, day0, dayN, diff))
    (run_dir / "probe.md").write_text(json.dumps(
        {"baseline": baseline_probe, "final": final_probe}, indent=2))

    return {"bot": bot, "days": n_days, "trail": trail, "diff": diff,
            "baseline_probe": baseline_probe, "final_probe": final_probe}


if __name__ == "__main__":
    import argparse
    from sim.brain_client import BrainClient
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", required=True)
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--brain-url", default="http://127.0.0.1:5001")
    ap.add_argument("--run", default="run1")
    args = ap.parse_args()
    brain = BrainClient(args.brain_url)
    summary = run_accelerated_life(brain, args.bot, args.days,
                                   run_dir=Path("eval/evolution") / args.run)
    print(f"\n=== {summary['bot']} after {summary['days']} days ===")
    print(f"added {len(summary['diff']['added'])}, changed {len(summary['diff']['changed'])}, "
          f"dropped {len(summary['diff']['dropped'])} facets")
    print(f"see eval/evolution/{args.run}/REPORT.md")
```

- [ ] **Step 5: Run to verify pass**

Run: `venv/bin/pytest tests/test_accelerated_life_bdd.py -v`
Expected: PASS (2 scenarios passed).

- [ ] **Step 6: Run the whole suite green**

Run: `venv/bin/pytest -q`
Expected: PASS (all tests, including pre-existing, green).

- [ ] **Step 7: Commit**

```bash
git add sim/accelerated_life.py tests/features/accelerated_life.feature tests/test_accelerated_life_bdd.py
git commit -m "feat(sim): accelerated-life harness (day loop, probe, identity diff) (BDD)"
```

---

## Task 8: Live verification run (manual — not a unit test)

**This is the eyeball success gate from the spec.** Requires Ollama on `<ollama-host>` and the game DB container up.

- [ ] **Step 1: Ensure the game DB is up** (else bots fall back to L1 Human)

Run: `docker ps --format '{{.Names}}' | grep ac-database || docker start ac-database`
Expected: `ac-database` listed/started.

- [ ] **Step 2: Start the experiment brain on :5001 with a fresh evo DB, self-reflect OFF**

We isolate council-driven drift from the brain's built-in self-reflection.
```bash
rm -f /tmp/wbb-evo.db
cd ~/wow-bot-brain
WBB_DB_PATH=/tmp/wbb-evo.db WBB_SELF_REFLECT=0 WBB_GUILD_ACTIONS=1 \
  setsid nohup venv/bin/uvicorn main:app --host 127.0.0.1 --port 5001 \
  >/tmp/wbb-evo-brain.log 2>&1 &
sleep 4 && curl -s 127.0.0.1:5001/bots | head -c 200
```
Expected: brain responds. (NEVER `pkill uvicorn` — it returns 144 and can kill the prod brain. Find this brain's PID from the log / `lsof -i:5001` if you must stop it.)

- [ ] **Step 2.5: Confirm the bot resolves to a real identity (not L1 Human)**

```bash
curl -s -X POST 127.0.0.1:5001/chat -H 'content-type: application/json' \
  -d '{"bot_name":"Geysse","player_name":"Gus","message":"hey","channel":"SAY","location":"Stormwind"}'
```
Expected: an in-character reply; the brain log shows `Geysse (L16 Dwarf Rogue ...)` not `L1 Human`. If L1 Human, the game DB isn't reachable — fix before continuing.

- [ ] **Step 3: Run accelerated life for one bot, 10 days**

```bash
WBB_DB_PATH=/tmp/wbb-evo.db venv/bin/python -m sim.accelerated_life \
  --bot Geysse --days 10 --brain-url http://127.0.0.1:5001 --run geysse1
```
Expected: completes in a few minutes; prints facet counts; writes `eval/evolution/geysse1/REPORT.md`.

- [ ] **Step 4: Read the result and judge it**

Run: `cat eval/evolution/geysse1/REPORT.md`
Success criterion (eyeball): the day-N identity has facets that grew out of the run, the day-0-vs-day-N probe shows a recognizably *different but still believable* person, and nothing breaks the vanilla game-world gate (no expansions/anachronisms in-game).
If drift is too weak: bump `--days`, or note it for tuning (persona temps / nudge strength) in the morning report — do not silently change the design.

- [ ] **Step 5: Commit the run artifacts**

```bash
git add eval/evolution/geysse1/
git commit -m "eval: first accelerated-life evolution run (Geysse, 10 days)"
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Writable identity layer (kind='identity', augments template, pruned by weight) → Tasks 1, 2, 6 (`apply_edits` + `prune_memory_by_weight`, cap 16). ✓
- Prompt read path `{identity_section}` + game-locked/person-open framing → Tasks 2, 3, 4. ✓
- Council engine: 3 diverse personas, propose (diverse), synthesize (reconcile), deterministic fallback, injectable seam → Tasks 5, 6. ✓
- Accelerated-life harness: rotating day scenes, live+reflect, persistence, trail → Task 7. ✓
- Observation: trail.jsonl, fixed probe, day0-vs-dayN diff, REPORT.md → Task 7. ✓
- Cross-process write path = direct shared-DB writes; brain only reads → Task 4 (read) + Task 8 launch (both point at /tmp/wbb-evo.db). ✓
- Eyeball verification gate; self-reflect OFF to isolate; game DB up → Task 8. ✓
- Scope fences (no live promotion, no event memory, Ollama only, one bot) → respected (live brain untouched; runs on :5001). ✓

**Placeholder scan:** none — every code/step is concrete.

**Type consistency:** nudge `{subject, content, weight_delta}`; edit `{subject, content, weight}`; `Persona(name, lens)`; `run_reflection(bot, *, who, propose, synthesize, recent_limit, council)`; `DayScene(location, channel, partner, player)`. Names match across tasks. `prune_memory_by_weight`, `delete_memory`, `get_who`, `build_identity_section` consistent. ✓
