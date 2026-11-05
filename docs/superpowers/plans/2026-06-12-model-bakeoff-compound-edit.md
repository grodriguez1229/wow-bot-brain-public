# Model Bake-off + Compound Template Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test the "qwen3.5:9b is a model ceiling" hypothesis via a 3-model bake-off, then apply a compound template-diversification edit on the winning model, with clean attribution of model effect vs. template effect.

**Architecture:** A new pure `sim/optimize/bakeoff.py` module records one scored row per model and picks a viable winner; `regen_eval` gains a `pool` param so held-out scenes can be regenerated too. The actual model runs, scoring (Claude-as-judge, frozen rubric), and content edits are executed as documented procedure tasks against the existing eval/held-out/anchor harness. Nothing auto-merges.

**Tech Stack:** Python 3, pytest-bdd (Gherkin), httpx, local Ollama (<ollama-host>:11434), uvicorn experiment brain on :5001, git on branch `optimizer-run`.

**Spec:** `docs/superpowers/specs/2026-06-12-model-bakeoff-compound-edit-design.md`

---

## File Structure

- **Create** `sim/optimize/bakeoff.py` — `BakeoffRow` dataclass, `record_row`/`read_rows` (JSONL), `pick_winner`, `timed_regen` (times a regen and returns seconds-per-scene). Pure + thin orchestration; one responsibility: bake-off bookkeeping.
- **Create** `tests/features/bakeoff.feature` + `tests/test_bakeoff.py` — Gherkin coverage for `pick_winner` and the record/read roundtrip, following the `tests/test_gate.py` pattern.
- **Modify** `sim/optimize/loop_cycle.py:47` — add `pool: str = "eval"` to `regen_eval` so it can regenerate the `heldout` pool.
- **Create** `eval/bakeoff/rows.jsonl` (run output) — one `BakeoffRow` per model.
- **Create** `eval/bakeoff/phaseB.json` (run output) — Phase B candidate scores + gate decision.
- **Modify** `personality.py`, `prompts.py` — Phase B compound edit (whitelisted).

---

## Task 1: BakeoffRow + record/read roundtrip

**Files:**
- Create: `sim/optimize/bakeoff.py`
- Test: `tests/test_bakeoff.py`, `tests/features/bakeoff.feature`

- [ ] **Step 1: Write the failing feature**

Create `tests/features/bakeoff.feature`:

```gherkin
Feature: Model bake-off bookkeeping
  As the model-comparison harness
  I want each model's score and speed recorded, and a viable winner chosen
  So that a model swap is an evidence-based reset of the baseline, not a guess

  Scenario: A recorded row round-trips through the log
    Given a bake-off row for "mistral-small:22b" eval 2.6 seconds-per-scene 40.0
    When I write it and read the log back
    Then the log has 1 row for "mistral-small:22b" with eval 2.6

  Scenario: The strongest viable model wins
    Given a logged row "qwen3.5:9b" eval 1.98 seconds-per-scene 12.0
    And a logged row "gemma4:latest" eval 2.30 seconds-per-scene 20.0
    And a logged row "mistral-small:22b" eval 2.75 seconds-per-scene 45.0
    When I pick the winner over baseline "qwen3.5:9b" eval 1.98 margin 0.5 max-seconds 90.0
    Then the winner is "mistral-small:22b"

  Scenario: A model that does not clear the margin loses to the baseline
    Given a logged row "qwen3.5:9b" eval 1.98 seconds-per-scene 12.0
    And a logged row "gemma4:latest" eval 2.30 seconds-per-scene 20.0
    When I pick the winner over baseline "qwen3.5:9b" eval 1.98 margin 0.5 max-seconds 90.0
    Then the winner is "qwen3.5:9b"

  Scenario: A strong but too-slow model is rejected as non-viable
    Given a logged row "qwen3.5:9b" eval 1.98 seconds-per-scene 12.0
    And a logged row "mistral-small:22b" eval 2.90 seconds-per-scene 120.0
    When I pick the winner over baseline "qwen3.5:9b" eval 1.98 margin 0.5 max-seconds 90.0
    Then the winner is "qwen3.5:9b"
```

- [ ] **Step 2: Write the failing step defs**

Create `tests/test_bakeoff.py`:

