# Bot Evolution — Slice 1: Accelerated-Life + Council Engine

**Date:** 2026-06-15
**Status:** APPROVED (user approved design 2026-06-15, then handed overnight autonomy to build it)
**Repo:** `wow-bot-brain` (local-only, no public remote)

## Goal

Make bots **genuinely evolve beyond their base personality** — drift from the template,
shaped by relationships, following a life arc, picking up opinions they weren't born with.
The user picked *all four* of those as what "evolved" should look like.

This spec is **slice 1 of a 4-part effort** (see Decomposition). Slice 1 is a thin,
end-to-end vertical slice whose success criterion is a "whoa, it's evolving" moment:
**watch one bot visibly become a different — but still believable — person, fast, offline.**

The engine of that growth is the user's own idea: a **council of diverse-personality
agents**, repurposed from *critic* to *engine*. Instead of one bland local-model
self-reflection, a panel of distinct lenses pushes each bot to grow in non-average
directions.

## Decomposition (the full system → 4 sub-projects)

1. **Accelerated-life slice (THIS SPEC):** writable identity layer + minimal diverse
   council as the reflection engine + a time-compression harness + eyeball observation.
2. **Richer experience substrate:** activate the dormant `event` memory + relationship
   accumulation with recency, so "life arc" and "relationship-shaped" have real fuel.
3. **Evolution judging + guardrails:** formal measurement that drift is *believable and
   good*, plus off-the-rails detection (the original council-as-critic idea, now QA on
   the engine).
4. **Live promotion:** wire the tuned council into the live brain with scheduled
   reflections; observe in the real game.

Each later sub-project gets its own spec → plan → build cycle.

## Guardrail: what can drift, what is locked

- **Game-world frame: LOCKED to vanilla.** No expansions, no flying mounts / Death
  Knights, level cap 60, level-appropriate *game* knowledge, no in-game anachronisms.
  The existing lore gate stays.
- **The person behind the keyboard: fully open.** They can talk about anything within the
  model's available knowledge — modern history, real-world events, culture, opinions on
  anything. They are **not** frozen in 2005 as people; only their *character's world* is
  the period piece.

Consequence: the current prompts' "real person in 2005" + "no modern slang that breaks
2005 immersion" framing is **relaxed** to game-locked / person-open. Slice 1's
*experiment brain* adopts the new framing so drift can actually surface in generated
chat. The full live lore-gate rewrite to honor this lands in sub-projects 3/4 — **slice 1
does not touch the live (`:5000`) brain or its prompts.**

## Architecture overview

```
                 accelerated-life harness  (sim/accelerated_life.py)
                 ──────────────────────────────────────────────────
  for day in 1..N:
     1. LIVE  : run rotating scenes (sim/scene_runner) vs experiment brain :5001
                → fresh transcript lines saved to /tmp/wbb-evo.db
     2. REFLECT: council.run_reflection(bot, db_path)        [the drift driver]
                 ├─ gather recent life (messages + relationships + identity)
                 ├─ N diverse personas PROPOSE nudges        (Ollama, injectable seam)
                 ├─ SYNTHESIZE nudges → concrete identity edits
                 └─ write identity facets directly to /tmp/wbb-evo.db (kind='identity')
     3. SNAPSHOT: append identity + sample lines to eval/evolution/<run>/trail.jsonl

  experiment brain :5001  (main.py, WBB_DB_PATH=/tmp/wbb-evo.db)
     reads kind='identity' → {identity_section} in CHAT/TICK prompts (read path only)
```

**Process model (critical, learned from `memory_fixture`):** the brain is a *subprocess*;
the sim/harness talks to it over HTTP. So the council **write path** writes identity
facets *directly to the shared `/tmp/wbb-evo.db` file* via `db.upsert_memory` (same trick
`sim/memory_fixture.load_memory_fixture` uses), while the brain only needs a minimal
**read path** change to inject the identity section on its next request. No new brain
endpoint is required for slice 1.

## Component 1 — The writable identity layer

**Storage:** reuse the existing generic `bot_memory` table with a **new `kind='identity'`**.
Each facet is one row: `(bot_name, 'identity', subject, content, weight, updated_at)`.
- `subject` = a stable facet key (e.g. `outlook`, `pugs`, `late-nights`, `rivalry:Lynea`).
- `content` = a short first-person line ("done with pugs after getting ninja-looted twice").
- `weight` = strength/conviction (1–5); reinforced facets gain weight, used for pruning.

