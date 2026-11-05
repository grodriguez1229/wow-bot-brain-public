# Shared Memory — Phase 1 (Foundation) Design

**Date:** 2026-06-13
**Status:** Approved (design); pending implementation plan.
**Repo:** `wow-bot-brain` (local-only, no remotes — private per project rule).

## Motivation

Cycle-2 evaluation (`eval/bakeoff/REPORT.md`) established that prompt/template wording
tweaks inside the optimizer whitelist cannot break the ~2.2 believability ceiling. The
bottleneck is **architectural**: the `/tick` endpoint is stateless and `/chat` memory is
strictly pairwise (`get_memory(bot, player)`), so bots cannot react to what is being said
*around* them. With no human present every turn is a blind `/tick`, and scenes collapse
into WTB/LFG classified-ad broadcast (no-player ambient scenes scored ~1.5).

The fix is **shared memory**: give bots awareness of nearby conversation (short-term) and
a durable, evolving record of the people/world they experience (long-term). This is a
large, multi-layer system, so it is **phased**. This spec covers **Phase 1 only**.

## Goal of Phase 1

Build the two foundational memory layers plus the write-path machinery that later layers
reuse, with the **biggest believability win per unit of risk** and **without corrupting
eval attribution**:

1. **Short-term "overheard" layer** — caller-passed, ephemeral. Stops broadcast spam.
2. **Relationship layer** — brain-owned, persistent. Enriches the existing relationships
   table with notes/feelings, not just a familiarity counter.
3. **Consolidation skeleton** — the write path. After a scene, an LLM pass turns the
   transcript into durable memory updates. Phase 1 wires exactly ONE layer
   (relationships) end-to-end to prove the interface.

Architecture chosen: **Approach 1 — sheets + consolidation pass**, borrowing the
caller-passed trick (Approach 3) for the short-term layer only.

## Non-goals (Phase 1)

Out of scope, deferred to Phase 2+:
- Events / "what happened" memory layer.
- Places / world-state memory layer.
- Evolving self-concept / personality-opinion layer.
- Embedding / RAG retrieval.
- Live-game C++ wiring (the C++ `LlmBridge` passing nearby chat).
- The multi-agent personality-critique pipeline (separate future project; the
  consolidation `summarize` interface is the seam it will later plug into).

## Architecture

Layered memory. Phase 1 implements the bottom two layers and the consolidation seam;
Phase 2+ layers attach to the same sheet store and consolidation skeleton.

```
            ┌─────────────────────────────────────────────┐
 request →  │  /chat, /tick                                │
            │   ├─ short-term: req.recent_lines (caller)   │  ephemeral
            │   └─ long-term:  relationship slice (DB)      │  persistent
            │  → prompt sections → local LLM → BotResponse  │
            └─────────────────────────────────────────────┘
 end of scene:
            ┌─────────────────────────────────────────────┐
            │  consolidate_scene(scene, summarize=...)      │
            │   reads transcript → per-bot relationship     │
            │   note/familiarity updates → bot_memory sheet │
            └─────────────────────────────────────────────┘
```

### Component: `models.py`
Add an optional field to both request models:

```python
class RecentLine(BaseModel):
    speaker: str
    text: str

class ChatRequest(BaseModel):
    ...
    recent_lines: Optional[list[RecentLine]] = None  # last N things said nearby

class TickRequest(BaseModel):
    ...
    recent_lines: Optional[list[RecentLine]] = None
```

The brain stays **stateless** about the short-term layer — it consumes whatever the
caller supplies. This matches the existing design where the orchestrator (sim now, C++
later) owns proximity/turn order.

### Component: `prompts.py`
Add a `{nearby_section}` placeholder to **both** `CHAT_PROMPT` and `TICK_PROMPT`. The
TICK addition is the high-value change (today TICK is fully blind). Rendered form:

```
OVERHEARD NEARBY (react to this, don't repeat it):
  Lynea: anyone running Deadmines?
  Geysse: nah im broke, gotta grind first
```

When `recent_lines` is empty the section renders empty (current behavior preserved).
Also start injecting the relationship `notes` field (currently dead) into the existing
memory/context section so persistent relationship colour reaches the prompt.

A small pure builder function (e.g. `build_nearby_section(recent_lines) -> str`) keeps
this unit-testable without an LLM.

### Component: `db.py`
1. New `bot_memory` table — the durable "sheet" store. Phase 1 actively uses the
   relationship slice; columns for the dormant layers are created but unused:

```sql
CREATE TABLE IF NOT EXISTS bot_memory (
    bot_name   TEXT NOT NULL,
    kind       TEXT NOT NULL,   -- 'relationship' (P1) | 'event' | 'place' | 'self' (P2+)
    subject    TEXT NOT NULL,   -- e.g. the other person's name, a zone, '' for self
    content    TEXT NOT NULL,   -- free-text memory note
    weight     INTEGER DEFAULT 1,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bot_name, kind, subject)
);
```