```python
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.optimize.bakeoff import BakeoffRow, record_row, read_rows, pick_winner

scenarios("features/bakeoff.feature")


@pytest.fixture
def ctx():
    return {"rows": []}


@given(parsers.parse(
    'a bake-off row for "{model}" eval {ev:f} seconds-per-scene {sp:f}'))
def _row(ctx, model, ev, sp):
    ctx["row"] = BakeoffRow(model=model, eval_mean=ev, seconds_per_scene=sp)


@when("I write it and read the log back")
def _roundtrip(ctx, tmp_path):
    p = tmp_path / "rows.jsonl"
    record_row(str(p), ctx["row"])
    ctx["read"] = read_rows(str(p))


@then(parsers.parse('the log has {n:d} row for "{model}" with eval {ev:f}'))
def _check(ctx, n, model, ev):
    assert len(ctx["read"]) == n
    assert ctx["read"][0].model == model
    assert ctx["read"][0].eval_mean == ev


@given(parsers.parse(
    'a logged row "{model}" eval {ev:f} seconds-per-scene {sp:f}'))
def _logged(ctx, model, ev, sp):
    ctx["rows"].append(BakeoffRow(model=model, eval_mean=ev, seconds_per_scene=sp))


@when(parsers.parse(
    'I pick the winner over baseline "{bm}" eval {bme:f} margin {m:f} max-seconds {mx:f}'))
def _pick(ctx, bm, bme, m, mx):
    ctx["winner"] = pick_winner(ctx["rows"], baseline_model=bm,
                                baseline_mean=bme, margin=m, max_seconds_per_scene=mx)


@then(parsers.parse('the winner is "{model}"'))
def _winner(ctx, model):
    assert ctx["winner"] == model, ctx["winner"]
```

- [ ] **Step 3: Run to verify failure**

Run: `cd ~/wow-bot-brain && venv/bin/pytest tests/test_bakeoff.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.optimize.bakeoff'`

- [ ] **Step 4: Implement `sim/optimize/bakeoff.py`**

```python
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class BakeoffRow:
    model: str
    eval_mean: float
    seconds_per_scene: float


def record_row(path: str, row: BakeoffRow) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(asdict(row)) + "\n")


def read_rows(path: str) -> list[BakeoffRow]:
    p = Path(path)
    if not p.exists():
        return []
    return [BakeoffRow(**json.loads(line))
            for line in p.read_text().splitlines() if line.strip()]


def pick_winner(rows: list[BakeoffRow], *, baseline_model: str,
                baseline_mean: float, margin: float,
                max_seconds_per_scene: float) -> str:
    """Highest-scoring model that clears the noise margin over the baseline AND is
    fast enough to be live-viable. Falls back to the baseline model if none qualify."""
    viable = [r for r in rows
              if r.eval_mean - baseline_mean > margin
              and r.seconds_per_scene <= max_seconds_per_scene]
    if not viable:
        return baseline_model
    return max(viable, key=lambda r: r.eval_mean).model
```

- [ ] **Step 5: Run to verify pass**

Run: `cd ~/wow-bot-brain && venv/bin/pytest tests/test_bakeoff.py -q`
Expected: PASS (4 scenarios)

- [ ] **Step 6: Commit**

```bash
cd ~/wow-bot-brain
git add sim/optimize/bakeoff.py tests/test_bakeoff.py tests/features/bakeoff.feature
git commit -m "feat(bakeoff): scored-row log + viable-winner selection"
```

---

## Task 2: `timed_regen` helper

**Files:**
- Modify: `sim/optimize/bakeoff.py`
- Test: `tests/test_bakeoff.py` (add a plain unit test; no brain needed)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bakeoff.py`:

```python
def test_timed_regen_returns_seconds_per_scene(monkeypatch):
    from sim.optimize import bakeoff

    def fake_regen(manifest_path, out_dir, brain_url="http://localhost:5001", pool="eval"):
        return ["a.json", "b.json", "c.json", "d.json"]  # pretend 4 scenes

    monkeypatch.setattr(bakeoff, "regen_eval", fake_regen)
    paths, secs = bakeoff.timed_regen("m.json", "/tmp/x", pool="eval")
    assert len(paths) == 4
    assert secs >= 0.0  # 4 scenes, near-instant fake -> ~0
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/wow-bot-brain && venv/bin/pytest tests/test_bakeoff.py::test_timed_regen_returns_seconds_per_scene -q`
Expected: FAIL — `AttributeError: module 'sim.optimize.bakeoff' has no attribute 'timed_regen'`

- [ ] **Step 3: Implement `timed_regen` in `sim/optimize/bakeoff.py`**

Add the import at the top (under the existing imports) and the function at the bottom:

```python
from sim.optimize.loop_cycle import regen_eval  # noqa: E402  (re-exported for monkeypatch)