**Distinct from `kind='self'`:** `self` stays the ≤4 overwriting rolling-status (mood/focus,
short horizon). `identity` is the **accumulating, drifting who-I'm-becoming** — generously
capped (`_MAX_IDENTITY = 16`), pruned by `(weight, recency)` so weak/stale facets fade but
strong ones persist. It **augments, never overwrites** the frozen `IRL_IDENTITIES` template
that seeded the bot.

**DB helpers** (in `db.py`, mirroring existing ones): identity facets reuse
`upsert_memory(bot,'identity',subject,content,weight)`, `get_memory_sheet(bot,'identity')`,
`prune_memory`. Add `prune_memory_by_weight(bot, kind, keep)` (delete lowest
`weight`, then oldest) since identity prunes by conviction, not just recency.

**Prompt read path** (`memory_prompt.py` + `prompts.py`, experiment brain):
`build_identity_section(identity_facets)` → a new `{identity_section}` placeholder in BOTH
CHAT and TICK prompts, rendered as e.g.:

```
WHO YOU'VE BECOME (this grew out of your time on the server — let it color how you talk):
- done with pugs after getting ninja-looted twice
- weirdly into late-night philosophy tangents
- soft spot for Lynea, you two always end up chatting
```

Empty facet set → empty string (a never-reflected bot prompts exactly as today).

## Component 2 — The council engine (`council.py`)

Mirrors `consolidate.py` / `self_memory.py`: **pure parsing/merge logic + an injectable
model seam**; no Ollama in tests.

### Personas (the lenses)

Three diverse lenses for slice 1, each a distinct system-prompt persona. They are
**meant to disagree** — that disagreement is what makes drift non-average and interesting.
They map onto the four evolution kinds the user picked:

- **The Edge** — pushes for sharper, more specific *opinions, tastes, grudges, in-jokes*.
  ("New opinions & interests".)
- **The Heart** — pushes for *relationship-driven* change: who the bot bonds with /
  clashes with, and how that reshapes them. ("Relationship-shaped".)
- **The Arc** — pushes for *narrative continuity*: a through-line over days (burnout, a
  comeback, getting into something), and consistency with who they were becoming.
  ("A life arc".)

"Drift from the template" is the emergent result of all three pushing over many cycles.

Persona definitions live as data (`COUNCIL = [Persona(name, lens_system_prompt), ...]`) so
the panel is trivially editable / extensible (slice 1 ships 3; nothing hard-codes "3").

### One reflection cycle — `run_reflection(bot, *, db_path, propose=None, synthesize=None)`

