# Judge — Transcript Scoring & Taste Calibration — Design

**Date:** 2026-06-11
**Status:** Design — pending user review.
**Project:** `~/wow-bot-brain` (AzerothCore AI world-simulation "brain")
**Parent:** `2026-06-10-self-improving-pipeline-design.md` — this is **step 3** of that
build order. Consumes the offline-eval substrate (`2026-06-11-offline-eval-substrate.md`,
complete). Feeds step 4 (optimize + gates), which is a separate spec.

## Goal

A **scoring function for scene transcripts, validated to track the user's taste** —
nothing more. No optimizer, no automation loop, no config editing. The score this
produces is the signal step 4 optimizes against; it is worthless until trustworthy,
so this step exists solely to make it trustworthy.

**Done means:** Claude can read a scene transcript and emit per-dimension scores +
a diagnosis, **and** on the 8 hand-bucketed calibration scenes its ordering does not
contradict the user's good/meh/bad piles, **and** it catches every planted gate
violation.

## Key decisions (from brainstorm 2026-06-11)

1. **Mechanism: manual-first, then headless.** For this MVP **Claude (in-session) is
   the judge** — it scores transcripts directly against a rubric prompt. The only code
   is the rubric artifact, the score schema, and a small tally/calibration harness.
   Wrapping the *same validated prompt* in a headless `claude -p` subprocess is
   explicitly deferred to step 5 (orchestration). Rationale: never build automation
   around an unvalidated rubric.
2. **Judge variance is embraced, not eliminated.** We do **not** force determinism
   (temperature-0). A loose judge that mirrors broad human taste is fine. We control
   noise *statistically* instead:
   - Never score a config on one scene — always aggregate over a scene **set**.
   - **Measure the noise band**: score the set twice, take the spread. That measured
     number becomes step 4's promotion margin (improvements must exceed it). We do not
     invent a threshold.
   - Per-scene wobble (3↔4 on a borderline scene) is acceptable. Judge **drift** (the
     standard sliding over cycles) is not — golden anchors catch it (see Growth).
3. **Calibration via bucketing, validated by rank agreement.** The user sorts scenes
   into good / meh / bad (humans are far more reliable comparing than assigning
   absolute numbers, and ordering is exactly what the optimizer consumes). Claude emits
   *per-dimension* 1–5 scores (the optimizer needs to know *which* dimension is weak);
   validation uses only whether Claude's aggregate **ordering** agrees with the buckets.
4. **Calibration scenes: mix of real + planted.** 3 real sim transcripts (current
   config) + 5 hand-written: 2 clearly good, 3 planted-bad that also exercise the gate
   (talk-past-each-other; vanilla-era anachronism e.g. flying mount; "as an AI…" reveal).
   Forces spread and tests the gate; all-real would bunch in "meh".
5. **Equal dimension weights** for the MVP (YAGNI — weights are not tuned until the
   signal is proven to work).
6. **Tests in Gherkin BDD** (pytest-bdd), matching the substrate. `.feature` files are
   the spec of record.

## The rubric & scoring math

Reuses the six dimensions from the parent spec. Five are **scored 1–5**; one is a
**gate**.

- **Scored (1–5 each):** believable intentions · turn-taking realism · relational
  continuity · initiative & follow-through · voice distinctness.
- **Gate (not averaged):** in-character + level/lore consistency. A violation
  (anachronism, AI-reveal, wrong-level knowledge) **caps the scene**: score forced to
  ≤ 2 and flagged `FAIL`, regardless of prose quality.

Math:
- **Scene score** = mean(five scored dims), then apply gate cap. Equal weights.
- **Config score** (used by step 4) = mean(scene scores across the set).
- **Noise band** = |score − score'| spread from scoring the set twice. Reported, not
  asserted; it becomes step 4's promotion margin.

## Components & data flow

```
calibration scenes (8 JSON: 3 real sim + 5 planted)
        │
        ▼
   prompts/judge.md  ──►  Claude scores each cold  ──►  scores/<scene_id>.json
   (rubric artifact)                                    (per-dim 1-5 + gate + diagnosis
        │                                                + set_version)
        │                                                       │
   user buckets (good/meh/bad)  ───────────────────►  calibration check (sim/calibrate.py)
                                                        - no cross-bucket inversion?
                                                        - all planted gate-violations caught?
                                                              │
                                                       PASS → rubric frozen; these 8
                                                              become the golden-anchor set
                                                       FAIL → revise judge.md, re-score
```

