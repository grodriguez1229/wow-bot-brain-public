# Optimizer Loop — Self-Improving Tuning Cycle — Design

**Date:** 2026-06-12
**Status:** Design — pending user review.
**Project:** `~/wow-bot-brain` (AzerothCore AI world-simulation "brain")
**Parent:** `2026-06-10-self-improving-pipeline-design.md` — this is **step 4 (optimize +
gates)** of that build order, and folds in the light **step 5 (loop driver)** so the
result actually self-iterates. Consumes the **judge** (`2026-06-11-judge-scoring-design.md`,
complete: rubric frozen, 8 golden anchors, measured **noise band 0.4**) and the offline
substrate (`2026-06-11-offline-eval-substrate.md`, complete).

## Goal

A loop that, each cycle, proposes **one** whitelisted edit to the *experiment* config,
regenerates eval scenes, scores them with the judge, and **keeps or reverts** the edit
through a strict gate — driven by a `/loop` session so it runs **unattended in the
experiment lane**, never touching the world the user plays in.

**Done means:** the loop runs unattended for N cycles, every cycle gated and logged
(git history + run log), producing a measurable eval-score gain over baseline, with **no
golden-anchor drift** and **zero contact with the prod brain/DB**.

## Key decisions (from brainstorm 2026-06-12)

1. **Claude-in-the-loop (intelligent edits).** Each cycle, Claude (via `/loop`) reads the
   lowest-scoring eval scenes + the current config, diagnoses the weakest pattern, and
   writes ONE targeted whitelisted edit (prompt / identity / orchestration / llm knob).
   Not a mechanical parameter sweep — we want prompt/personality rewrites, not just
   number-twiddling. Cost: bounded by Pro rate limits → cadence ~one cycle / 10–15 min.
2. **Full auto in the experiment lane.** Cycles auto-apply / score / gate / commit-or-revert
   with no approval. The loop pauses for the human **only** on (a) golden-anchor drift, or
   (b) a config being promoted to the live game. Promotion to prod is always a separate,
   explicit, human-approved step; the loop never does it.
3. **Build sequencing: one verified cycle, then the driver.** First make a single cycle
   work end-to-end (manually triggered) and verify it by hand; only then switch on the
   `/loop` driver. Never let an unverified cycle run free.
4. **Three disjoint scene pools** (see below) — resolves the held-out gap; the existing 8
   golden anchors stay purely as the drift ruler.
5. **One edit per cycle**, from a fixed whitelist, enforced by a pre-apply guard.
6. **Tests in Gherkin BDD** (pytest-bdd), matching the codebase. The pure gate logic is the
   critical unit; orchestration is tested with a fake judge + fake editor.

## Scene pools (generated once, up front, from the sim)

| Pool | Size | Role | Optimized against? |
|------|------|------|--------------------|
| **Golden anchors** | existing 8 | drift ruler, re-scored every cycle | **No** — never a target |
| **Eval** | ~16 real sim scenes (varied zones/seeds) | what candidates are scored on | **Yes** — Claude sees & diagnoses |
| **Held-out** | ~8 real sim scenes (different seeds) | the promotion gate (anti-overfit) | **No** — only scored at the gate |

- Eval/held-out are **real current-config sim output** — the "bad" baseline (per the judge
  calibration, the user rated all current-config scenes BAD) that the loop exists to improve.
- All scenes carry `tags` + `set_version`. Pools must be **disjoint** (asserted in code);
  adding scenes later bumps `set_version` and re-baselines (per the judge spec's growth model).
- Golden anchors include hand-planted scenes and are NOT representative sim output, which is
  exactly why they are the drift tripwire and not an optimization target.

### Gate margin calibration (setup, before the loop runs)

The judge's measured noise band is **0.4**, but that was re-scoring *fixed* transcripts —
judge-only variance. Each cycle **regenerates** scenes from Ollama, adding generation
variance on top. So the gate margin must cover **both**. At setup, generate the eval pool
**twice with the same baseline config**, score both passes, and set

> **gate margin `M` = max(0.4, measured eval-pool generation+judge spread)**

`M` (not a hardcoded 0.4) is the threshold a candidate must beat. This keeps the gate from
passing on the inherent noise of re-rolling scenes. `M` is recorded in the run log header.

## The optimize cycle (one iteration)

1. **Baseline** = current experiment config's eval-pool mean score (cached from last cycle;
   computed fresh on the first cycle).
2. **Diagnose** — Claude reads the lowest-scoring eval scenes + the current config and
   identifies the weakest pattern/dimension.
3. **Propose ONE edit** from the whitelist. A pre-apply **guard** rejects out-of-scope edits
   before they touch disk.
4. **Apply** the edit to the experiment **config snapshot**, and rebuild a **fresh
   experiment DB** (identities are copied into `bot_personalities` rows at bot creation, so
   identity/prompt changes only take effect on a clean DB).
5. **Regenerate** the eval scenes with the candidate config (local Ollama — cheap).
6. **Score** the candidate eval scenes against the **frozen** `prompts/judge.md` — cold,
   on their merits, not framed as "did my edit help?".
