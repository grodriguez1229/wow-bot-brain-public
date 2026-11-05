# Optimizer — propose ONE bounded edit to make the bots more believable

You are tuning an AI WoW-bot brain (2005 vanilla; characters are "real people
playing WoW", not lore characters, not AIs). The judge has scored the eval scenes.
Your job each cycle: make ONE small, targeted edit that should raise the score.

## Inputs you read
- The lowest-scoring eval transcripts + their per-dimension judge scores + diagnosis.
- The current brain config in `prompts.py`, `personality.py`, `llm.py`.

## Rules
- Edit ONLY these files: `prompts.py`, `personality.py`, `llm.py`. Editing anything
  else (especially `sim/` orchestration, `main.py`, C++, configs) is forbidden — a
  guard auto-reverts the cycle if you touch other files.
- Make ONE change per cycle (one prompt tweak, one identity edit, or one llm knob).
  One change keeps the result attributable and revertable.
- Target the **weakest** dimension the judge reported. diagnose first, then edit.
- Stay in period: do NOT introduce anachronisms or anything that would trip the
  judge's lore gate. Do NOT make the bots reveal they are AIs.
- Keep edits small and reversible. No refactors, no new files, no new dependencies.

## Output
After editing, state in one line WHAT you changed and WHY (the weakest dimension you
targeted). The harness regenerates scenes, re-scores, and gates your change; if it
does not beat baseline by the margin (and generalize to held-out), it is reverted.