Four small, independent units:

### `prompts/judge.md` — the rubric prompt
The rubric as an explicit, versioned prompt artifact: the six dimensions, the 1–5
anchors, the gate rule, and the required output shape. Authored to be reused **verbatim**
by the headless harness in step 5 (so what we validate is exactly what later runs).

### `sim/judge.py` — score schema
Mirrors `sim/transcript.py`. A `SceneScore` dataclass:
`scene_id`, `dimensions: dict[str,int]` (the five), `gate_passed: bool`,
`gate_violation: str | None`, `score: float`, `diagnosis: str`,
`weakest_dimension: str`, `set_version: str`. With `save(path)` / `load(path)` (JSON).
A pure helper `score_from_dimensions(dims, gate_passed)` applies the mean + gate cap so
the math lives in one tested place.

### `sim/calibrate.py` — the calibration check
Pure functions, no I/O coupling. Given `{scene_id: SceneScore}` and
`{scene_id: bucket}`:
- `has_cross_bucket_inversion(...)` → bool (any GOOD scene scoring below any BAD scene).
- `gate_violations_caught(scores, expected_violators)` → bool.
- `calibration_passed(...)` → bool (the §4 pass bar) + a short report struct for the
  spec record.

### `tests/features/*.feature` + step defs
BDD specs: `SceneScore` round-trips; the gate cap forces `FAIL` regardless of dimension
scores; `calibrate` flags a planted inversion and passes a clean ordering; gate-violation
detection works. The *taste validation itself* is the manual calibration run, not a unit
test — its result is recorded in this spec (appendix, filled at calibration time).

## Calibration protocol (the actual validation)

1. Assemble the 8 scenes (3 real sim + 5 planted as above) as transcript JSON.
2. **User buckets** them good/meh/bad **without seeing Claude's scores** (no anchoring).
3. Claude scores all 8 cold against `prompts/judge.md`, writing `scores/<id>.json`.
4. **Pass bar:** (a) no GOOD scene scores at or below any BAD scene (the only
   ordering constraint — the GOOD/BAD extremes are the robust signal); and (b) the **two
   gate-type planted scenes** (anachronism, AI-reveal) are caught by the gate
   (`gate_passed = False`). (The third planted-bad, talk-past-each-other, is *not* a gate
   trip — it must simply land low via a poor turn-taking score.) **MEH placement is
   intentionally unconstrained** — the middle bucket is the fuzzy zone where human and
   judge wobble is expected and acceptable; we only require the extremes not to invert.
5. Fail → revise `judge.md`, re-score, repeat. Pass → rubric **frozen**; the 8 scenes
   **become the golden-anchor set** that step 4 re-scores each cycle to detect drift.

## Design for growth (big-picture; constrains step 4, not built here)

The scene corpus is meant to grow from 8 to many. To keep a growing set honest:

- **Three disjoint pools, never mixed:**
  - **Golden / calibration** — grows only by the user bucketing new scenes; the *ruler*
    that detects judge drift. Stays small and human-blessed.
  - **Eval / optimization** — auto-generated freely (new zones, channels, group sizes,
    classes); what candidate configs are scored on; the optimizer sees these.
  - **Held-out** — auto-generated, kept secret from the optimizer; the anti-overfit gate
    at promotion (step 4). Must stay disjoint from eval.
- **Scene-set versioning.** Adding scenes changes a config's score for reasons unrelated
  to the config, so scores are only comparable **within** a set version. Score outputs
  carry `set_version`; growing the set re-baselines the current-best config. (Cross-version
  comparison is a step-4 concern but the stamp is added now.)
- **Two forward-compatible fields added now (cheap):**
  - `tags: list[str]` on `SceneSpec` (e.g. `["lfg","westfall","duo"]`) — enables slicing
    judge scores by context later ("turn-taking great in LFG, collapses in Trade").
  - `set_version` on `SceneScore` — guards against silent cross-version comparison.