def timed_regen(manifest_path: str, out_dir: str,
                brain_url: str = "http://localhost:5001",
                pool: str = "eval") -> tuple[list[str], float]:
    """Regenerate a pool and return (paths, seconds_per_scene). The brain must already
    be running on the candidate model with a fresh DB."""
    start = time.perf_counter()
    paths = regen_eval(manifest_path, out_dir, brain_url=brain_url, pool=pool)
    elapsed = time.perf_counter() - start
    per_scene = elapsed / len(paths) if paths else 0.0
    return paths, per_scene
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/wow-bot-brain && venv/bin/pytest tests/test_bakeoff.py -q`
Expected: PASS (5 tests/scenarios total)

- [ ] **Step 5: Commit**

```bash
cd ~/wow-bot-brain
git add sim/optimize/bakeoff.py tests/test_bakeoff.py
git commit -m "feat(bakeoff): timed_regen returns seconds-per-scene"
```

---

## Task 3: `regen_eval` gains a `pool` param

**Files:**
- Modify: `sim/optimize/loop_cycle.py:47-71`
- Test: `tests/test_loop_cycle.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_loop_cycle.py` (it uses a manifest fixture; if none, this inline one suffices):

```python
def test_regen_eval_accepts_pool_and_reads_that_key(tmp_path, monkeypatch):
    import json
    from sim.optimize import loop_cycle

    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"eval": ["ambient-a-s1"], "heldout": ["ambient-a-s2"]}))

    seen = {}

    class FakeSpec:
        scene_id = "ambient-a"
        location = "Org"; channel = "SAY"; bots = ["Bo"]; player = None; turns = 2

    def fake_all_specs():
        return [FakeSpec()]

    def fake_run_scene(**kw):
        seen["sid"] = kw["scene_id"]
        class SC:
            def save(self, p): p.write_text("{}")
        return SC()

    monkeypatch.setattr("sim.scenes.all_specs", fake_all_specs)
    monkeypatch.setattr("sim.scene_runner.run_scene", fake_run_scene)
    monkeypatch.setattr("sim.brain_client.BrainClient", lambda base_url: object())

    loop_cycle.regen_eval(str(manifest), str(tmp_path / "out"), pool="heldout")
    assert seen["sid"] == "ambient-a-s2"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/wow-bot-brain && venv/bin/pytest tests/test_loop_cycle.py::test_regen_eval_accepts_pool_and_reads_that_key -q`
Expected: FAIL — `TypeError: regen_eval() got an unexpected keyword argument 'pool'`

- [ ] **Step 3: Modify `regen_eval`**

In `sim/optimize/loop_cycle.py`, change the signature (line ~47) and the loop source. Replace:

```python
def regen_eval(manifest_path: str, out_dir: str,
               brain_url: str = "http://localhost:5001") -> list[str]:
```

with:

```python
def regen_eval(manifest_path: str, out_dir: str,
               brain_url: str = "http://localhost:5001",
               pool: str = "eval") -> list[str]:
```

and change the loop line `for sid in m["eval"]:` to:

```python
    for sid in m[pool]:
