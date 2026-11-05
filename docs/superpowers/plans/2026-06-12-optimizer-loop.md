# Optimizer Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-improving tuning loop that, each cycle, applies one whitelisted edit to the experiment brain config, regenerates eval scenes, scores them with the judge, and keeps-or-reverts through a strict 4-part gate — then a `/loop` driver repeats it unattended.

**Architecture:** Pure-Python optimizer modules under `sim/optimize/` (gate decision, run log, scene pools, whitelist guard, cycle orchestration), plus an experiment-brain runner and an optimizer prompt. The "config" is the actual source files (`prompts.py`, `personality.py`, `llm.py`); the experiment lane is a git branch; apply = edit files + restart `:5001` brain on a fresh DB; snapshot/rollback = git. Claude (in the `/loop`) performs the diagnose-and-edit step; everything else is mechanical and tested.

**Tech Stack:** Python 3.12, dataclasses, stdlib `json`/`subprocess`/`statistics`, pytest-bdd. Reuses `sim/judge.py` (`SceneScore`), `sim/run.py` (scene generation), the frozen `prompts/judge.md`, and the 8 golden anchors in `eval/calibration/`.

**Spec:** `docs/superpowers/specs/2026-06-12-optimizer-loop-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `sim/optimize/__init__.py` | package marker (empty) |
| `sim/optimize/gate.py` | PURE 4-part keep/revert decision — the safety core |
| `sim/optimize/runlog.py` | append/read one-line (JSONL) cycle records |
| `sim/optimize/pools.py` | load the 3 scene pools, assert disjoint, compute pool means |
| `sim/optimize/guard.py` | PURE whitelist check: which changed paths are out of scope |
| `sim/optimize/experiment_brain.py` | (re)start/stop the `:5001` brain on a fresh DB; mechanical |
| `sim/optimize/cycle.py` | orchestrate one cycle's mechanical half (evaluate candidate, finalize) |
| `prompts/optimizer.md` | how Claude diagnoses + proposes ONE bounded whitelisted edit |
| `eval/optimizer/manifest.json` | pools manifest (eval/held-out ids, golden ref, gate margin M) |
| `eval/optimizer/scenes/*.json` | generated eval + held-out transcripts |
| `tests/features/*.feature` + `tests/test_*.py` | BDD for gate, runlog, pools, guard, cycle |

**Canonical names/contracts used across tasks (do not rename):**
- Whitelist (MVP): `ALLOWED_PATHS = {"prompts.py", "personality.py", "llm.py"}`
- Buckets/dirs: golden anchors live in `eval/calibration/scenes/`; new pools in `eval/optimizer/scenes/`.
- Experiment brain: port `5001`, DB `/tmp/wbb-exp.db` (fresh each apply), `WBB_DB_PATH` env.
- Gate margin symbol: `M` (a float, calibrated in Task 8, stored in the manifest as `gate_margin`).
- `SceneScore` comes from `sim.judge` (fields: `scene_id, dimensions, gate_passed, gate_violation, score, diagnosis, weakest_dimension, set_version`).

---

### Task 1: The gate (pure 4-part decision)

**Files:**
- Create: `sim/optimize/__init__.py` (empty), `sim/optimize/gate.py`
- Create: `tests/features/gate.feature`, `tests/test_gate.py`

- [ ] **Step 1: Create the empty package marker** `sim/optimize/__init__.py` (no content).

- [ ] **Step 2: Write the feature** `tests/features/gate.feature`:

```gherkin
Feature: The promotion gate
  As the optimizer's safety core
  I want a candidate edit kept only if it clears noise, generalizes, stays in
  character, and does not coincide with judge drift
  So that unattended cycles cannot degrade the bots or fool themselves

  Background:
    Given a gate margin of 0.6

  Scenario: A clean win is kept
    Given baseline eval 2.0 and candidate eval 2.8
    And baseline held-out 2.0 and candidate held-out 2.3
    And 0 new lore failures
    And golden anchors at 3.0 frozen 3.0
    When I evaluate the gate
    Then the decision is keep

  Scenario: An eval gain within the margin is reverted
    Given baseline eval 2.0 and candidate eval 2.4
    And baseline held-out 2.0 and candidate held-out 2.3
    And 0 new lore failures
    And golden anchors at 3.0 frozen 3.0
    When I evaluate the gate
    Then the decision is revert because "eval gain <= margin"

  Scenario: A held-out regression is reverted
    Given baseline eval 2.0 and candidate eval 2.8
    And baseline held-out 2.0 and candidate held-out 1.9
    And 0 new lore failures
    And golden anchors at 3.0 frozen 3.0
    When I evaluate the gate
    Then the decision is revert because "held-out regressed"

  Scenario: A new lore failure is reverted
    Given baseline eval 2.0 and candidate eval 2.8
    And baseline held-out 2.0 and candidate held-out 2.3
    And 1 new lore failures
    And golden anchors at 3.0 frozen 3.0
    When I evaluate the gate
    Then the decision is revert because "new lore-gate failures"

  Scenario: Golden-anchor drift beyond the margin is reverted
    Given baseline eval 2.0 and candidate eval 2.8
    And baseline held-out 2.0 and candidate held-out 2.3
    And 0 new lore failures
    And golden anchors at 3.7 frozen 3.0
    When I evaluate the gate
    Then the decision is revert because "golden-anchor drift"
```

- [ ] **Step 3: Write the step defs** `tests/test_gate.py`:

```python
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.optimize.gate import GateInputs, evaluate_gate

scenarios("features/gate.feature")


@pytest.fixture
def ctx():
    return {}


@given(parsers.parse("a gate margin of {m:f}"))
def _margin(ctx, m):
    ctx["margin"] = m


@given(parsers.parse("baseline eval {b:f} and candidate eval {c:f}"))
def _eval(ctx, b, c):
    ctx["base_eval"], ctx["cand_eval"] = b, c


@given(parsers.parse("baseline held-out {b:f} and candidate held-out {c:f}"))
def _ho(ctx, b, c):
    ctx["base_ho"], ctx["cand_ho"] = b, c


@given(parsers.parse("{n:d} new lore failures"))
def _lore(ctx, n):
    ctx["new_lore"] = n


@given(parsers.parse("golden anchors at {a:f} frozen {f:f}"))
def _anchors(ctx, a, f):
    ctx["anchor"], ctx["anchor_frozen"] = a, f


@when("I evaluate the gate")
def _eval_gate(ctx):
    ctx["decision"] = evaluate_gate(GateInputs(
        baseline_eval_mean=ctx["base_eval"], candidate_eval_mean=ctx["cand_eval"],
        baseline_heldout_mean=ctx["base_ho"], candidate_heldout_mean=ctx["cand_ho"],
        new_lore_failures=ctx["new_lore"], anchor_mean=ctx["anchor"],
        anchor_frozen_mean=ctx["anchor_frozen"], margin=ctx["margin"],
    ))


@then("the decision is keep")
def _keep(ctx):
    assert ctx["decision"].keep, ctx["decision"]


@then(parsers.parse('the decision is revert because "{reason}"'))
def _revert(ctx, reason):
    assert not ctx["decision"].keep
    assert reason in ctx["decision"].reasons, ctx["decision"].reasons
```

- [ ] **Step 4: Run → FAIL** — `venv/bin/pytest tests/test_gate.py -q` → `ModuleNotFoundError: sim.optimize.gate`.

- [ ] **Step 5: Implement** `sim/optimize/gate.py`:

```python
"""The promotion gate — the optimizer's pure safety core.

A candidate edit is kept only if ALL four clauses hold. This is the entire
"don't degrade / don't fool yourself" argument, in one tested function.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateInputs:
    baseline_eval_mean: float
    candidate_eval_mean: float
    baseline_heldout_mean: float
    candidate_heldout_mean: float
    new_lore_failures: int
    anchor_mean: float
    anchor_frozen_mean: float
    margin: float  # M


@dataclass
class GateDecision:
    keep: bool
    reasons: list[str] = field(default_factory=list)  # failed clauses; empty == keep


def evaluate_gate(i: GateInputs) -> GateDecision:
    reasons: list[str] = []
    if not (i.candidate_eval_mean - i.baseline_eval_mean > i.margin):
        reasons.append("eval gain <= margin")
    if not (i.candidate_heldout_mean > i.baseline_heldout_mean):
        reasons.append("held-out regressed")
    if i.new_lore_failures > 0:
        reasons.append("new lore-gate failures")
    if abs(i.anchor_mean - i.anchor_frozen_mean) > i.margin:
        reasons.append("golden-anchor drift")
    return GateDecision(keep=not reasons, reasons=reasons)
```

- [ ] **Step 6: Run → PASS** — `venv/bin/pytest tests/test_gate.py -q` (5 scenarios). Then full suite `venv/bin/pytest -q`.

- [ ] **Step 7: Commit**

```bash
git add sim/optimize/__init__.py sim/optimize/gate.py tests/test_gate.py tests/features/gate.feature
git commit -m "feat(optimize): pure 4-part promotion gate (BDD)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The run log (JSONL cycle records)

**Files:**
- Create: `sim/optimize/runlog.py`
- Create: `tests/features/runlog.feature`, `tests/test_runlog.py`

- [ ] **Step 1: Write the feature** `tests/features/runlog.feature`:

```gherkin
Feature: The optimizer run log
  As the loop's audit trail
  I want each cycle appended as one record
  So that the whole run is reconstructable after the fact

  Scenario: Records append and read back in order
    Given an empty run log
    When I append a kept cycle 1 "raise warmth in chat prompt" eval 2.0 to 2.8
    And I append a reverted cycle 2 "shorten tick prompt" eval 2.8 to 2.9
    Then the log has 2 records
    And record 1 is kept with commit not empty
    And record 2 is not kept
```

- [ ] **Step 2: Write the step defs** `tests/test_runlog.py`:

```python
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.optimize.runlog import CycleRecord, append_record, read_records

scenarios("features/runlog.feature")


@pytest.fixture
def ctx(tmp_path):
    return {"path": tmp_path / "runlog.jsonl"}


@given("an empty run log")
def _empty(ctx):
    assert not ctx["path"].exists()


@when(parsers.parse('I append a kept cycle {n:d} "{summary}" eval {b:f} to {c:f}'))
def _append_kept(ctx, n, summary, b, c):
    append_record(ctx["path"], CycleRecord(
        cycle=n, edit_summary=summary, baseline_eval_mean=b, candidate_eval_mean=c,
        heldout_delta=0.3, kept=True, reasons=[], commit_sha="abc123"))


@when(parsers.parse('I append a reverted cycle {n:d} "{summary}" eval {b:f} to {c:f}'))
def _append_revert(ctx, n, summary, b, c):
    append_record(ctx["path"], CycleRecord(
        cycle=n, edit_summary=summary, baseline_eval_mean=b, candidate_eval_mean=c,
        heldout_delta=0.0, kept=False, reasons=["eval gain <= margin"], commit_sha="def456"))


@then(parsers.parse("the log has {n:d} records"))
def _count(ctx, n):
    ctx["recs"] = read_records(ctx["path"])
    assert len(ctx["recs"]) == n


@then("record 1 is kept with commit not empty")
def _r1(ctx):
    r = ctx["recs"][0]
    assert r.kept and r.commit_sha


@then("record 2 is not kept")
def _r2(ctx):
    assert not ctx["recs"][1].kept
```

- [ ] **Step 3: Run → FAIL** — `venv/bin/pytest tests/test_runlog.py -q`.

- [ ] **Step 4: Implement** `sim/optimize/runlog.py`:

```python
"""Append-only JSONL audit trail: one CycleRecord per optimize cycle."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class CycleRecord:
    cycle: int
    edit_summary: str
    baseline_eval_mean: float
    candidate_eval_mean: float
    heldout_delta: float
    kept: bool
    reasons: list[str] = field(default_factory=list)
    commit_sha: str = ""


def append_record(path, rec: CycleRecord) -> None:
    with Path(path).open("a") as f:
        f.write(json.dumps(asdict(rec)) + "\n")


def read_records(path) -> list[CycleRecord]:
    p = Path(path)
    if not p.exists():
        return []
    return [CycleRecord(**json.loads(line)) for line in p.read_text().splitlines() if line.strip()]
```

- [ ] **Step 5: Run → PASS**, then full suite.

- [ ] **Step 6: Commit**

```bash
git add sim/optimize/runlog.py tests/test_runlog.py tests/features/runlog.feature
git commit -m "feat(optimize): JSONL run log of cycle records (BDD)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Scene pools (load, disjoint, pool mean)

**Files:**
- Create: `sim/optimize/pools.py`
- Create: `tests/features/pools.feature`, `tests/test_pools.py`

- [ ] **Step 1: Write the feature** `tests/features/pools.feature`:

```gherkin
Feature: Optimizer scene pools
  As the eval substrate
  I want three named, provably-disjoint pools and a way to average a pool
  So that the optimizer never trains and gates on the same scenes

  Scenario: Disjoint pools load and report their sizes
    Given a manifest with golden "g1","g2" eval "e1","e2","e3" heldout "h1","h2"
    When I load the pools
    Then golden has 2, eval has 3, heldout has 2
    And the pools are disjoint

  Scenario: Overlapping pools are rejected
    Given a manifest with golden "g1" eval "e1","g1" heldout "h1"
    When I load the pools
    Then loading raises a disjointness error

  Scenario: Pool mean averages the named scenes' scores
    Given scores e1=2.0 e2=3.0 e3=4.0
    Then the mean of eval "e1","e2","e3" is 3.0
```

- [ ] **Step 2: Write the step defs** `tests/test_pools.py`:

```python
import json
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.judge import SceneScore, DIMENSIONS
from sim.optimize.pools import load_pools, pool_mean, PoolsError

scenarios("features/pools.feature")


def _score(sid, val):
    return SceneScore(scene_id=sid, dimensions={d: int(val) for d in DIMENSIONS},
                      gate_passed=True, gate_violation=None, score=val,
                      diagnosis="", weakest_dimension="intentions")


def _csv(s):  # 'a','b' -> ["a","b"]
    return [x.strip().strip('"') for x in s.split(",")]


@pytest.fixture
def ctx(tmp_path):
    return {"tmp": tmp_path}


@given(parsers.parse('a manifest with golden {g} eval {e} heldout {h}'))
def _manifest(ctx, g, e, h):
    m = {"set_version": "v1", "gate_margin": 0.6,
         "golden_dir": "eval/calibration/scenes", "golden": _csv(g),
         "scenes_dir": "eval/optimizer/scenes", "eval": _csv(e), "heldout": _csv(h)}
    p = ctx["tmp"] / "manifest.json"
    p.write_text(json.dumps(m))
    ctx["manifest"] = p


@when("I load the pools")
def _load(ctx):
    try:
        ctx["pools"] = load_pools(ctx["manifest"])
    except PoolsError as e:
        ctx["error"] = e


@then(parsers.parse("golden has {a:d}, eval has {b:d}, heldout has {c:d}"))
def _sizes(ctx, a, b, c):
    p = ctx["pools"]
    assert (len(p.golden), len(p.eval), len(p.heldout)) == (a, b, c)


@then("the pools are disjoint")
def _disjoint(ctx):
    p = ctx["pools"]
    assert set(p.golden).isdisjoint(p.eval)
    assert set(p.eval).isdisjoint(p.heldout)
    assert set(p.golden).isdisjoint(p.heldout)


@then("loading raises a disjointness error")
def _raises(ctx):
    assert isinstance(ctx.get("error"), PoolsError)


@given(parsers.parse("scores e1={a:f} e2={b:f} e3={c:f}"))
def _scores(ctx, a, b, c):
    ctx["scores"] = {"e1": _score("e1", a), "e2": _score("e2", b), "e3": _score("e3", c)}


@then(parsers.parse('the mean of eval {ids} is {expected:f}'))
def _mean(ctx, ids, expected):
    assert pool_mean(ctx["scores"], _csv(ids)) == pytest.approx(expected)
```

- [ ] **Step 3: Run → FAIL** — `venv/bin/pytest tests/test_pools.py -q`.

- [ ] **Step 4: Implement** `sim/optimize/pools.py`:

```python
"""Load the three optimizer scene pools and guarantee they never overlap.

golden = drift ruler (never optimized against); eval = what candidates are scored
on; heldout = the anti-overfit gate. Overlap would let the loop train and grade on
the same scenes, so it is a hard error.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from sim.judge import SceneScore


class PoolsError(ValueError):
    pass


@dataclass
class Pools:
    golden: list[str]
    eval: list[str]
    heldout: list[str]
    golden_dir: str
    scenes_dir: str
    gate_margin: float
    set_version: str


def load_pools(manifest_path) -> Pools:
    m = json.loads(Path(manifest_path).read_text())
    p = Pools(golden=m["golden"], eval=m["eval"], heldout=m["heldout"],
              golden_dir=m["golden_dir"], scenes_dir=m["scenes_dir"],
              gate_margin=m["gate_margin"], set_version=m["set_version"])
    for a, b in (("golden", "eval"), ("eval", "heldout"), ("golden", "heldout")):
        overlap = set(getattr(p, a)) & set(getattr(p, b))
        if overlap:
            raise PoolsError(f"pools {a} and {b} overlap: {sorted(overlap)}")
    return p


def pool_mean(scores: dict[str, SceneScore], ids: list[str]) -> float:
    return float(mean(scores[i].score for i in ids))
```

- [ ] **Step 5: Run → PASS**, then full suite.

- [ ] **Step 6: Commit**

```bash
git add sim/optimize/pools.py tests/test_pools.py tests/features/pools.feature
git commit -m "feat(optimize): scene pools loader with disjointness guard (BDD)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: The whitelist guard (pure)

**Files:**
- Create: `sim/optimize/guard.py`
- Create: `tests/features/guard.feature`, `tests/test_guard.py`

- [ ] **Step 1: Write the feature** `tests/features/guard.feature`:

```gherkin
Feature: Edit whitelist guard
  As the loop's blast-radius limiter
  I want any change outside the allowed config files flagged
  So that a cycle can never touch C++, the prod DB, or unrelated code

  Scenario: An in-scope edit is allowed
    Given changed paths "prompts.py","personality.py"
    Then no paths are out of scope

  Scenario: An out-of-scope edit is flagged
    Given changed paths "prompts.py","sim/scene_runner.py","main.py"
    Then the out-of-scope paths are "sim/scene_runner.py","main.py"
```

- [ ] **Step 2: Write the step defs** `tests/test_guard.py`:

```python
import pytest
from pytest_bdd import scenarios, given, then, parsers

from sim.optimize.guard import ALLOWED_PATHS, out_of_scope

scenarios("features/guard.feature")


def _csv(s):
    return [x.strip().strip('"') for x in s.split(",")]


@pytest.fixture
def ctx():
    return {}


@given(parsers.parse("changed paths {paths}"))
def _changed(ctx, paths):
    ctx["changed"] = _csv(paths)


@then("no paths are out of scope")
def _none(ctx):
    assert out_of_scope(ctx["changed"], ALLOWED_PATHS) == []


@then(parsers.parse("the out-of-scope paths are {paths}"))
def _some(ctx, paths):
    assert out_of_scope(ctx["changed"], ALLOWED_PATHS) == _csv(paths)
```

- [ ] **Step 3: Run → FAIL** — `venv/bin/pytest tests/test_guard.py -q`.

- [ ] **Step 4: Implement** `sim/optimize/guard.py`:

```python
"""Whitelist guard: only these brain-config files may change in a cycle.

MVP excludes sim orchestration on purpose — editing the scene generator would let
the optimizer game its own eval. Tune the brain; keep the exam fixed.
"""
from __future__ import annotations

# Relative to repo root, matching `git diff --name-only` output.
ALLOWED_PATHS = {"prompts.py", "personality.py", "llm.py"}


def out_of_scope(changed_paths: list[str], allowed: set[str]) -> list[str]:
    """Return changed paths that are NOT in the whitelist (order preserved)."""
    return [p for p in changed_paths if p not in allowed]
```

- [ ] **Step 5: Run → PASS**, then full suite.

- [ ] **Step 6: Commit**

```bash
git add sim/optimize/guard.py tests/test_guard.py tests/features/guard.feature
git commit -m "feat(optimize): pure whitelist guard for cycle edits (BDD)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Experiment-brain runner (mechanical)

**Files:**
- Create: `sim/optimize/experiment_brain.py`
- Create: `tests/test_experiment_brain.py` (light: command construction only)

- [ ] **Step 1: Write the failing test** `tests/test_experiment_brain.py` (we unit-test only the pure command builder; start/stop are exercised live in Task 8):

```python
from sim.optimize.experiment_brain import uvicorn_cmd


def test_uvicorn_cmd_uses_fresh_db_and_port():
    cmd = uvicorn_cmd(port=5001, db_path="/tmp/wbb-exp.db")
    assert cmd[:3] == ["venv/bin/uvicorn", "main:app", "--host"]
    assert "5001" in cmd
    # db path is passed via env, not argv:
    assert "/tmp/wbb-exp.db" not in cmd
```

- [ ] **Step 2: Run → FAIL** — `venv/bin/pytest tests/test_experiment_brain.py -q`.

- [ ] **Step 3: Implement** `sim/optimize/experiment_brain.py`:

```python
"""Start/stop the experiment brain on :5001 with a FRESH DB each apply.

A fresh DB is required because identities are copied into bot_personalities rows at
creation, so prompt/identity edits only take effect on a clean DB. This module is
mechanical (subprocess); only uvicorn_cmd is unit-tested, the rest is exercised live.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx


def uvicorn_cmd(port: int = 5001, db_path: str = "/tmp/wbb-exp.db") -> list[str]:
    # db_path goes through env (WBB_DB_PATH), not argv — see start_experiment_brain.
    return ["venv/bin/uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)]


def start_experiment_brain(port: int = 5001, db_path: str = "/tmp/wbb-exp.db",
                           log_path: str = "/tmp/wbb-exp-brain.log",
                           ready_timeout: float = 20.0) -> subprocess.Popen:
    """Delete any old DB, launch a fresh brain, block until it answers /docs."""
    Path(db_path).unlink(missing_ok=True)
    env = {**os.environ, "WBB_DB_PATH": db_path}
    log = open(log_path, "w")
    proc = subprocess.Popen(uvicorn_cmd(port, db_path), env=env, stdout=log, stderr=log)
    deadline = time.time() + ready_timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/docs", timeout=2).status_code == 200:
                return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"experiment brain did not become ready on :{port}")


def stop_experiment_brain(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
```

- [ ] **Step 4: Run → PASS** the unit test, then full suite.

- [ ] **Step 5: Commit**

```bash
git add sim/optimize/experiment_brain.py tests/test_experiment_brain.py
git commit -m "feat(optimize): experiment-brain runner (fresh-DB restart)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Cycle orchestration (mechanical half, tested with fakes)

**Files:**
- Create: `sim/optimize/cycle.py`
- Create: `tests/features/cycle.feature`, `tests/test_cycle.py`

This is the mechanical half of a cycle: given that Claude has already edited files, `evaluate_candidate` regenerates+scores, and `finalize` runs the gate and commits-or-reverts via injected callbacks. The diagnose/edit step is done by Claude in the `/loop` (Task 10), not here.

- [ ] **Step 1: Write the feature** `tests/features/cycle.feature`:

```gherkin
Feature: One optimize cycle (mechanical half)
  As the loop body
  I want to evaluate a candidate and finalize keep-or-revert
  So that the smart edit Claude made is gated and recorded deterministically

  Scenario: A winning candidate commits and advances baseline
    Given a candidate that scores eval 2.8 and held-out 2.3 with 0 new lore failures
    And the baseline is eval 2.0 held-out 2.0 and margin 0.6
    And golden anchors at 3.0 frozen 3.0
    When I finalize the cycle 1 "warmer chat prompt"
    Then the cycle is kept
    And git commit was called
    And the run log has 1 kept record

  Scenario: A losing candidate reverts and does not advance baseline
    Given a candidate that scores eval 2.3 and held-out 2.3 with 0 new lore failures
    And the baseline is eval 2.0 held-out 2.0 and margin 0.6
    And golden anchors at 3.0 frozen 3.0
    When I finalize the cycle 2 "shorter tick prompt"
    Then the cycle is reverted
    And git revert was called
    And the run log has 1 not-kept record
```

- [ ] **Step 2: Write the step defs** `tests/test_cycle.py`:

```python
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.optimize.cycle import finalize, CandidateResult
from sim.optimize.runlog import read_records

scenarios("features/cycle.feature")


@pytest.fixture
def ctx(tmp_path):
    return {"runlog": tmp_path / "runlog.jsonl", "git_calls": []}


@given(parsers.parse("a candidate that scores eval {e:f} and held-out {h:f} "
                     "with {lore:d} new lore failures"))
def _cand(ctx, e, h, lore):
    ctx["cand"] = CandidateResult(eval_mean=e, heldout_mean=h, new_lore_failures=lore)


@given(parsers.parse("the baseline is eval {e:f} held-out {h:f} and margin {m:f}"))
def _base(ctx, e, h, m):
    ctx["base_eval"], ctx["base_ho"], ctx["margin"] = e, h, m


@given(parsers.parse("golden anchors at {a:f} frozen {f:f}"))
def _anchors(ctx, a, f):
    ctx["anchor"], ctx["frozen"] = a, f


@when(parsers.parse('I finalize the cycle {n:d} "{summary}"'))
def _finalize(ctx, n, summary):
    def fake_commit(msg):
        ctx["git_calls"].append(("commit", msg)); return "sha123"
    def fake_revert():
        ctx["git_calls"].append(("revert", None))
    ctx["decision"] = finalize(
        cycle=n, edit_summary=summary, candidate=ctx["cand"],
        baseline_eval_mean=ctx["base_eval"], baseline_heldout_mean=ctx["base_ho"],
        anchor_mean=ctx["anchor"], anchor_frozen_mean=ctx["frozen"], margin=ctx["margin"],
        runlog_path=ctx["runlog"], commit=fake_commit, revert=fake_revert)


@then("the cycle is kept")
def _kept(ctx):
    assert ctx["decision"].keep


@then("the cycle is reverted")
def _rev(ctx):
    assert not ctx["decision"].keep


@then("git commit was called")
def _commit(ctx):
    assert ("commit", "warmer chat prompt") in [(k, m) for k, m in ctx["git_calls"]] or \
           any(k == "commit" for k, _ in ctx["git_calls"])


@then("git revert was called")
def _revert_called(ctx):
    assert any(k == "revert" for k, _ in ctx["git_calls"])


@then(parsers.parse("the run log has {n:d} kept record"))
def _kept_log(ctx, n):
    recs = read_records(ctx["runlog"])
    assert len([r for r in recs if r.kept]) == n


@then(parsers.parse("the run log has {n:d} not-kept record"))
def _notkept_log(ctx, n):
    recs = read_records(ctx["runlog"])
    assert len([r for r in recs if not r.kept]) == n
```

- [ ] **Step 3: Run → FAIL** — `venv/bin/pytest tests/test_cycle.py -q`.

- [ ] **Step 4: Implement** `sim/optimize/cycle.py`:

```python
"""One optimize cycle's mechanical half: gate a candidate and record the outcome.

The smart half (diagnose + edit source files) is done by Claude in the /loop before
calling finalize(). Here we only run the pure gate and commit-or-revert via injected
callbacks, so this is fully testable without git/Claude/Ollama.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sim.optimize.gate import GateInputs, GateDecision, evaluate_gate
from sim.optimize.runlog import CycleRecord, append_record


@dataclass
class CandidateResult:
    eval_mean: float
    heldout_mean: float
    new_lore_failures: int


def finalize(*, cycle: int, edit_summary: str, candidate: CandidateResult,
             baseline_eval_mean: float, baseline_heldout_mean: float,
             anchor_mean: float, anchor_frozen_mean: float, margin: float,
             runlog_path, commit: Callable[[str], str], revert: Callable[[], None]
             ) -> GateDecision:
    decision = evaluate_gate(GateInputs(
        baseline_eval_mean=baseline_eval_mean, candidate_eval_mean=candidate.eval_mean,
        baseline_heldout_mean=baseline_heldout_mean, candidate_heldout_mean=candidate.heldout_mean,
        new_lore_failures=candidate.new_lore_failures, anchor_mean=anchor_mean,
        anchor_frozen_mean=anchor_frozen_mean, margin=margin))
    if decision.keep:
        sha = commit(edit_summary)
    else:
        revert()
        sha = ""
    append_record(runlog_path, CycleRecord(
        cycle=cycle, edit_summary=edit_summary,
        baseline_eval_mean=baseline_eval_mean, candidate_eval_mean=candidate.eval_mean,
        heldout_delta=candidate.heldout_mean - baseline_heldout_mean,
        kept=decision.keep, reasons=decision.reasons, commit_sha=sha))
    return decision
```

- [ ] **Step 5: Run → PASS**, then full suite.

- [ ] **Step 6: Commit**

```bash
git add sim/optimize/cycle.py tests/test_cycle.py tests/features/cycle.feature
git commit -m "feat(optimize): cycle finalize — gate + commit/revert + log (BDD, fakes)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: The optimizer prompt

**Files:**
- Create: `prompts/optimizer.md`
- Create: `tests/test_optimizer_prompt.py`

- [ ] **Step 1: Write the failing test** `tests/test_optimizer_prompt.py`:

```python
from pathlib import Path

from sim.optimize.guard import ALLOWED_PATHS


def test_optimizer_prompt_names_whitelist_and_rules():
    text = Path("prompts/optimizer.md").read_text()
    for p in ALLOWED_PATHS:
        assert p in text, f"optimizer prompt missing whitelisted file {p}"
    for token in ["ONE", "weakest", "diagnose", "do NOT", "orchestration"]:
        assert token in text, f"optimizer prompt missing {token}"
```

- [ ] **Step 2: Run → FAIL** — `venv/bin/pytest tests/test_optimizer_prompt.py -q`.

- [ ] **Step 3: Implement** `prompts/optimizer.md` (exact content):

```markdown
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
```

- [ ] **Step 4: Run → PASS**, then full suite.

- [ ] **Step 5: Commit**

```bash
git add prompts/optimizer.md tests/test_optimizer_prompt.py
git commit -m "feat(optimize): optimizer prompt artifact (whitelist + one-edit rule)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Generate the pools live + calibrate the gate margin M

> Live/integration task. Uses the `:5001` experiment brain and the judge (Claude scores).
> Produces `eval/optimizer/scenes/*.json` + `eval/optimizer/manifest.json`.

**Files:**
- Create: `eval/optimizer/scenes/*.json` (24 generated transcripts)
- Create: `eval/optimizer/manifest.json`

No new `SceneSpec` entries are needed: we generate 24 distinct transcripts by running the
3 existing catalog specs across 8 seeds, with seed-suffixed ids so eval and held-out are
disjoint.

- [ ] **Step 1: Start a fresh experiment brain** on :5001:

```bash
venv/bin/python -c "from sim.optimize.experiment_brain import start_experiment_brain as s; s(); print('ready')"
```

- [ ] **Step 2: Generate the 24 transcripts** (3 catalog specs × 8 seeds) into
  `eval/optimizer/scenes/`, each id suffixed `-s<seed>`:

```bash
venv/bin/python - <<'PY'
from pathlib import Path
from sim import scenes
from sim.brain_client import BrainClient
from sim.scene_runner import run_scene
out = Path("eval/optimizer/scenes"); out.mkdir(parents=True, exist_ok=True)
brain = BrainClient(base_url="http://localhost:5001")
made = []
for seed in [11, 12, 13, 14, 15, 16, 17, 18]:
    for sp in scenes.all_specs():
        sid = f"{sp.scene_id}-s{seed}"
        sc = run_scene(brain=brain, scene_id=sid, location=sp.location, channel=sp.channel,
                       bots=list(sp.bots), player=sp.player, turns=sp.turns, seed=seed)
        sc.save(out / f"{sid}.json"); made.append(sid)
print(len(made), "scenes generated")
PY
ls eval/optimizer/scenes | wc -l   # expect 24
```

- [ ] **Step 3: Build the manifest programmatically** (sort ids, split 16 eval / 8 held-out;
  the loader proves disjointness):

```bash
venv/bin/python - <<'PY'
import json, glob, os
ids = sorted(os.path.basename(p)[:-5] for p in glob.glob("eval/optimizer/scenes/*.json"))
assert len(ids) == 24, f"expected 24, got {len(ids)}"
manifest = {
  "set_version": "v1",
  "gate_margin": 0.6,  # placeholder; overwritten by Step 4
  "golden_dir": "eval/calibration/scenes",
  "golden": ["westfall-lfg","orgrimmar-banter","ambient-no-player","planted-good-lfg",
             "planted-good-banter","planted-bad-talkpast","planted-bad-anachronism","planted-bad-aireveal"],
  "scenes_dir": "eval/optimizer/scenes",
  "eval": ids[:16],
  "heldout": ids[16:],
}
json.dump(manifest, open("eval/optimizer/manifest.json", "w"), indent=2)
from sim.optimize.pools import load_pools
load_pools("eval/optimizer/manifest.json")  # raises PoolsError if any overlap
print("manifest written; pools load and are disjoint")
PY
```

- [ ] **Step 4: Calibrate M (generation+judge band).** Regenerate the eval pool a SECOND time
  with the same baseline config (re-run Step 2's loop into a temp dir for just the 16 eval ids),
  have Claude score both passes cold against `prompts/judge.md`, and compute the max per-scene
  |score difference| across the two generations. Then set `gate_margin` in the manifest:

```bash
venv/bin/python - <<'PY'
import json
M = max(0.4, MEASURED_SPREAD)  # replace MEASURED_SPREAD with the computed number
m = json.load(open("eval/optimizer/manifest.json"))
m["gate_margin"] = round(M, 2)
json.dump(m, open("eval/optimizer/manifest.json", "w"), indent=2)
print("gate_margin M =", m["gate_margin"])
PY
```
(This is why M ≥ the judge-only 0.4: it also absorbs scene-regeneration variance.)

- [ ] **Step 5: Commit**

```bash
git add eval/optimizer/
git commit -m "test(optimize): generate eval+held-out pools (24 scenes) + calibrate gate margin M

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Live one-cycle verification (the proof before the loop)

> Human-in-the-loop / Claude-acting task. Run ONE real cycle end-to-end by hand and confirm
> the machinery works before any unattended looping. NO new code unless a bug is found.

- [ ] **Step 1:** Create and switch to an experiment branch: `git checkout -b optimizer-run`.

- [ ] **Step 2: Establish baseline.** Start the fresh experiment brain (Task 8 Step 2), generate
  the eval+held-out pools' scenes with the current config (already done in Task 8), and have
  Claude score them → record baseline eval mean and held-out mean.

- [ ] **Step 3: Diagnose + edit (Claude).** Following `prompts/optimizer.md`, read the lowest
  eval scenes + their diagnoses + the current `prompts.py`/`personality.py`/`llm.py`, and make
  ONE whitelisted edit targeting the weakest dimension.

- [ ] **Step 4: Guard check.**

```bash
venv/bin/python -c "
import subprocess
from sim.optimize.guard import ALLOWED_PATHS, out_of_scope
changed = subprocess.check_output(['git','diff','--name-only']).decode().split()
bad = out_of_scope(changed, ALLOWED_PATHS)
assert not bad, f'edit touched out-of-scope files: {bad}'
print('guard ok:', changed)
"
```

- [ ] **Step 5: Evaluate candidate.** Restart the experiment brain (fresh DB) so the edit takes
  effect, regenerate the **eval** scenes, score them with Claude → candidate eval mean, count of
  new lore failures vs baseline, and the golden-anchor mean.
  **Efficiency — held-out is the LAST gate clause, so score it last and only if needed:** only
  regenerate+score the held-out pool if the candidate already clears the cheaper clauses (eval
  gain > M, no new lore failures, no anchor drift). If it fails any of those, it will revert
  regardless, so skip held-out and pass `candidate_heldout_mean = baseline_heldout_mean` to
  `finalize` (delta 0). This saves Claude budget on the many reverting cycles.

- [ ] **Step 6: Finalize via the tested path.** Call `sim.optimize.cycle.finalize(...)` with real
  `commit`/`revert` callbacks (a real git commit of the 3 config files, or `git checkout -- <files>`),
  margin = manifest `gate_margin`, writing to `eval/optimizer/runlog.jsonl`. Confirm the run-log
  record and the git state match the decision (a kept cycle = a commit; a reverted cycle = clean tree).

- [ ] **Step 7:** Confirm the full unit suite still passes (`venv/bin/pytest -q`) and the run log
  has exactly one record. Report the cycle outcome (kept/reverted + reason). If anything in the
  machinery misbehaved, STOP and fix it before Task 10 — this is the gate before unattended running.

- [ ] **Step 8: Commit the run artifacts** (run log; the config commit already happened if kept):

```bash
git add eval/optimizer/runlog.jsonl
git commit -m "test(optimize): first live cycle verified end-to-end

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: The /loop driver (enable self-iteration)

> Wires the verified cycle into a self-paced loop. Only enable after Task 9 passed.

**Files:**
- Create: `sim/optimize/loop_cycle.py` (a single entry that runs ONE full cycle, calling the
  verified pieces) — so the `/loop` invocation is a thin, repeatable command.

- [ ] **Step 1:** Implement `sim/optimize/loop_cycle.py` exposing
  `run_one_cycle(cycle_no, score_fn, *, manifest_path, runlog_path, baseline)`. It performs the
  Task-9 MECHANICAL sequence (guard-check the working tree, restart fresh brain, regenerate the
  eval pool, apply the held-out short-circuit, run `finalize`) and returns the `CycleRecord`.
  Two collaborators are injected so the function stays testable and honest about who scores:
  - `score_fn(scene_paths: list[str]) -> dict[str, SceneScore]` — the **judge**. Because the
    judge is manual-first (Claude scores in-session), the `/loop` session supplies a `score_fn`
    that scores against `prompts/judge.md`; tests pass a fake.
  - the diagnose/edit step is NOT inside `run_one_cycle` — Claude makes its one whitelisted edit
    first, then calls `run_one_cycle`. Document this contract at the top of the file.
  `run_one_cycle` is verified by the live supervised run (Step 4), not a unit test (its parts —
  `finalize`, `gate`, `pools`, `guard`, `experiment_brain` — are each already tested).

- [ ] **Step 2:** Add a stop-condition helper `should_stop(records, k=8)` returning True when the
  last `k` records are all `kept == False` (convergence). Unit-test it:

```python
# tests/test_loop_cycle.py
from sim.optimize.loop_cycle import should_stop
from sim.optimize.runlog import CycleRecord

def _rec(kept):
    return CycleRecord(cycle=0, edit_summary="", baseline_eval_mean=0, candidate_eval_mean=0,
                       heldout_delta=0, kept=kept)

def test_should_stop_after_k_no_wins():
    assert should_stop([_rec(False)] * 8, k=8)
    assert not should_stop([_rec(False)] * 7 + [_rec(True)], k=8)
    assert not should_stop([_rec(False)] * 3, k=8)
```
Run → FAIL → implement `should_stop` → PASS.

- [ ] **Step 3:** Drive it with the `/loop` skill (self-paced). The loop prompt each wake:
  "Run optimizer cycle N: read the lowest eval scenes, make ONE whitelisted edit per
  `prompts/optimizer.md`, then call `run_one_cycle(N)`; if `should_stop` or golden-anchor drift,
  stop and summarize." The `/loop` self-paces (~one cycle / 10–15 min) and backs off on rate
  limits. Pause/stop conditions: convergence (`should_stop`), golden-anchor drift (a `finalize`
  revert with reason `golden-anchor drift`), rate-limit exhaustion, or user interrupt.

- [ ] **Step 4:** Do a SHORT supervised run first — 2–3 cycles watched live — to confirm cadence,
  guard, gate, and the run log all behave under the driver. Then it can run unattended.

- [ ] **Step 5: Commit**

```bash
git add sim/optimize/loop_cycle.py tests/test_loop_cycle.py
git commit -m "feat(optimize): loop entry + convergence stop; /loop driver

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for the executor
- Run all pytest via `venv/bin/pytest`. Full suite stays green after every task.
- Tasks 1–7 are pure/mechanical TDD — safe for subagents. Task 8 generates data (live brain + Claude scoring). Tasks 9–10 are Claude-acting / human-supervised and run in the main session.
- Experiment brain only (`:5001`, `/tmp/wbb-exp.db`); never touch prod `:5000` or the prod DB.
- The optimizer runs on the `optimizer-run` branch; promotion of any tuned config to the live game is OUT OF SCOPE (separate, human-gated).
- Known ceiling: the loop chases the judge, which over-credits mundane coherence — expect competent-but-mundane convergence; revisit via a judge-spec revision later.
- **Spec reconciliation:** the spec named a `config_snapshot.py`. This plan realizes that
  responsibility with the simpler **file-edit + git** model decided at plan time: the config IS
  the source files, the snapshot/rollback IS git (commit/`checkout`), `experiment_brain.py`
  applies a config by restarting on a fresh DB, and `guard.py` enforces the whitelist via
  `git diff`. Same guarantees (atomic apply, full rollback, blast-radius limit), fewer moving
  parts. MVP whitelist is brain-config only (`prompts.py`, `personality.py`, `llm.py`); sim
  orchestration is intentionally excluded so the loop can't game its own eval substrate.