1. **Gather recent life:** `db.get_recent_messages(bot, limit=...)` (the day's transcript),
   `db.get_memory_sheet(bot,'relationship')`, current `db.get_memory_sheet(bot,'identity')`,
   and the frozen `who` from the personality row. Compose a compact "recent life" digest.
2. **Propose (diverse):** for each persona, `propose(persona, digest, current_identity)`
   → a small JSON list of nudges `{subject, content, direction, rationale, weight_delta}`.
   Default backend = `local_propose` (one Ollama call per persona, persona system-prompt,
   low-ish temperature, `num_predict` bounded). Parsing is pure + defensive
   (`parse_nudges`): bad/empty entries dropped, never raised; `weight_delta` clamped.
3. **Synthesize:** `synthesize(current_identity, all_nudges)` → concrete identity edits
   (add new facet / strengthen existing / soften existing). Default backend = `local_synthesize`
   (one Ollama call that reconciles the conflicting nudges; where two lenses pull opposite
   ways, the *tension itself* may be kept as a facet). Pure parse `parse_edits`. A
   deterministic fallback merge (`merge_nudges`) is used if the synthesis call returns
   nothing parseable, so a cycle never silently no-ops.
4. **Apply + prune:** write edits via `db.upsert_memory(bot,'identity',...)` adjusting
   `weight`; `prune_memory_by_weight(bot,'identity', keep=_MAX_IDENTITY)`. Return the
   applied edits (for the trail).

The `propose`/`synthesize` seams mean a **Claude backend can swap in later** for
higher-fidelity deep reflections (sub-project 3/4) behind the same signatures — exactly
the seam the project's earlier specs anticipated for "fan-out personality-critique agents".

## Component 3 — The accelerated-life harness (`sim/accelerated_life.py`)

A **"day"** = live, then reflect:

1. **Live the day:** run a small *rotating* set of scenes via `sim.scene_runner.run_scene`
   against the experiment brain (`sim.brain_client`). Rotate location / partner / opener
   each day (a `day_plan(day_idx)` picks from a varied catalog) so experience differs day
   to day — variety is the fuel for drift. Scenes run with `consolidate=True` so
   relationship memory accumulates too. Transcript lines land in `/tmp/wbb-evo.db` because
   the brain saves messages there.
2. **Reflect:** `council.run_reflection(bot, db_path='/tmp/wbb-evo.db')`.
3. **Snapshot:** append a day record to `eval/evolution/<run>/trail.jsonl`:
   `{day, identity_facets, applied_edits, sample_lines}`.

Run **N days** (default 10; configurable). Runs in minutes (offline sim path, Ollama).
Module structure mirrors `sim/optimize/loop_cycle`. State persists across days in the one
throwaway `/tmp/wbb-evo.db`; identity + relationships accumulate; each day's scenes are
generated by a brain already carrying the accumulated drift.

**Lifecycle helpers** (reuse existing patterns): start the experiment brain on `:5001`
with `WBB_DB_PATH=/tmp/wbb-evo.db` via the project's existing
`sim.optimize.experiment_brain.start_experiment_brain()` helper (NEVER `pkill uvicorn` —
exit 144; use `stop_experiment_brain(proc)`), run the loop, leave the brain up. The chosen
real Alliance char's `bot_personalities` row is **created lazily by the brain** on its
first `/chat`/`/tick` (it copies `IRL_IDENTITIES` + queries the game DB for race/class/
level) — so **the game DB container (`ac-database`) must be UP** or the bot falls back to
the L1-Human identity (the substrate bug noted in project memory). No explicit identity
seed is needed; `sim.memory_fixture.load_memory_fixture` remains available if we want to
pre-seed *relationships* for a run.

## Component 4 — Observing the drift (verification)

Slice 1 is **eyeball-first**, exactly like the judge calibration was. No formal scoring
yet (that's sub-project 3).

- **Per-day trail:** `eval/evolution/<run>/trail.jsonl` (above).
- **The money shot — a fixed probe:** ask the bot the *same* questions on day 0 and day N
  (e.g. "tell me about yourself" + one topical probe) via the brain `/chat`, rendered side
  by side → `eval/evolution/<run>/probe.md`.
- **Identity diff:** day-0 vs day-N facet set rendered as added / changed / dropped →
  `eval/evolution/<run>/REPORT.md`.

**Success = the user reads the day-0-vs-day-N output and goes "yeah, that bot grew, and
it's still believable."**

## What slice 1 does NOT do (YAGNI / scope fence)

- No live (`:5000`) brain or prompt changes; no rebuild; no C++.
- No formal judge/scoring of evolution (sub-project 3).
- No `event`/`place` memory activation (sub-project 2) — the council reads what exists
  today (messages + relationships + identity).
- No persistent per-bot "muse" matchmaking (the Approach C idea — a later evolution of A).
- No multi-bot evolution at once — slice 1 evolves **one** bot end-to-end. (The harness
  should not hard-block multiple, but the verified path is one bot.)
- No Claude backend wired yet — Ollama personas only; the seam is left for it.

## Testing strategy

Project norm: **TDD + BDD (pytest-bdd / Gherkin)**, no network in tests.
- **Pure units (unit tests):** `parse_nudges`, `parse_edits`, `merge_nudges`
  (deterministic fallback), `prune_memory_by_weight`, `build_identity_section`,
  `day_plan` rotation.
- **Council cycle (BDD):** `run_reflection` with **injected fake `propose`/`synthesize`**
  — Given a bot with a current identity and a recent-life digest, When the council
  reflects with three disagreeing fake lenses, Then identity facets are added/strengthened/
  pruned as specified and the applied edits are returned. No Ollama.
- **Harness (BDD, with a fake brain):** Given a fake brain client and a fake council, When
  the accelerated-life harness runs K days, Then K trail records are written and identity
  accumulates across days. No Ollama, no subprocess.
- **Live verification (manual, not a test):** the real run in Component 4 against Ollama
  on `.99` + the experiment brain.

## Files (new / touched)

- **New:** `council.py`; `sim/accelerated_life.py`; tests + `.feature` files under `tests/`.
- **Touched:** `db.py` (+`prune_memory_by_weight`); `memory_prompt.py`
  (+`build_identity_section`); `prompts.py` (+`{identity_section}`, relaxed framing);
  `main.py` (fill `identity_section` in `/chat` + `/tick`). All reversible, brain-side
  only; the live brain process is restarted only if/when the user promotes (it is NOT
  promoted in slice 1).

## Reversibility

In-place feature branch off `master` (project norm — not worktrees, because the running
brain/venv/relative paths are bound to the working dir). Small commits. Nothing merges to
`master` or touches live without the user's review. Throwaway `/tmp/wbb-evo.db` per run.