```

- [ ] **Step 4: Run to verify pass**

Run: `cd ~/wow-bot-brain && venv/bin/pytest tests/test_loop_cycle.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/wow-bot-brain
git add sim/optimize/loop_cycle.py tests/test_loop_cycle.py
git commit -m "feat(regen): regen_eval can target the heldout pool"
```

---

## Task 4: Phase A — run the model bake-off (procedure, Claude-as-judge)

No new code. Executed once per candidate; the judge is Claude against the frozen
`prompts/judge.md`. Candidates: `qwen3.5:9b`, `mistral-small:22b`, `gemma4:latest`.

- [ ] **Step 1: Confirm the config knob and baseline**

Run: `cd ~/wow-bot-brain && grep -n "OLLAMA_MODEL" config.py`
Expected: a line like `OLLAMA_MODEL = "qwen3.5:9b"`. Note its current value to restore later.

- [ ] **Step 2: For EACH candidate model, in turn**, do the following (the model swap in `config.py` is the documented, deliberately out-of-whitelist edit per the spec):

```bash
cd ~/wow-bot-brain
# 2a. set the model (replace MODEL with the candidate)
python - <<'PY'
import re, pathlib
p = pathlib.Path("config.py"); s = p.read_text()
s = re.sub(r'OLLAMA_MODEL\s*=\s*".*?"', 'OLLAMA_MODEL = "MODEL"', s)
p.write_text(s)
print("set to MODEL")
PY
# 2b. restart the experiment brain fresh (NEVER pkill — exit 144)
venv/bin/python -c "from sim.optimize.experiment_brain import start_experiment_brain as s; s()"
# 2c. timed regen of the 16 eval scenes for this model
venv/bin/python -c "from sim.optimize.bakeoff import timed_regen; import json; paths,sps=timed_regen('eval/optimizer/manifest.json','/tmp/wbb-bakeoff/MODEL_SLUG/scenes'); print('SECONDS_PER_SCENE', round(sps,2)); print(len(paths),'scenes')"
```

(MODEL_SLUG = the model name with `:`/`.` replaced by `_`, e.g. `mistral-small_22b`.)

- [ ] **Step 3: Score the 16 scenes cold (Claude-as-judge)**

Read all 16 `/tmp/wbb-bakeoff/MODEL_SLUG/scenes/*.json`. Score each against
`prompts/judge.md` (5 dims 1–5 + gate). Compute the mean via:

```bash
cd ~/wow-bot-brain && venv/bin/python -c "
from sim.judge import score_from_dimensions
scores = [score_from_dimensions(d, g) for d,g in [
  # ({'intentions':_,'turn_taking':_,'continuity':_,'initiative':_,'voice':_}, gate_passed_bool), ... x16
]]
print('eval_mean', round(sum(scores)/len(scores),3))
"
```

- [ ] **Step 4: Record the row for this model**

```bash
cd ~/wow-bot-brain && venv/bin/python -c "
from sim.optimize.bakeoff import BakeoffRow, record_row
record_row('eval/bakeoff/rows.jsonl', BakeoffRow(model='MODEL', eval_mean=EVAL_MEAN, seconds_per_scene=SECONDS_PER_SCENE))
print('recorded MODEL')
"
```

Repeat Steps 2–4 for all three models.

- [ ] **Step 5: Pick the winner and restore config to `M*`**

```bash
cd ~/wow-bot-brain && venv/bin/python -c "
from sim.optimize.bakeoff import read_rows, pick_winner
rows = read_rows('eval/bakeoff/rows.jsonl')
qwen = next(r for r in rows if r.model=='qwen3.5:9b')
w = pick_winner(rows, baseline_model='qwen3.5:9b', baseline_mean=qwen.eval_mean, margin=0.5, max_seconds_per_scene=90.0)
print('WINNER', w)
for r in rows: print(f'{r.model:22} eval={r.eval_mean:.3f} s/scene={r.seconds_per_scene:.1f}')
"
```

Then set `config.py` `OLLAMA_MODEL` to the printed WINNER (using the Step 2a snippet
with MODEL = winner). This is `M*`; its `eval_mean` is `new_baseline_mean`.

- [ ] **Step 6: Commit the bake-off result**

```bash
cd ~/wow-bot-brain
git add eval/bakeoff/rows.jsonl config.py
git commit -m "exp(bakeoff): phase A results; set actor model to M*"
```

---

## Task 5: Phase B — apply the compound template edit (whitelisted)

All edits are in `personality.py` / `prompts.py`. Apply them together; they target one
root cause (baked-in, parroted filler).

- [ ] **Step 1: Diversify + de-cliché `personality.py` goal pools**

In `pick_goal_for_level`, broaden each `random.choice` list and remove the
self-pitying monoculture. Concretely, in the **level ≤ 10** list replace
`"get some better gear, everything i have sucks"` with two fresher options and add
variety, so the list becomes:

```python
        return random.choice([
            "figure out where to go next",
            "ding the next level before i log",
            "find the trainer and learn new abilities",
            "stop dying to these stupid mobs lol",
            "make it to the next town in one piece",
            "find someone to group with for these hard quests",
            "finish this quest chain im on",
            "scrape together enough silver for skills",
        ])
```

Apply the same spirit (add 1–2 options, drop any "everything sucks / so slow / broke"
self-pity duplicates that recur across bands) to the ≤20, ≤30, ≤40, ≤50, ≤58 lists —
keep every option level-accurate and 2005-vanilla.

- [ ] **Step 2: De-catchphrase `typing_style` strings in `IRL_IDENTITIES`**

Remove the literal parrotable lines. For `weekend_warrior` (line ~102) change
`"out of loop but cheerful. 'wait what happened?' types normally. 'man i wish i could play more'. friendly."`
to:
`"out of loop but cheerful. asks what he missed. types in full words. friendly, a little wistful about limited play time."`

Scan the other 15 `typing_style` strings and convert any remaining hard-coded quoted
catchphrase that would be parroted (e.g. fixed exclamations) into a *description* of the
style rather than a quotable line. Leave genuinely characterizing tics (u/ur, lowercase)
that add variety rather than repetition.

- [ ] **Step 3: Strip parroted examples from `prompts.py` TICK activities**

In `personality.py` `pick_tick_activity`, the **SAY** prompt (line ~213) hands the model
verbatim examples that get parroted. Change:

```python
            "prompt": f"You're in {location}. Mutter something to yourself or comment on whats happening around you. Very short. Like 'ugh another murloc' or 'nice'. One line.",
```

to:

```python
            "prompt": f"You're in {location}. Mutter a short, specific reaction to whatever you're actually doing right now — name the mob, quest, or thing in front of you. Avoid generic filler. One line.",
```

- [ ] **Step 4: Add the engagement rule to `prompts.py` CHAT_PROMPT**

In `prompts.py`, inside `CHAT_PROMPT` RULES, after the line
`- Respond to what they SAID, don't monologue.` add:

```
- Actually engage their LAST message — react to its specific content. Do NOT restate your own goal or status unless they asked.
```

- [ ] **Step 5: Guard check (must stay in whitelist)**

```bash
cd ~/wow-bot-brain && venv/bin/python -c "import subprocess; from sim.optimize.guard import ALLOWED_PATHS, out_of_scope; c=subprocess.check_output(['git','diff','--name-only']).decode().split(); bad=out_of_scope(c,ALLOWED_PATHS); assert not bad, bad; print('guard ok', c)"
```

Expected: `guard ok ['personality.py', 'prompts.py']` (config.py was already committed in
Task 4, so it must NOT appear here). If `config.py` appears, it means Step 6 of Task 4
wasn't committed — commit it first, then re-run.

---

## Task 6: Phase B — evaluate the candidate through the full gate (procedure)

- [ ] **Step 1: Restart the brain fresh so the edits load**

```bash
cd ~/wow-bot-brain && venv/bin/python -c "from sim.optimize.experiment_brain import start_experiment_brain as s; s()"
```

- [ ] **Step 2: Regenerate + score the 16 eval scenes**

```bash
cd ~/wow-bot-brain && venv/bin/python -c "from sim.optimize.loop_cycle import regen_eval; regen_eval('eval/optimizer/manifest.json','/tmp/wbb-phaseB/eval', pool='eval')"
```

Read all 16 `/tmp/wbb-phaseB/eval/*.json`, score cold against `prompts/judge.md`,
compute `candidate_eval_mean` (via `score_from_dimensions` as in Task 4 Step 3). Count
`new_lore_failures` = scenes that now trip the gate but whose Phase-A `M*+base` baseline
did not.

- [ ] **Step 3: Cheap-clause check → held-out short-circuit**

Compute `eval_gain = candidate_eval_mean - new_baseline_mean`.
- If `eval_gain <= 0.5` OR `new_lore_failures > 0`: it reverts. Skip held-out; set
  `candidate_heldout_mean = new_baseline_mean + 1e-3`, `anchor_now = 2.525`.
- Else: regenerate + score the 8 held-out scenes:

```bash
cd ~/wow-bot-brain && venv/bin/python -c "from sim.optimize.loop_cycle import regen_eval; regen_eval('eval/optimizer/manifest.json','/tmp/wbb-phaseB/heldout', pool='heldout')"
```

  → `candidate_heldout_mean`. Then re-score the 8 golden anchors (frozen transcripts in
  `eval/calibration/scenes/`, ids in manifest `golden`) → `anchor_now`.

- [ ] **Step 4: Finalize (gate + commit-or-revert + record)**

```bash
cd ~/wow-bot-brain && venv/bin/python -c "
import json, subprocess
from sim.optimize.gate import GateInputs, evaluate_gate
NB=NEW_BASELINE_MEAN; CAND=CANDIDATE_EVAL_MEAN; CHO=CANDIDATE_HELDOUT_MEAN
NLF=NEW_LORE_FAILURES; ANCH=ANCHOR_NOW
dec = evaluate_gate(GateInputs(baseline_eval_mean=NB, candidate_eval_mean=CAND,
  baseline_heldout_mean=NB, candidate_heldout_mean=CHO,
  new_lore_failures=NLF, anchor_mean=ANCH, anchor_frozen_mean=2.525, margin=0.5))
rec = {'phase':'B','model':'M_STAR','new_baseline_mean':NB,'candidate_eval_mean':CAND,
  'candidate_heldout_mean':CHO,'new_lore_failures':NLF,'anchor_now':ANCH,
  'keep':dec.keep,'reasons':dec.reasons}
import pathlib; pathlib.Path('eval/bakeoff').mkdir(parents=True, exist_ok=True)
pathlib.Path('eval/bakeoff/phaseB.json').write_text(json.dumps(rec, indent=2))
print('KEEP' if dec.keep else 'REVERT', dec.reasons)
"
```

- [ ] **Step 5: Keep or revert the template edit per the decision**

- If **REVERT**: `git checkout -- personality.py prompts.py` (the templates go back to
  baseline; the model swap from Task 4 stays — that's the Phase A finding).
- If **KEEP**: leave the edits in place and commit them:
  `git add personality.py prompts.py && git commit -m "exp(phaseB): compound template edit (kept)"`

- [ ] **Step 6: Commit the Phase B record**

```bash
cd ~/wow-bot-brain
git add eval/bakeoff/phaseB.json
git commit -m "exp(phaseB): candidate scores + gate decision"
```

---

## Task 7: Report + memory update

- [ ] **Step 1: Build the attribution table** from `eval/bakeoff/rows.jsonl` +
`eval/bakeoff/phaseB.json`: three rows — `qwen+base=1.975`, `M*+base` (model effect),
`M*+newtemplates` (template effect / combined total). State which (if any) cleared 0.5,
the 22b latency verdict, and a promotion recommendation. Branch stays unmerged.

- [ ] **Step 2: Update memory** `project_wow_sim_selfimprove.md` with: the winning model,
the three attribution numbers, whether the compound edit was kept, and the latency
finding for `mistral-small:22b`. Keep the security/privacy and "promotion is the user's
call" framing. Update the one-line pointer in `MEMORY.md` only if the hook changed.

- [ ] **Step 3: Post the report to the user** as the final message (text only). Do NOT
schedule any wakeup or loop — this is a one-shot experiment, not the autonomous loop.

---

## Self-Review

**Spec coverage:** Phase A bake-off (Tasks 1–4) ✓; latency capture (Task 2 `timed_regen`,
Task 4 Step 2c) ✓; held-out regen (Task 3) ✓; winner selection w/ margin+latency (Task 1
`pick_winner`, Task 4 Step 5) ✓; Phase B compound edit personality+prompts (Task 5) ✓;
full gate eval w/ held-out short-circuit + anchor drift (Task 6) ✓; guard/scope handling
of the config.py swap (Task 4 deliberate, Task 5 Step 5 guard) ✓; attribution output +
report + no auto-merge (Task 7) ✓; BDD test for the recorder (Task 1) ✓.

**Placeholder scan:** ALL-CAPS tokens (MODEL, MODEL_SLUG, EVAL_MEAN, SECONDS_PER_SCENE,
NEW_BASELINE_MEAN, CANDIDATE_EVAL_MEAN, CANDIDATE_HELDOUT_MEAN, NEW_LORE_FAILURES,
ANCHOR_NOW, M_STAR) are **runtime values the operator substitutes per run**, not unfinished
plan content — each is defined where it's introduced. This is inherent to a Claude-as-judge
procedure (the same convention the existing optimizer runbook uses).

**Type consistency:** `BakeoffRow(model, eval_mean, seconds_per_scene)` used identically in
Tasks 1, 2, 4. `pick_winner(rows, *, baseline_model, baseline_mean, margin,
max_seconds_per_scene)` matches between Task 1 impl and Task 4 call. `regen_eval(...,
pool=)` matches between Task 3 impl, Task 2 `timed_regen`, and Task 6 calls. `evaluate_gate`/
`GateInputs` fields match `sim/optimize/gate.py` as used in `tests/test_gate.py`.
