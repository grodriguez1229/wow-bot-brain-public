# Evolution Judge + Optimizer Loop — Implementation Plan

> Executed in-session with TDD (write test → fail → implement → pass → commit per task).
> Heavy reuse of `sim/calibrate.py` + `sim/optimize/{gate,guard,runlog,experiment_brain}`.

**Goal:** A calibrated in-session judge scores evolution-run quality (5 dims + guardrail gate),
and an optimizer loop tunes `council.py` to raise it, keep/revert-gated.

**Spec:** `docs/superpowers/specs/2026-06-15-evolution-judge-optimizer-design.md`

**Test fixture (reuse):** `monkeypatch.setattr(db, "DB_PATH", str(tmp_path/"t.db")); db.init_db()`.

---

### Task 1 — `sim/evolution_judge.py` (scoring core)
- Test `tests/test_evolution_judge.py`:
  - `EVOLUTION_DIMENSIONS == ["growth","believability","continuity","diversity","rootedness"]`
  - `score_from_dimensions(dims, gate_passed)` = mean; capped at `GATE_CAP=2.0` when gate failed.
  - `weakest_dimension(dims)` = lowest, ties → canonical order.
  - `EvolutionScore` round-trips via `save`/`load` (mirror `SceneScore`); has `.score`, `.gate_passed`.
- Implement mirroring `sim/judge.py` (own DIMENSIONS list; do NOT import scene `DIMENSIONS`).
- Commit `feat(evo-judge): EvolutionScore + gate-capped scoring`.

### Task 2 — `prompts/evolution_judge.md` (rubric)
- Test `tests/test_evolution_judge_prompt.py` (like `test_judge_prompt.py`): asserts the file names
  all 5 dimensions, the 4 guardrails (frame_break/template_betrayal/identity_collapse/fixation),
  emits a single JSON object, and tells Claude NOT to compute the overall score.
- Write the rubric: judges a `run` payload (trajectory + day0/dayN probe + consolidation table);
  person-open / game-locked framing; the gate is separate (caps score). Output JSON
  `{run_id, dimensions{...}, gate_passed, gate_violation, diagnosis}`.
- Commit `feat(evo-judge): rubric prompts/evolution_judge.md`.

### Task 3 — Fixed cast: `seed_cast` + `eval/evolution/fixtures/cast.json`
- Test `tests/test_seed_cast.py`: `seed_cast(path, db_path)` inserts `bot_personalities` rows with
  the pinned `identity_id`/`who`/race/class so a subsequent `db.get_who` returns the fixture value
  (NOT a re-roll). Idempotent (re-seed overwrites).
- Implement `seed_cast` in `sim/memory_fixture.py` (sibling of `load_memory_fixture`; direct INSERT
  OR REPLACE into bot_personalities). Author `cast.json` = 3 real Alliance chars (Geysse L19 Dwarf
  Rogue, Lynea L?? NE Warrior, +1) with full pinned rows (eval cast) + 1 held-out bot.
- Commit `feat(evo-eval): fixed-cast fixture + seed_cast`.

### Task 4 — Eval aggregation (in `sim/evolution_judge.py`)
- Test (extend `tests/test_evolution_judge.py`):
  - `aggregate_scores([EvolutionScore...]) -> float` = mean of `.score`.
  - `guardrail_failures([EvolutionScore...]) -> int` = count where `not gate_passed`.
  - `load_run(run_dir) -> dict` reads `trail.jsonl`+`probe.md` into `{run_id, trail, baseline, final}`.
- Implement. Commit `feat(evo-eval): aggregate_scores + guardrail_failures + load_run`.

### Task 5 — `sim/evolution_calibrate.py`
- Test `tests/test_evolution_calibrate.py`: confirm `calibration_report`/`noise_band` (re-exported
  from `sim.calibrate`) work on `EvolutionScore` (duck-typed): a good≤bad pair → inversion; an
  uncaught planted violator → reported; noise_band returns max per-run |Δ|.
- Implement: `from sim.calibrate import calibration_report, noise_band` re-export +
  `degraded_council(kind) -> list[council.Persona]` factory (single-lens / merge-only-ish variants)
  + `make_calibration_runs(...)` spec (orchestration; thin, exercised live not unit-tested).
- Commit `feat(evo-calib): reuse calibration checks + degraded-council factory`.

### Task 6 — `sim/optimize/evolution_cycle.py` (mechanical cycle, fake judge+eval) — BDD
- Feature `tests/features/evolution_cycle.feature` + `tests/test_evolution_cycle_bdd.py`:
  - Scenario: candidate clears margin + no guardrail fails + anchor stable → KEEP, CycleRecord.kept.
  - Scenario: candidate below margin → REVERT.
  - Scenario: candidate introduces a guardrail failure → REVERT (even if score up).
- Implement `run_cycle(...)` taking injected `eval_fn` (cast→list[EvolutionScore]) and using
  `gate.evaluate_gate` + `runlog.append_record`; keep/revert via injected `apply`/`revert` callables
  (so tests don't touch git). Map guardrail_failures → `GateInputs.new_lore_failures`.
- Commit `feat(evo-opt): evolution_cycle with reused 4-clause gate (BDD)`.

### Task 7 — Loop driver + prompts + runbook
- `prompts/evolution_optimizer.md`: read runlog + weakest dimension → ONE small `council.py` edit,
  whitelist = `council.py`. `sim/optimize/evolution_loop.py`: `loop_state.json` + stop conditions
  (8 consecutive reverts / anchor drift / cap), `guard.out_of_scope(changed, {"council.py"})`.
  `docs/evolution-optimizer-runbook.md`: my per-cycle in-session steps; NEVER pkill uvicorn.
- Light test: `out_of_scope` rejects a non-council change; loop stop-condition helper.
- Commit `feat(evo-opt): loop driver + optimizer prompt + runbook`.

### Task 8 — Live: calibration package + provisional loop (manual)
- Start experiment brain :5001 fresh DB + `seed_cast`. Generate ~8 calibration runs (current +
  degraded + 1 planted-violator). Provisional self-calibration (cold in-session scores + provisional
  buckets) → provisional M + frozen anchor mean. Run 1–2 provisional optimizer cycles end-to-end
  (edit council → eval K×D → judge in-session → gate → keep/revert → log). Nothing merged/promoted.
- Write `docs/REPORT-2026-06-15-evolution-subproject3.md` + update memory + leave the user a
  blind-bucket checkpoint (the calib runs + how to bucket → real recalibration).
