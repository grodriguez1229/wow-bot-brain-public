# Evolution judge — calibration log

## Round 1 (2026-06-16)

**User blind buckets:** full = meh · single_lens = good · planted_violator = bad

**First rubric (v1) — MISCALIBRATED:** scored full 3.80 > single_lens 2.80 (inverted vs user).
The good-vs-bad-only `calibration_report` passed (good 2.80 > bad 2.00), but the good>meh>bad
ordering was wrong. Root cause: v1 rewarded richness/volume; the user prizes restraint, output
variety (not facet count), coherence, and earned insight.

**User's stated taste (the fix signal):**
- `full`'s probe answers are samey (recycles the same lament) — diversity must be judged on what
  it SAYS, not facet count.
- `single_lens` is more coherent (one consistent self) and lands a real-person insight.
- "more agile, without forcing itself to spit something out just so it can meet the numeric match
  on a prompt" → penalize padded / produced-to-fill output; volume ≠ quality.

**Rubric v2** (prompts/evolution_judge.md) encodes this: a "prize restraint and agility" principle;
diversity = output variety; continuity = coherence; growth = earned/natural (not volume);
believability penalizes generated-to-fill; rootedness rewards earned insight. Added
`bucket_order_ok` (good>meh>bad means) to catch this class of inversion.

**Re-score under v2 (FIT CHECK — I knew the buckets, so not independent):**
single_lens 3.60 (good) > full 2.80 (meh) > planted_violator 2.00 (bad, frame_break caught).
`calibration_report` ✅ + `bucket_order_ok` ✅.

**Status:** rubric v2 *can express* the user's taste, but this is overfit-prone (3 runs, labels
known). **Real calibration requires a FRESH blind batch**: generate N varied runs, cold-score them
sealed, THEN have the user bucket without seeing scores, then compare. Until that passes, the
optimizer loop stays OFF.
