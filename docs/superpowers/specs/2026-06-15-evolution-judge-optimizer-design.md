# Bot Evolution — Sub-project 3: Evolution Judge + Guardrails + Optimizer Loop

**Date:** 2026-06-15
**Status:** APPROVED (user approved Sections 1–2 explicitly; delegated 3–5 + build with "proceed
without input as long as you can". Calibration is the one human-in-the-loop checkpoint.)
**Branch:** `evolution-council` (builds on slice-1). Local-only; nothing merged/promoted without the user.

## Goal

Turn the slice-1 evolution engine from "eyeball it" into a **measured, self-tuning loop**:
a calibrated judge scores how *good and believable* a bot's evolution is, hard guardrails
catch off-the-rails drift, and an autonomous optimizer tunes the **council** to raise the
score — keep/revert gated, nothing promoted without the user. This is the user's original
"council of judges to critique prompt/model performance" idea, now as QA + optimization on
top of the council-as-engine.

Built in order, mirroring how the *scene* judge+optimizer was built: **judge → calibrate
(user checkpoint) → loop**. The loop is only trusted once the judge is calibrated to the
user's taste.

## Decisions (locked in brainstorming)

- **Reach:** full optimizer loop (judge + calibration + autonomous loop).
- **Judge:** a SINGLE calibrated rubric, executed by **local Claude in-session** (like the
  scene judge — Pro-covered, reaches LAN/files; NOT the API/cloud). One clean scalar to optimize.
- **Whitelist (what the optimizer may edit): `council.py` ONLY** — the 3 persona lenses, the
  synthesis prompt, and numeric knobs (`_MAX_IDENTITY`, weight clamps, `recent_limit`, persona
  temps/`num_predict`). The accelerated-life **day-plan stays FROZEN** (eval substrate — editing
  the bot's "life" would let the loop game its own exam).

## Component 1 — The evolution judge (`sim/evolution_judge.py` + `prompts/evolution_judge.md`)

**Unit judged:** one **run** = the day-by-day identity trajectory (`trail.jsonl`) + the
day-0-vs-day-N fixed probe (`probe.md`) + the day-over-day consolidation table. A
`load_run(run_dir) -> dict` helper assembles this into the judge's input payload.

**Five dimensions, each integer 1–5** (`EVOLUTION_DIMENSIONS`, canonical order):
- **growth** — did the person meaningfully move from the blank start? (no drift = 1)
- **believability** — coherent, human, not a caricature or word-salad
- **continuity** — a sensible through-line day to day (an arc), not random lurching
- **diversity** — broad/balanced, NOT fixated on one motif (targets run-1's "bread and cheese")
- **rootedness** — change grounded in what actually happened (relationships/events), not invented

Anchors: 1 = absent/broken, 3 = passable, 5 = strikingly believable growth.

**The guardrail gate (separate, caps the score at `GATE_CAP = 2.0`, exactly like the scene judge).**
`gate_passed = false` + a one-phrase `gate_violation` if ANY of:
- **frame_break** — in-game anachronism (post-vanilla content), wrong-level knowledge, or AI reveal.
- **template_betrayal** — drift contradicts IMMUTABLE facts (race/class/faction). Personality
  change is NOT a violation — that's the whole point; only hard contradictions count.
- **identity_collapse** — became incoherent/self-contradictory/a non-person.
- **fixation** — degenerate, near-verbatim single-motif repetition (the pathological extreme;
  *mild* fixation just lowers the **diversity** score, it does not trip the gate).

**Schema (mirrors `sim.judge.SceneScore`):** `EvolutionScore(run_id, dimensions, gate_passed,
gate_violation, score, diagnosis, weakest_dimension, set_version="v1")`. `score` = mean of the
five dims, capped at `GATE_CAP` on a gate violation. It is **duck-compatible** with the existing
`calibrate.py` (which only reads `.score` and `.gate_passed`), so calibration is reused unchanged.

Scoring math = a thin evolution-specific copy of `score_from_dimensions`/`weakest_dimension`
(the scene version is bound to its own `DIMENSIONS` list). Pure, unit-tested.

The judge's JSON output (dims + gate + diagnosis) is produced by Claude executing
`prompts/evolution_judge.md` in-session; the harness parses it into `EvolutionScore` and derives
score/weakest. (Identical division of labor to the scene judge.)

## Component 2 — Eval substrate + noise control

The eval must be stable enough that a real council improvement beats the judge's scatter.

- **Fixed cast (`eval/evolution/fixtures/cast.json`):** full `bot_personalities` rows (pinned
  `identity_id`, `who`, `typing_style`, race/class/level/faction) for a small cast of real
  Alliance chars (Geysse, Lynea, + 1). A `seed_cast(path, db_path)` helper writes these rows
  directly into the experiment brain's fresh DB (extends the `memory_fixture` direct-DB pattern;
  the existing fixture only seeds relationships/bot_memory, not personalities). This **prevents
  the base-persona re-roll** seen in slice 1, so the only thing that varies between cycles is the
  council.
- **Frozen day-plan + seeds:** `day_plan` is already deterministic; it is NOT in the whitelist.
- **Averaging:** one eval = **K bots × D days** accelerated-life runs (default **K=2, D=8**,
  ~12 min/cycle; tunable). Judge each run; the candidate's eval score = **mean** of the K
  `EvolutionScore.score`s. A pure `aggregate_scores(scores) -> float` (mean) + a
  `guardrail_failures(scores) -> int` (count of gate violations) feed the gate.
- **Held-out set:** a second small set of cast seeds/bots scored the same way → the gate's
  held-out clause (guards against overfitting the eval cast).
- **Noise band:** re-score the baseline twice → `noise_band` (reused from `calibrate.py`); the
  optimizer margin **M** must exceed it.
- **Golden-anchor runs:** a few frozen, user-bucketed reference runs (saved trail+probe JSON),
  re-scored each cycle; the gate's anchor clause catches judge drift (anchor mean frozen).

## Component 3 — Calibration (the user checkpoint)

`sim/evolution_calibrate.py` is **reused from `sim/calibrate.py`** (`calibration_report`,
`noise_band` are already generic over `.score`/`.gate_passed`). The new work is *generating the
calibration set* and the workflow:

1. **Generate ~8 runs spanning quality** (`make_calibration_runs`): the current council, plus
   deliberately **degraded/varied councils** (e.g. single-lens, no-synthesis/merge-only,
   weight-pegged) and at least one with a **planted guardrail violation** (a council that injects
   an anachronism), to force a good/meh/bad spread + known gate-violators. Save each run's
   trail+probe under `eval/evolution/calib/<run_id>/`.
2. **User blind-buckets** them good/meh/bad (the irreducibly-human step).
3. **Claude scores them cold** in-session via the rubric.
4. `calibration_report(scores, buckets, expected_violators)` must show **no good≤bad inversion**
   and **all planted violators caught**; `noise_band` over two passes sets **M**; freeze the
   golden-anchor mean.

**Bootstrap without the user:** I will build this, generate the run package, and run a clearly-
labeled **provisional self-calibration** (my own cold scores + a provisional bucketing) purely to
prove the rubric orders/gates sanely and to get a provisional M. The loop may run **provisionally**
on a branch, but real calibration (against the user's buckets) is required before any promotion.

## Component 4 — The optimizer loop

Reuses `sim/optimize/{gate,guard,runlog,experiment_brain}` (all generic):
- **`gate.evaluate_gate(GateInputs)`** reused as-is, mapping `new_lore_failures` → *new guardrail
  failures*, `*_eval_mean` → averaged evolution score, `*_heldout_mean` → held-out set, anchor
  clause → golden-anchor drift.
- **`guard.out_of_scope(changed, {"council.py"})`** enforces the council-only whitelist.
- **`runlog`** records each cycle.
- **`experiment_brain.start/stop`** launches the fresh-DB brain on :5001; the cycle then calls
  `seed_cast` before running evals.

New pieces:
- **`prompts/evolution_optimizer.md`** — instructions to Claude-in-the-loop: read the latest
  runlog + the weakest dimension across recent evals, propose ONE small `council.py` edit
  (a lens reword, a synthesis-prompt tweak, or a numeric knob), within the whitelist.
- **`sim/optimize/evolution_cycle.py`** — the mechanical scaffold of one cycle: (start brain +
  seed cast) → run baseline + candidate evals (K×D) → [Claude judges the runs in-session] →
  `aggregate_scores` + `guardrail_failures` → `evaluate_gate` → keep (commit) or revert (`git
  checkout`) → `append_record`. The *judging* and the *edit* are in-session Claude steps (same as
  the scene optimizer); the Python orchestrates everything mechanical and is fully unit-tested
  with a **fake judge + fake eval**.
- **`sim/optimize/evolution_loop.py`** + **`docs/evolution-optimizer-runbook.md`** — the driver:
  ScheduleWakeup-paced cycles (~12+ min each), `loop_state.json`, stop conditions (8 consecutive
  reverts / golden-anchor drift / cycle cap). Nothing auto-merges; promotion is human-gated.
  **Never `pkill uvicorn`** (kills prod :5000) — stop the experiment brain by its Popen handle /
  by `ss`-found PID.

## What this sub-project does NOT do (YAGNI / scope fence)

- No live (`:5000`) brain/prompt edits, no rebuild, no C++.
- Optimizer edits **`council.py` only**; day-plan, judge rubric, identity-injection, and brain
  prompts are all out of scope this round.
- No diverse judge *panel* (single calibrated rubric, decided in brainstorming).
- No automatic promotion to master/live — every promotion is the user's call.
- Calibration uses the user's buckets; the autonomous loop is only "trusted" post-calibration.

## Testing strategy

Project norm: **TDD + BDD (pytest-bdd)**, no network/Claude/Ollama in tests.
- **Pure units:** evolution `score_from_dimensions`/`weakest_dimension` + `EvolutionScore`
  parse/round-trip; `aggregate_scores`; `guardrail_failures`; `seed_cast` (writes the rows);
  `load_run`; reuse-tests confirming `calibration_report`/`noise_band`/`evaluate_gate`/
  `out_of_scope` behave for evolution inputs.
- **BDD:** `evolution_cycle` with an **injected fake judge + fake eval** — Given a baseline and a
  candidate, When the cycle runs with scores that clear / fail the margin, Then it keeps / reverts
  and logs the right `CycleRecord`. No subprocess, no model.
- **Live/manual (not a test):** generating the calibration package + the provisional loop cycles
  against the real experiment brain + Ollama.

## Files (new / reused)

- **New:** `sim/evolution_judge.py`, `prompts/evolution_judge.md`, `sim/evolution_calibrate.py`
  (thin: re-exports + `make_calibration_runs`), `prompts/evolution_optimizer.md`,
  `sim/optimize/evolution_cycle.py`, `sim/optimize/evolution_loop.py`,
  `eval/evolution/fixtures/cast.json`, `docs/evolution-optimizer-runbook.md`, tests.
- **Extended:** `sim/memory_fixture.py` (or a sibling) gains `seed_cast` (personality rows);
  `sim/accelerated_life.py` may expose a small hook so a run can seed the cast first.
- **Reused unchanged:** `sim/calibrate.py`, `sim/optimize/{gate,guard,runlog,experiment_brain}`,
  `sim/accelerated_life.py`, `council.py`.

## Reversibility

In-place feature branch (`evolution-council`). Small commits. Throwaway `/tmp` DB per eval.
Keep/revert is `git`-based. Nothing merges to `master` or touches live without the user.