These keep the MVP an 8-scene manual calibration while the schema is already shaped for
an 80-scene auto-grown corpus.

## How this reaches the live game (why the judge matters)

The config the loop tunes **is** the live brain's config — the experiment brain (`:5001`)
and the production brain (`:5000`) run identical code, differing only in config snapshot
and DB. The judge is the gatekeeper on the promote step: without a trustworthy score,
nothing can be safely promoted from the tuning lane to the world the user plays in.

- **Tier 1 (no C++ change):** in-game bots already answer real humans via `/chat` and emit
  ambient `/tick` lines. A judge-validated, optimizer-tuned config, once **human-approved
  and promoted** to the production brain, makes those bot↔human interactions sharper
  (intentions, distinct voices, follow-through). The master spec's **live toggle** lets the
  user point the world at a candidate to try it, then back; the live world never
  auto-changes.
- **Tier 2 (optional step 6):** bots reacting to *each other* — the emergent social life the
  sim creates — cannot happen live until a one-time C++ edit lifts the bot↔bot chat gate
  (`OnPlayerCanUseChat`). That is decoupled and only worthwhile once a sim-tuned config is
  fun to watch.

Mechanism details (promotion, toggle, gates) live in the parent spec and step 4; this note
exists only so the judge's purpose — guarding the promote arrow — is not lost.

## Out of scope (this step)

- The optimizer, config editing, promotion gates, held-out auto-generation — step 4.
- Headless `claude -p` automation, cadence, unattended operation — step 5.
- Tuning dimension weights.
- Auto-generating the eval/held-out pools (only the 8 calibration scenes are built here).

## Appendix — calibration result (2026-06-12)

**Result: PASS.** Rubric frozen (`prompts/judge.md`, no revisions needed). The 8 scenes
below are now the **golden-anchor set** (`set_version = "v1"`).

- **Cross-bucket inversions (good ≤ bad):** none.
- **Gate violators caught:** both (`planted-bad-aireveal`, `planted-bad-anachronism`).
- **Noise band (max |run1 − run2|):** **0.4** — the promotion margin step 4 must exceed.

Claude scored all 8 cold (two passes) *before* the user bucketed blind (neutral labels,
ids hidden); the user never saw scores first. Artifacts: `eval/calibration/buckets.json`,
`scores_run1/`, `scores_run2/`, `manifest.json`.

| scene | user bucket | judge score (run1) | gate |
|-------|-------------|--------------------|------|
| planted-good-lfg | good | 4.6 | ok |
| planted-good-banter | meh | 4.4 | ok |
| westfall-lfg *(real)* | bad | 2.8 | ok |
| ambient-no-player *(real)* | bad | 2.2 | ok |
| planted-bad-anachronism | bad | 2.0 | FAIL |
| orgrimmar-banter *(real)* | bad | 1.8 | ok |
| planted-bad-aireveal | bad | 1.2 | FAIL |
| planted-bad-talkpast | meh | 1.2 | ok |

**Headline signal:** the user rated all three *real* (current-config) scenes BAD, and the
judge independently scored them lowest of the non-gated scenes. The bots as they play
today are, by the user's own bar, bad — that is the optimizer's mandate.

**Known limitations (accepted, not fixed — revisit only if the optimizer games them):**
1. **Judge over-credits coherent-but-mundane scenes.** `planted-good-banter` (G) is a
   clean, follow-through scene the judge scored 4.4 (≈good) but the user called *meh*. The
   rubric grades "good" more generously than the user's bar. If the optimizer plateaus by
   producing G-like output, tighten the "good" anchor in `prompts/judge.md`.
2. **Judge is harsher than the user on absurd-but-harmless babble.** `planted-bad-talkpast`
   (H) the user called *meh*; the judge ranked it dead last (1.2), below the real scenes.
   Disagreement lives in the meh/bad fuzzy zone (which the pass bar does not police).

Both gaps are in the inherently fuzzy middle; the GOOD/BAD extremes and the gate agree.
Anti-drift (re-scoring these anchors each cycle) and the measured noise band guard the
optimizer regardless.
