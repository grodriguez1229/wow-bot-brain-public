# Model Bake-off + Compound Template Edit — Design

**Date:** 2026-06-12
**Branch context:** builds on `optimizer-run` (baseline `eval_mean = 1.975`, judge frozen, golden-anchor mean `2.525`, gate margin `M = 0.5`).
**Status:** approved 2026-06-12.

## Motivation

The first overnight optimizer run converged at 8 consecutive reverts with nothing
promoted. Two findings drive this follow-up:

1. **`qwen3.5:9b` appears to sit at a ~2.0 quality ceiling.** Every whitelisted prompt
   edit landed in the 1.8–2.2 band regardless of direction. This points at the *actor
   model* as the bottleneck, not the prompts.
2. **The repetitive filler is baked into the templates, not emergent.** The exact phrases
   the judge flagged come straight from `personality.py` / `prompts.py`:
   - `weekend_warrior.typing_style` literally contains `"man i wish i could play more"`.
   - level ≤ 10 goal pool contains `"everything i have sucks"` ("my gear sucks").
   - the TICK **SAY** activity prompt hands the model `"ugh another murloc"` / `"nice"`
     as examples, which bots parrot verbatim.

This project tests the model-ceiling hypothesis and the template-diversification fix
**as two cleanly attributed phases**, reusing the existing frozen judge + eval/held-out/
anchor harness. Nothing auto-merges; promotion to prod/live stays human-gated.

## Non-goals

- No structural/architectural change (stateful ticks, shared scene memory, goal
  rotation, C++ bot↔bot). That was rec #3 from the run and is explicitly out of scope here.
- No judge re-calibration. The judge stays frozen so scores remain comparable to the
  1.975 baseline and the 2.525 anchor.
- No promotion/merge to `master` or prod. This is an experiment that produces a report
  and a decision for the user.

## Phase A — Model bake-off (isolates the model)

Hold the **current baseline** `prompts.py` / `personality.py` / `llm.py` fixed. For each
candidate model, measure quality and viability under identical conditions.

**Candidates:** `qwen3.5:9b` (re-baseline, sanity check vs. 1.975), `mistral-small:22b`
(the strong bet, ~3× params), `gemma4:latest` (mid step-up).

**Per candidate:**
1. Set `OLLAMA_MODEL` to the candidate (the only change; everything else frozen).
2. Restart the experiment brain on a fresh `/tmp/wbb-exp.db` so the model loads clean.
3. Regenerate the 16 eval scenes (`regen_eval` against the manifest).
4. Score all 16 cold against `prompts/judge.md` (5 dims + gate) →
   `score_from_dimensions` → `eval_mean`.
5. Record **median per-scene generation latency** alongside the score. The 22b (12.6 GB)
   may be slow or VRAM-bound on the LAN Ollama box (<ollama-host>); latency is a real
   viability gate, not just a curiosity.

**Output:** a 3-row table `(model, eval_mean, median_latency_s)`.

**Winner selection `M*`:** the highest `eval_mean` that is **meaningfully above** qwen's
1.975 noise band (i.e. gain `> M = 0.5` over the re-measured qwen baseline) **and**
latency-viable (median per-scene generation comfortably under the brain's 45 s httpx
timeout, with margin for live play). If no candidate clears both, `M* = qwen3.5:9b` and
Phase B proceeds on qwen (the ceiling finding stands, templates tested anyway). The
winner's `eval_mean` becomes `new_baseline_mean`.

## Phase B — Compound template edit on `M*` (isolates the templates)

A single deliberate candidate (not the auto-loop), all edits applied together because
they target one root cause — baked-in, parroted filler:

- **`personality.py`:**
  - Broaden and de-cliché `pick_goal_for_level` pools across all level bands — more
    options, drop the tired/"everything sucks" monoculture, keep them level-accurate
    and 2005-vanilla.
  - Revise `typing_style` strings that carry literal catchphrases (notably
    `weekend_warrior`'s "man i wish i could play more") so the *style* is described
    without a parrotable line.
- **`prompts.py` (TICK):** remove the over-specific example phrases ("ugh another
  murloc", "nice") that seed verbatim repetition; describe the intent instead.
- **`prompts.py` (CHAT):** add cycle-2's engagement rule — respond to the other
  speaker's last message; don't restate your own goal. (This was the single best lever
  in the first run, +0.175 before noise.)

**Evaluation (one shot, full gate):**
- Regenerate + score the 16 eval scenes on `M*` → `candidate_eval_mean`.
- Regenerate + score the 8 held-out scenes → `candidate_heldout_mean`.
- Re-score the 8 golden anchors (frozen transcripts) → `anchor_now` for drift.
- Run `evaluate_gate` with `margin = 0.5` against `new_baseline_mean`. Keep iff: eval
  gain `> 0.5` AND held-out not regressed AND no new lore failures AND
  `|anchor_now − 2.525| ≤ 0.5`.

**Margin note:** generation noise was *not* re-measured on `M*`; 0.5 (qwen-derived) is
kept as a conservative threshold. If Phase B lands just under 0.5 on a stronger model,
re-measuring noise on `M*` is the documented follow-up before lowering it.

## Attribution output

Three comparable points plus the combined total:

| config | eval_mean | reads as |
|--------|-----------|----------|
| `qwen3.5:9b` + baseline templates | 1.975 (known) | starting point |
| `M*` + baseline templates | from Phase A | **model effect** |
| `M*` + diversified templates + engagement | from Phase B | **template effect** + combined total |

## Guard / scope handling

- The model swap is a one-line change in `config.py`, which is **outside** the prompt
  whitelist (`prompts.py` / `personality.py` / `llm.py`). This is deliberate: a model
  swap resets the baseline, it does not pass through the 0.5 gate. Phase A documents the
  `config.py` `OLLAMA_MODEL` edit and restores it to the chosen `M*` at the end; the
  whitelist guard is only relaxed for that documented line.
- Phase B edits are all inside the whitelist; the standard guard check applies unchanged.
- Operational gotcha carried over: **never `pkill uvicorn`** (exit 144). Restart via
  `start_experiment_brain()`; kill a stale `:5001` by specific pid from `ss -ltnp`.

## Testing

- BDD coverage already exists for the harness pieces (gate, pools, guard, runlog, cycle).
  New code in this project is thin orchestration; add a Gherkin scenario for the
  bake-off recorder (records one row per model; picks the viable max) following the
  existing pytest-bdd pattern. No judge/sim-engine changes, so their suites are untouched.

## Deliverables

- Phase A bake-off table (model, eval_mean, latency) committed under `eval/bakeoff/`.
- Phase B candidate scores + gate decision appended to a run record under `eval/bakeoff/`.
- A short written report to the user with the 3-point attribution and a promotion
  recommendation. Branch stays unmerged; the user decides what (if anything) to promote.
