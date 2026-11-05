# Evolution Optimizer — per-cycle editor instructions (Claude-in-the-loop)

You are tuning the **council** (`council.py`) to make bots evolve more believably, as scored by
the evolution judge (`prompts/evolution_judge.md`). One small, reasoned edit per cycle.

## Hard rules
- **Whitelist: you may edit `council.py` ONLY.** Specifically: the three persona `lens` strings,
  the `local_synthesize` system prompt, and the numeric knobs (`_MAX_IDENTITY`, `_WD_MIN/_WD_MAX`,
  `_W_MIN/_W_MAX`, `recent_limit`, persona `temperature`/`num_predict`). Never touch the day-plan,
  the judge rubric, the brain prompts, or the identity-injection wording — those are the frozen
  exam. `sim.optimize.guard.out_of_scope(changed, {"council.py"})` must return `[]`.
- **One change per cycle.** Small and reversible. The gate keeps it only if it beats the margin,
  regresses nothing held-out, adds zero guardrail failures, and the anchors haven't drifted.

## Each cycle
1. Read `eval/evolution/optimizer/runlog.jsonl` and the last few EvolutionScores. Look at the
   **weakest dimension** across recent eval runs and the judge `diagnosis` lines.
2. Form ONE hypothesis that targets that weakness, e.g.:
   - low **diversity** / fixation → strengthen the synthesis "merge duplicates / keep it broad /
     don't let one motif dominate" instruction, or lower persona `num_predict`.
   - low **continuity** → strengthen The Arc lens / the synthesis "stay consistent with who they've
     been becoming" line.
   - low **rootedness** → push lenses to cite the recent-life digest more; raise `recent_limit`.
   - low **growth** → raise weight deltas / let synthesis commit to bolder facets.
3. Make the edit. Confirm only `council.py` changed (`git diff --name-only`).
4. Run the eval (K×D accelerated-life over the fixed cast), judge each run in-session via the
   rubric, then call `evolution_cycle.run_cycle(...)`. It keeps (commits) or reverts (git checkout)
   and logs the cycle.
5. Stop per `evolution_loop.should_stop` (consecutive reverts / cycle cap) or golden-anchor drift.

Nothing merges to master or touches the live brain. Promotion is the user's call.
