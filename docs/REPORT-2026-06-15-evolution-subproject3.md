# Session report — Sub-project 3: Evolution Judge + Guardrails + Optimizer Loop

**Branch:** `evolution-council` (builds on slice 1). **Nothing merged to master. Nothing touched live.**
**Tests:** 187 passing. Prod brain (`:5000`) untouched throughout.
**Spec:** `docs/superpowers/specs/2026-06-15-evolution-judge-optimizer-design.md` ·
**Plan:** `docs/superpowers/plans/2026-06-15-evolution-judge-optimizer.md`

## What you asked for
Your original "council of judges to critique prompt/model performance" — now as **QA +
optimization** on top of the council-as-engine. You chose: **full optimizer loop**, **single
calibrated rubric** judge, **`council.py`-only** edit whitelist. Then: "proceed without input as
long as you can."

## What I built (all TDD/BDD)
- **Evolution judge** (`sim/evolution_judge.py` + `prompts/evolution_judge.md`): scores a whole
  *run* on 5 dims — **growth, believability, continuity, diversity, rootedness** — with a guardrail
  gate that caps the score at 2.0 on **frame_break / template_betrayal / identity_collapse /
  fixation**. `EvolutionScore` is duck-compatible with your `SceneScore`, so the existing
  `calibrate.py` and `optimize/gate.py` work on it unchanged.
- **Fixed-cast eval substrate** (`seed_cast` + `eval/evolution/fixtures/cast.json`): pins the base
  persona (Geysse/Lynea/Tomaslin) so it never re-rolls between cycles — fixing the slice-1 confound.
  Plus `aggregate_scores` (K-bot mean) + `guardrail_failures`.
- **Calibration** (`sim/evolution_calibrate.py`): reuses your `calibration_report`/`noise_band`
  (they only read `.score`/`.gate_passed`); adds a `degraded_council` factory (full / single-lens /
  planted-violator) to generate a quality spread.
- **Optimizer loop** (`sim/optimize/evolution_cycle.py` + `evolution_loop.py` +
  `prompts/evolution_optimizer.md` + `docs/evolution-optimizer-runbook.md`): one cycle = edit
  `council.py` → eval K×D → judge in-session → **reused 4-clause gate** keep/revert → log. Whitelist
  guarded (`guard.out_of_scope(changed, {"council.py"})`), stop conditions, frozen day-plan. Heavy
  reuse of `gate/guard/runlog/experiment_brain`.

## Proven on real data (the headline)
I generated a 3-run calibration package (Geysse, 6 days each, fresh cast-seeded brain per run) and
judged each in-session via the rubric:

| run | score | gate | weakest |
|---|---|---|---|
| **full** (real 3-lens council) | **3.80** | PASS | diversity |
| **single_lens** (Edge only) | **2.80** | PASS | diversity |
| **planted_violator** (+ Saboteur) | **2.00** | **FAIL — frame_break** | believability |

**Provisional self-calibration PASSED:** no good≤bad inversion (3.8 > 2.8 > 2.0), and the planted
post-vanilla violation (Death Knight alt / Outland dailies / Epic Flying Mount) was **caught by the
guardrail**. So the judge orders runs sensibly *and* the gate catches off-the-rails drift, end to
end. Two side-findings: the diverse council clearly beats a single lens (3.8 vs 2.8 — validates
council-as-engine), and the judge names **diversity** as the ceiling on both good runs — the same
dedup/fixation lever slice 1 surfaced, so the optimizer already knows where to aim.

## What I deliberately did NOT do (and why)
- **No live optimizer-loop run.** The cycle logic is unit-tested (3 BDD scenarios) and the judge+gate
  are proven on real runs; a live cycle is ~15 min of eval + judging *per cycle* and — crucially —
  **an autonomous loop shouldn't be trusted until the judge is calibrated to YOUR taste**, not mine.
  It's fully wired and documented in the runbook, ready to run once calibrated.
- **Nothing promoted / merged / made live.**

## YOUR checkpoint — blind-bucket the calibration runs
This is the one irreducibly-human step. Read these three (don't peek at the scores above):
`eval/evolution/calib/{full,single_lens,planted_violator}/REPORT.md`
and bucket each **good / meh / bad**. Then tell me your buckets. If they match my provisional
ordering, the judge is calibrated and I'll set the real promotion margin **M** and turn the loop
loose (on the branch, nothing auto-promoted). If they don't, we adjust the rubric before trusting it.

## Then
Run the optimizer loop (per `docs/evolution-optimizer-runbook.md`) targeting the **diversity**
weakness, keep/revert-gated; review the winning `council.py`; you decide on promotion to live
(that's still sub-project 4). Remaining: sub-project 2 (richer `event`-memory substrate),
sub-project 4 (live promotion).
