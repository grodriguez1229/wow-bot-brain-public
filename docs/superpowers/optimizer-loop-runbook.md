# Optimizer Loop Runbook (autonomous /loop, one cycle per wake)

Each wake-up: execute **exactly one** optimize cycle, then reschedule or stop. You are
**Claude-in-the-loop** — you are both optimizer and judge. Branch: `optimizer-run`.
Spec: `docs/superpowers/specs/2026-06-12-optimizer-loop-design.md`.

## 0. Load state
- `git branch --show-current` must be `optimizer-run`. If not: `git checkout optimizer-run`.
- Read `eval/optimizer/loop_state.json` → `next_cycle` (N), `baseline_eval_mean`,
  `golden_frozen_mean`, `margin` (M=0.5), `consecutive_reverts`.
- Ensure the experiment brain is up:
  `ss -ltn | grep :5001 || venv/bin/python -c "from sim.optimize.experiment_brain import start_experiment_brain as s; s()"`
  **NEVER `pkill` uvicorn — it returns exit 144 and breaks the shell.** To restart, run
  `start_experiment_brain()` (it wipes `/tmp/wbb-exp.db` and relaunches; if a stale one is
  bound to :5001, find its pid with `ss -ltnp | grep :5001` and `kill <pid>` that specific pid).

## 1. Diagnose
Read 3-4 of the lowest-scoring eval transcripts (`eval/optimizer/scenes/*.json`; cycle-1
diagnosis: weak `turn_taking` / `continuity` / `voice` — repetition, parallel monologue,
blurred Brumdar/Sylvara voices, invented geography). Read current `prompts.py`,
`personality.py`, `llm.py`. Pick the single weakest pattern.

## 2. Make ONE whitelisted edit (per `prompts/optimizer.md`)
Edit only `prompts.py`, `personality.py`, or `llm.py`. One change. Stay in 2005 vanilla;
no anachronisms, no AI reveal. Different from edits already tried (see runlog `edit_summary`s).

## 3. Guard
```
venv/bin/python -c "import subprocess; from sim.optimize.guard import ALLOWED_PATHS, out_of_scope; c=subprocess.check_output(['git','diff','--name-only']).decode().split(); bad=out_of_scope(c,ALLOWED_PATHS); assert not bad, bad; print('guard ok', c)"
```
If it fails: `git checkout -- .` and skip to step 8 as a revert (record reason "out of scope").

## 4. Apply + regenerate eval
Restart the brain fresh so the edit loads, then regenerate the 16 eval scenes:
```
venv/bin/python -c "from sim.optimize.experiment_brain import start_experiment_brain as s; s()"
venv/bin/python -c "from sim.optimize.loop_cycle import regen_eval; regen_eval('eval/optimizer/manifest.json','/tmp/wbb-cand/scenes')"
```

## 5. Score the candidate eval scenes (cold)
Read all 16 `/tmp/wbb-cand/scenes/*.json`. Score each against `prompts/judge.md`: 5 dims
1-5 + gate. Compute `candidate_eval_mean` via `sim.judge.score_from_dimensions`. Count
`new_lore_failures` = scenes that now trip the gate but whose baseline did not.

## 6. Cheap-clause check → held-out short-circuit
Compute `eval_gain = candidate_eval_mean - baseline_eval_mean`.
- If `eval_gain <= M` OR `new_lore_failures > 0`: it will revert. Skip held-out; set
  `candidate_heldout_mean = baseline_eval_mean + 1e-3` (neutral), `anchor_now = golden_frozen_mean`.
- Else (a promising candidate): regenerate+score the 8 **held-out** scenes (manifest `heldout`)
  → `candidate_heldout_mean`; and re-score the 8 **golden anchors** (fixed transcripts in
  `eval/calibration/scenes/`, ids in manifest `golden`) → `anchor_now`.

## 7. Finalize (gate + commit/revert + log)
```python
import subprocess
from sim.optimize.cycle import finalize, CandidateResult
def commit(msg):
    subprocess.run(["git","add","prompts.py","personality.py","llm.py"],check=True)
    subprocess.run(["git","commit","-q","-m",msg],check=True)
    return subprocess.check_output(["git","rev-parse","HEAD"]).decode().strip()[:10]
def revert():
    subprocess.run(["git","checkout","--","prompts.py","personality.py","llm.py"],check=True)
dec = finalize(cycle=N, edit_summary="cycleN: <what+why>",
    candidate=CandidateResult(eval_mean=CAND, heldout_mean=CAND_HO, new_lore_failures=NLF),
    baseline_eval_mean=BASELINE, baseline_heldout_mean=BASELINE,
    anchor_mean=ANCHOR_NOW, anchor_frozen_mean=GOLDEN_FROZEN, margin=0.5,
    runlog_path="eval/optimizer/runlog.jsonl", commit=commit, revert=revert)
```

## 8. Update state + decide
- If `dec.keep`: `baseline_eval_mean = CAND`; `consecutive_reverts = 0`.
- Else: `consecutive_reverts += 1`.
- Write `eval/optimizer/loop_state.json` (increment `next_cycle`). Commit state+runlog+scores:
  `git add eval/optimizer/ && git commit -q -m "loop: cycle N <kept|reverted>"`.

## 9. Reschedule or stop
- **STOP** (do NOT reschedule; post a short summary of the run) if any: `consecutive_reverts >= 8`
  (converged); the finalize reason was `golden-anchor drift`; or repeated tooling errors.
- Otherwise **ScheduleWakeup** ~600s out with this same runbook prompt to run cycle N+1.

## Notes
- This branch is never merged automatically. Promotion of any kept config to prod/live is a
  separate human-gated step the user does after reviewing `runlog.jsonl`.
- Keep edits small and varied; the goal is to find a change that beats baseline by > 0.5 and
  generalizes to held-out without drifting the golden anchors.