7. **Gate — keep the edit iff ALL hold:**
   - candidate eval mean > baseline mean **by more than `M`** (the calibrated gate margin,
     see above), **and**
   - candidate also beats baseline on the **held-out** pool (by any positive margin —
     direction, not magnitude, since held-out only guards against overfit), **and**
   - **no new lore-gate failures** vs baseline, **and**
   - **golden anchors did not drift**: the golden-anchor mean this cycle stays within `M`
     of its frozen `v1` calibration value (drift beyond `M` = Claude moving the goalposts).
8. **Commit** the snapshot as the new best (baseline advances) — else **`git revert`**
   (baseline unchanged). Either way the cycle is one git commit.
9. Append a one-line record to the **run log** (cycle #, edit summary, baseline/candidate
   means, held-out delta, gate verdict, commit SHA).

The gate is intentionally strict: a change must clear noise **and** generalize **and** stay
in character **and** not coincide with score drift. Most cycles will revert — correct; only
real wins stick.

## The loop driver (step 5, light)

A **self-paced `/loop` session**. Each wake = one cycle. Self-paces to respect Pro rate
limits (~one cycle / 10–15 min; backs off when rate-limited). **Pauses/stops** on:

- **golden-anchor drift** → stop, surface for human review (possible self-deception);
- **convergence** → K consecutive no-win cycles (default **K = 8**);
- **rate-limit exhaustion** → sleep and resume;
- **user interrupt**.

Never promotes to prod.

## Edit whitelist + safety boundary

**Editable (one per cycle):** `prompts.py` templates · `IRL_IDENTITIES` content ·
goal/activity text · `llm.py` knobs (temperature, num_predict, truncation) · sim
orchestration policy (turn-taking, response odds, thread depth, follow-through).
**Never:** C++ · the dead `personalities/*.yaml` · the prod brain (`:5000`) / prod DB ·
anything outside the list.

A **pre-apply guard** validates each proposed edit against the whitelist and rejects
out-of-scope edits before they touch disk.

**Safety net:** experiment lane only · every cycle is a git commit *or* revert (always full
rollback) · prod promotion human-gated · golden-anchor drift halts the loop.

## Self-deception defenses (judge == optimizer == Claude)

The sharpest risk: Claude both proposes edits and scores them, so it can fool itself.
Defenses, all enforced structurally:

- **Held-out pool** Claude never optimizes against must *also* improve — catches overfitting
  to the visible eval scenes.
- **Cold scoring** against the frozen rubric — scenes judged on merit, not "did my change work?".
- **Golden-anchor drift check** every cycle — if the golden-anchor mean moves beyond `M`
  from its frozen `v1` value, Claude is moving the goalposts → halt.
- **One edit per cycle** — every change attributable and revertable.

## Components (small, focused, testable)

```
sim/optimize/
  config_snapshot.py   # snapshot / apply / restore a config to-from a dir (experiment lane)
  pools.py             # generate + load the 3 disjoint scene pools (tagged, versioned)
  gate.py              # PURE keep-or-revert decision (the 4-part gate) — fully unit-tested
  runlog.py            # append / read one-line cycle records
  cycle.py             # orchestrate ONE cycle: diagnose -> apply -> regen -> score -> gate
                       #   -> commit/revert -> log. Claude acts at the diagnose/propose step.
prompts/optimizer.md   # how Claude diagnoses + proposes a bounded whitelisted edit
loop entry (/loop)     # the driver that calls one cycle each wake
```

- `gate.py` is the critical pure unit — the entire safety argument lives in its decision
  function and is exhaustively tested.
- `config_snapshot.py` defines the experiment lane: a config is a directory of
  prompt/identity/knob/orchestration values that can be applied and rolled back atomically.
- `cycle.py` is orchestration; the diagnose/propose step is where Claude's judgment enters.
  It accepts the judge + editor as injected collaborators so it can be tested with fakes.

## Testing

BDD (pytest-bdd) for the pure pieces:
- **`gate.py`** — the 4-part decision, with a scenario per clause showing each clause alone
  flips keep→revert (noise margin, held-out regression, new lore failure, anchor drift).
- **`config_snapshot.py`** — snapshot → apply → restore round-trips the config exactly.
- **`pools.py`** — the three pools load and are provably disjoint.
- **`runlog.py`** — records append and read back.
- **`cycle.py`** — one full cycle with a **fake judge + fake editor** (no Claude/Ollama):
  a "winning" fake edit commits and advances baseline; a "losing" one reverts.

The **live end-to-end** (one real cycle against the `:5001` experiment brain) is verified by
hand before the `/loop` driver is enabled.

## Known ceiling (accepted)

The optimizer chases *the judge's* score, and the judge has a recorded blind spot — it
over-credits mundane-but-coherent scenes (the user's "meh" scene G scored 4.4). So the loop
may converge toward **competent-but-mundane** bots. Acceptable for a first loop: it will be
visible in the run log, and the rubric can be sharpened later (a judge-spec revision), which
re-baselines the loop. Not fixed here.

## Out of scope (this step)

- Promotion of a tuned config to the **production** brain / live game (separate, human-gated).
- The optional one-time **C++ edit** to enable bot↔bot chat in the live game (master-spec
  step 6).
- Sharpening the judge rubric's "good" bar (a future judge-spec revision).
- Multi-edit / parallel-candidate search (one edit per cycle by design).