2. Add `set_relationship_notes(bot_name, player_name, notes)` and begin populating the
   existing `relationships.notes` column.
3. Idempotent `CREATE TABLE IF NOT EXISTS` + `ALTER ... ` migration pattern, consistent
   with the existing `init_db()`.

### Component: `consolidate.py` (new)
The write path.

```python
def consolidate_scene(scene, *, summarize=local_summarize, db=...) -> list[MemoryUpdate]:
    """Read a finished Scene transcript; for each bot, derive relationship
    note/familiarity updates and persist them. `summarize` is an injectable
    callable (transcript_slice -> structured update) so tests can mock it and
    a richer backend (Claude / critique agents) can be swapped in later."""
```

- Default `summarize` = a local-model call (cheap, runs in the world loop).
- The callable seam is the **only** integration point the future fan-out critique agents
  need — they implement the same `summarize` signature with a richer backend.
- Parsing of the summarizer output is a pure function (unit-testable).
- Also exposed as a `/reflect` endpoint for the orchestrator to call post-scene.

### Component: `sim/brain_client.py`
`chat()` and `tick()` accept and forward `recent_lines` in the JSON payload.

### Component: `sim/scene_runner.py`
- Maintain the rolling transcript (already does via `recorded`); pass the last N lines
  (excluding the speaker's own last line) as `recent_lines` on each chat/tick call.
- After the scene completes, call `consolidate_scene(scene)` — gated by a
  `consolidate=False` default so the scored eval path leaves it OFF (see Eval section).

## Data flow

1. **Per turn:** scene_runner sends the last N nearby lines → brain renders
   `{nearby_section}` + relationship slice → local LLM → `BotResponse`.
2. **End of scene (world run only):** `consolidate_scene` reads the transcript → per-bot
   relationship note/familiarity updates → `bot_memory` + `relationships`.

## Eval attribution (protects the optimizer loop)

Persistent memory must not make eval runs incomparable. Rules:

- **Scored eval generation runs with `consolidate=False`** (no writes during scoring).
- **A seeded, checked-in memory fixture** (`load_memory_fixture` with an explicit
  `db_path`) can be loaded into the brain's DB before each scored eval run via the
  opt-in `memory_fixture` parameter on `regen_eval`, so the relationship layer
  contributes *identically* across candidates. The short-term overheard layer is
  deterministic from the (seeded) transcript, so it adds no variance beyond what the
  seed already controls. The actual seeded bake-off run (qwen, consolidation OFF) is the
  next, human-gated step.
- **Consolidation/persistence is exercised only in a separate "world run"**, never in the
  scored eval. Fresh-DB-per-cycle attribution stays intact.
- A BDD scenario asserts that two identical eval runs from the fixture produce identical
  memory state (determinism guard).

## Testing (BDD — pytest-bdd, per the learning goal)

Feature files:
- `bot reacts to an overheard line` — short-term layer: given recent_lines, the prompt
  contains the overheard section and the (mocked-LLM) reply references it.
- `consolidation updates a relationship note` — write path with a **mocked summarizer**:
  given a transcript, `consolidate_scene` persists the expected note + familiarity bump.
- `eval memory fixture is deterministic` — attribution guard: two runs from the fixture
  yield identical `bot_memory`/`relationships`.

Unit tests: `build_nearby_section` rendering (empty/non-empty), summarizer-output parsing,
`set_relationship_notes` round-trip, migration idempotency.

## Risks & mitigations

- **Eval contamination by persistence** → consolidation OFF in scored eval + seeded
  fixture (above).
- **Prompt bloat / context cost from overheard + notes** → cap N (short-term window) and
  notes length; measure per-scene latency in the next bake-off harness run.
- **Local summarizer producing junk relationship notes** → parser validates/clamps; bad
  output is dropped, not persisted; BDD covers the happy path with a mock.
- **Migration on existing DBs** → idempotent IF NOT EXISTS / ALTER pattern already in use.

## Definition of done (Phase 1)

- `recent_lines` plumbed request → prompt for both `/chat` and `/tick`.
- `bot_memory` table + relationship notes live and injected into prompts.
- `consolidate_scene` updates the relationship layer via an injectable summarizer; exposed
  as `/reflect`.
- sim passes `recent_lines`; scored eval path leaves consolidation OFF (default).
- `load_memory_fixture` accepts an explicit `db_path` so the brain's separate-process DB
  can be seeded; `regen_eval` has an opt-in `memory_fixture` parameter that seeds the
  brain's DB before scored generation when set (default None preserves prior behavior).
- BDD + unit tests green.
- The actual seeded bake-off run (qwen, consolidation OFF) comparing against the 2.163
  baseline is the next, human-gated step; nothing runs automatically and nothing is pushed
  to any remote.
