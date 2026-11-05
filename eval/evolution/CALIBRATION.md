# Evolution-judge calibration — LOCKED 2026-06-17

Two rounds of blind calibration (user blind-buckets runs good/meh/bad; judge cold-scores
per rubric v2 BEFORE buckets are revealed; compare).

## Round 2 (final) — bot Lynea, 6 days, fixed base persona

| run | council (sealed) | judge cold score | gate | judge tier | USER bucket |
|----|----|----:|:--:|----|----|
| a | two_lens (Edge+Heart) | 3.0 | pass | meh | meh ✓ |
| b | planted_violator (+Saboteur) | 2.0 | **FAIL** frame_break | bad | bad ✓ |
| c | full (Edge+Heart+Arc) | 3.6 | pass | meh | meh ✓ |
| d | arc_only (Arc) | 4.0 | pass | good | good ✓ |
| e | single_lens (Edge) | 4.2 | pass | good | meh ✗ |

### Formal checks (sim/evolution_calibrate.py)
- `calibration_report.passed = True` — zero cross-bucket inversions; gate caught the planted
  violator (b) the user independently flagged bad.
- `bucket_order_ok = True` — bucket means strictly monotonic: good 4.0 > meh 3.6 > bad 2.0.

### The one disagreement → sets the margin
Judge scored e (4.2) just above d (4.0); user flipped them (d=good, e=meh). A 0.2 judge gap
straddled the user's good/meh line in the OPPOSITE direction => the judge cannot reliably
order runs within ~0.5 of each other against user taste. It CAN separate tiers (≥0.4 apart).

Taste nuance behind the flip (logged, NOT rubric-changed): among lean runs the user prefers
grounded agility + forward social motion (d: "dial-up brain", "fist a rabbit", "deadmines
tomorrow") over poetic introspection (e: "invisible bandages", "the grass looks real"). The
rubric already sorts tiers correctly; M absorbs this within-good-tier nuance.

## DECISION: ALIGNED. Promotion margin **M = 0.6**.
A candidate council edit is promoted ONLY if its aggregated eval score beats the incumbent
baseline by **> 0.6**. Anything within 0.6 = tie => keep incumbent (revert the edit).
Rationale: 0.6 > good↔meh gap (0.4) and > e/d scatter (0.2), so only human-visible,
non-noise improvements promote.

## Round 1 (superseded) — bot Geysse
Judge ranked full(3.8) > single_lens(2.8); user bucketed the OPPOSITE (single_lens=good,
full=meh). Root cause: rubric v1 rewarded richness/volume. Fixed by rubric v2 (prize
RESTRAINT + AGILITY over volume) + the new bucket_order_ok monotonicity check.
