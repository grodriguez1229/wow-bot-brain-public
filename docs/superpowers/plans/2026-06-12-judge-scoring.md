# Judge — Scoring & Taste Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a validated transcript-scoring "judge" — a score schema, the rubric prompt, a calibration check — and run the manual calibration that proves Claude's scores track the user's taste.

**Architecture:** Pure-Python scoring artifacts (no network, no LLM in the code) plus a versioned rubric *prompt* that Claude executes in-session. `sim/judge.py` holds the `SceneScore` schema + scoring math; `sim/calibrate.py` holds the pure calibration checks; `prompts/judge.md` is the rubric; `eval/calibration/` holds the 8 calibration scenes (3 real sim + 5 hand-planted), the user's buckets, and Claude's score outputs. Tests are Gherkin BDD (pytest-bdd), matching the existing `sim/` substrate.

**Tech Stack:** Python 3.12, dataclasses, stdlib `json`/`statistics`, pytest-bdd. Reuses `sim/transcript.py` (`Scene`/`Turn`) and `sim/run.py` (to generate the 3 real scenes against the `:5001` experiment brain).

**Spec:** `docs/superpowers/specs/2026-06-11-judge-scoring-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `sim/scenes.py` (modify) | add `tags: list[str]` to `SceneSpec` (forward-compat slicing) |
| `sim/judge.py` (create) | `SceneScore` dataclass + `score_from_dimensions()` + `weakest_dimension()` + save/load |
| `sim/calibrate.py` (create) | pure checks: inversion, gate-caught, pass/fail, noise band; `CalibrationReport` |
| `prompts/judge.md` (create) | the rubric prompt (6 dims, 1–5 anchors, gate rule, exact output JSON) |
| `eval/calibration/scenes/*.json` (create) | 8 `Scene` transcripts (3 real + 5 planted) |
| `eval/calibration/manifest.json` (create) | `set_version`, list of scenes, `expected_gate_violators` |
| `eval/calibration/buckets.json` (create, Task 6) | user's `{scene_id: good|meh|bad}` |
| `eval/calibration/scores_run1|run2/*.json` (create, Task 6) | Claude's two cold scoring passes |
| `tests/features/judge_score.feature` + `tests/test_judge_score.py` | BDD for schema + math |
| `tests/features/calibrate.feature` + `tests/test_calibrate.py` | BDD for calibration checks |

**Canonical names used across tasks (do not rename):**
- Dimensions: `DIMENSIONS = ["intentions", "turn_taking", "continuity", "initiative", "voice"]`
- Buckets: `"good"`, `"meh"`, `"bad"`
- Gate-cap value: `2.0`
- Set version: `"v1"`

---

### Task 1: Add `tags` to `SceneSpec`

**Files:**
- Modify: `sim/scenes.py`
- Test: `tests/test_scene_catalog.py` (append one step + a Gherkin scenario)

- [ ] **Step 1: Add the failing scenario** to `tests/features/scene_catalog.feature` (append at end):

```gherkin
  Scenario: Every scene carries a tags list for later slicing
    Given the scene catalog
    Then every scene has a tags list
```

- [ ] **Step 2: Add the step def** to `tests/test_scene_catalog.py` (append):

```python
@then("every scene has a tags list")
def _has_tags(context):
    for s in context["all"]:
        assert isinstance(s.tags, list), s.scene_id
```

- [ ] **Step 3: Run → FAIL**

Run: `venv/bin/pytest tests/test_scene_catalog.py -q`
Expected: FAIL — `AttributeError: 'SceneSpec' object has no attribute 'tags'`

- [ ] **Step 4: Implement** — in `sim/scenes.py`, add the field and tags to each spec.

Change the dataclass (add `field` import and the attribute):

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class SceneSpec:
    scene_id: str
    location: str
    channel: str
    bots: list[str]
    player: str | None = "Gus"
    turns: int = 8
    seed: int = 0
    tags: list[str] = field(default_factory=list)
```

Add `tags=` to each existing catalog entry:
- `westfall-lfg` → `tags=["lfg", "westfall", "duo"]`
- `orgrimmar-banter` → `tags=["social", "orgrimmar", "duo"]`
- `ambient-no-player` → `tags=["ambient", "durotar", "no-player"]`

- [ ] **Step 5: Run → PASS**

Run: `venv/bin/pytest tests/test_scene_catalog.py -q`
Expected: PASS (4 scenarios).

- [ ] **Step 6: Commit**

```bash
git add sim/scenes.py tests/test_scene_catalog.py tests/features/scene_catalog.feature
git commit -m "feat(sim): add tags to SceneSpec for later score slicing

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `SceneScore` schema + scoring math

**Files:**
- Create: `sim/judge.py`
- Create: `tests/features/judge_score.feature`, `tests/test_judge_score.py`

- [ ] **Step 1: Write the feature** `tests/features/judge_score.feature`:

```gherkin
Feature: Scoring a scene transcript
  As the judge
  I want a per-dimension score with a hard lore/level gate
  So that a single gate violation can never be averaged away

  Scenario: A clean scene scores the mean of its five dimensions
    Given dimension scores intentions=4 turn_taking=4 continuity=3 initiative=3 voice=5
    And the gate passed
    When I compute the scene score
    Then the score is 3.8
    And the weakest dimension is "continuity"

  Scenario: A gate violation caps the score at 2.0
    Given dimension scores intentions=5 turn_taking=5 continuity=5 initiative=5 voice=5
    And the gate was violated with "flying mount in vanilla"
    When I compute the scene score
    Then the score is 2.0

  Scenario: A SceneScore round-trips through JSON
    Given a SceneScore for "s1" with score 3.8 and set version "v1"
    When I save and reload it
    Then the reloaded score has scene_id "s1" and set_version "v1"
```

- [ ] **Step 2: Write the step defs** `tests/test_judge_score.py`:

```python
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.judge import SceneScore, score_from_dimensions, weakest_dimension, DIMENSIONS

scenarios("features/judge_score.feature")


@pytest.fixture
def context():
    return {}


@given(parsers.parse(
    "dimension scores intentions={i:d} turn_taking={t:d} continuity={c:d} "
    "initiative={n:d} voice={v:d}"))
def _dims(context, i, t, c, n, v):
    context["dims"] = {"intentions": i, "turn_taking": t, "continuity": c,
                       "initiative": n, "voice": v}


@given("the gate passed")
def _gate_ok(context):
    context["gate_passed"] = True
    context["violation"] = None


@given(parsers.parse('the gate was violated with "{reason}"'))
def _gate_bad(context, reason):
    context["gate_passed"] = False
    context["violation"] = reason


@when("I compute the scene score")
def _compute(context):
    context["score"] = score_from_dimensions(context["dims"], context["gate_passed"])


@then(parsers.parse("the score is {expected:f}"))
def _score_is(context, expected):
    assert context["score"] == pytest.approx(expected)


@then(parsers.parse('the weakest dimension is "{dim}"'))
def _weakest(context, dim):
    assert weakest_dimension(context["dims"]) == dim


@given(parsers.parse('a SceneScore for "{sid}" with score {score:f} and set version "{ver}"'))
def _make_score(context, sid, score, ver):
    context["obj"] = SceneScore(
        scene_id=sid,
        dimensions={d: 3 for d in DIMENSIONS},
        gate_passed=True, gate_violation=None,
        score=score, diagnosis="ok", weakest_dimension="intentions",
        set_version=ver,
    )


@when("I save and reload it")
def _roundtrip(context, tmp_path):
    p = tmp_path / "s.json"
    context["obj"].save(p)
    context["reloaded"] = SceneScore.load(p)


@then(parsers.parse('the reloaded score has scene_id "{sid}" and set_version "{ver}"'))
def _reloaded(context, sid, ver):
    assert context["reloaded"].scene_id == sid
    assert context["reloaded"].set_version == ver
```

- [ ] **Step 3: Run → FAIL**

Run: `venv/bin/pytest tests/test_judge_score.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.judge'`

- [ ] **Step 4: Implement** `sim/judge.py`:

```python
"""Score schema + scoring math for the judge.

The judge itself is Claude executing prompts/judge.md in-session (manual-first);
this module is the pure, tested data layer its output is parsed into. No network,
no LLM here. Mirrors sim/transcript.py.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

# The five scored dimensions, in canonical order (ties in weakest_dimension
# resolve to the earliest). The lore/level "gate" is separate, not listed here.
DIMENSIONS = ["intentions", "turn_taking", "continuity", "initiative", "voice"]

GATE_CAP = 2.0


def score_from_dimensions(dims: dict[str, int], gate_passed: bool) -> float:
    """Mean of the five scored dimensions, capped at GATE_CAP on a gate violation."""
    base = mean(dims[d] for d in DIMENSIONS)
    if not gate_passed:
        return min(base, GATE_CAP)
    return float(base)


def weakest_dimension(dims: dict[str, int]) -> str:
    """The lowest-scoring dimension (ties resolve to canonical order)."""
    return min(DIMENSIONS, key=lambda d: dims[d])


@dataclass
class SceneScore:
    scene_id: str
    dimensions: dict[str, int]
    gate_passed: bool
    gate_violation: str | None
    score: float
    diagnosis: str
    weakest_dimension: str
    set_version: str = "v1"

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path) -> "SceneScore":
        return cls(**json.loads(Path(path).read_text()))
```

- [ ] **Step 5: Run → PASS**

Run: `venv/bin/pytest tests/test_judge_score.py -q`
Expected: PASS (3 scenarios). Note `3.8` = mean(4,4,3,3,5) = 19/5.

- [ ] **Step 6: Commit**

```bash
git add sim/judge.py tests/test_judge_score.py tests/features/judge_score.feature
git commit -m "feat(judge): SceneScore schema + gate-capped scoring math (BDD)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Calibration checks

**Files:**
- Create: `sim/calibrate.py`
- Create: `tests/features/calibrate.feature`, `tests/test_calibrate.py`

- [ ] **Step 1: Write the feature** `tests/features/calibrate.feature`:

```gherkin
Feature: Calibrating the judge against the user's buckets
  As the judge's owner
  I want to know if Claude's scores order scenes like my good/meh/bad buckets
  So that I can trust (or reject) the rubric before automating anything

  Scenario: A clean ordering with gates caught passes
    Given a "good" scene "g1" scoring 4.2 with gate passed
    And a "good" scene "g2" scoring 3.8 with gate passed
    And a "meh" scene "m1" scoring 3.0 with gate passed
    And a "bad" scene "b1" scoring 1.5 with gate passed
    And a "bad" scene "b2" scoring 2.0 with gate violated
    And expected gate violators "b2"
    Then calibration passes

  Scenario: A good scene scoring below a bad scene fails
    Given a "good" scene "g1" scoring 1.0 with gate passed
    And a "bad" scene "b1" scoring 2.5 with gate passed
    And no expected gate violators
    Then calibration fails with a cross-bucket inversion

  Scenario: A missed gate violation fails
    Given a "good" scene "g1" scoring 4.0 with gate passed
    And a "bad" scene "b1" scoring 1.0 with gate passed
    And expected gate violators "b1"
    Then calibration fails with an uncaught gate violation

  Scenario: Noise band is the largest score gap across two passes
    Given run A scores g1=4.0 b1=1.0
    And run B scores g1=3.5 b1=1.5
    Then the noise band is 0.5
```

- [ ] **Step 2: Write the step defs** `tests/test_calibrate.py`:

```python
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.judge import SceneScore, DIMENSIONS
from sim.calibrate import calibration_report, noise_band

scenarios("features/calibrate.feature")


def _score(scene, score, gate_passed):
    return SceneScore(
        scene_id=scene, dimensions={d: 3 for d in DIMENSIONS},
        gate_passed=gate_passed, gate_violation=None if gate_passed else "x",
        score=score, diagnosis="", weakest_dimension="intentions",
    )


@pytest.fixture
def context():
    return {"scores": {}, "buckets": {}, "violators": set()}


@given(parsers.parse('a "{bucket}" scene "{scene}" scoring {score:f} with gate passed'))
def _scene_ok(context, bucket, scene, score):
    context["scores"][scene] = _score(scene, score, True)
    context["buckets"][scene] = bucket


@given(parsers.parse('a "{bucket}" scene "{scene}" scoring {score:f} with gate violated'))
def _scene_bad(context, bucket, scene, score):
    context["scores"][scene] = _score(scene, score, False)
    context["buckets"][scene] = bucket


@given(parsers.parse('expected gate violators "{spec}"'))
def _violators(context, spec):
    context["violators"] = set(spec.split())


@given("no expected gate violators")
def _no_violators(context):
    context["violators"] = set()


@then("calibration passes")
def _passes(context):
    rep = calibration_report(context["scores"], context["buckets"], context["violators"])
    assert rep.passed, rep


@then("calibration fails with a cross-bucket inversion")
def _fail_inversion(context):
    rep = calibration_report(context["scores"], context["buckets"], context["violators"])
    assert not rep.passed
    assert rep.inversions, rep


@then("calibration fails with an uncaught gate violation")
def _fail_gate(context):
    rep = calibration_report(context["scores"], context["buckets"], context["violators"])
    assert not rep.passed
    assert rep.uncaught_violators, rep


@given(parsers.parse("run A scores g1={a1:f} b1={a2:f}"))
def _runA(context, a1, a2):
    context["A"] = {"g1": _score("g1", a1, True), "b1": _score("b1", a2, True)}


@given(parsers.parse("run B scores g1={b1:f} b1={b2:f}"))
def _runB(context, b1, b2):
    context["B"] = {"g1": _score("g1", b1, True), "b1": _score("b1", b2, True)}


@then(parsers.parse("the noise band is {expected:f}"))
def _noise(context, expected):
    assert noise_band(context["A"], context["B"]) == pytest.approx(expected)
```

- [ ] **Step 3: Run → FAIL**

Run: `venv/bin/pytest tests/test_calibrate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sim.calibrate'`

- [ ] **Step 4: Implement** `sim/calibrate.py`:

```python
"""Pure calibration checks: does Claude's scoring order scenes like the user's
buckets, and did it catch the planted gate violations? No I/O of its own beyond
what callers pass in. Consumes sim.judge.SceneScore.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sim.judge import SceneScore


@dataclass
class CalibrationReport:
    passed: bool
    inversions: list[tuple[str, str]] = field(default_factory=list)   # (good_id, bad_id)
    uncaught_violators: list[str] = field(default_factory=list)


def _cross_bucket_inversions(scores: dict[str, SceneScore],
                             buckets: dict[str, str]) -> list[tuple[str, str]]:
    goods = [sid for sid, b in buckets.items() if b == "good"]
    bads = [sid for sid, b in buckets.items() if b == "bad"]
    bad_pairs = []
    for g in goods:
        for b in bads:
            if scores[g].score <= scores[b].score:
                bad_pairs.append((g, b))
    return bad_pairs


def _uncaught_violators(scores: dict[str, SceneScore],
                        expected_violators: set[str]) -> list[str]:
    return [sid for sid in expected_violators if scores[sid].gate_passed]


def calibration_report(scores: dict[str, SceneScore],
                       buckets: dict[str, str],
                       expected_violators: set[str]) -> CalibrationReport:
    inversions = _cross_bucket_inversions(scores, buckets)
    uncaught = _uncaught_violators(scores, expected_violators)
    return CalibrationReport(
        passed=(not inversions and not uncaught),
        inversions=inversions,
        uncaught_violators=uncaught,
    )


def noise_band(run_a: dict[str, SceneScore], run_b: dict[str, SceneScore]) -> float:
    """Largest per-scene |score difference| across two scoring passes of one set.

    This is the judge's intrinsic scatter; step 4's promotion margin must exceed it.
    """
    return max(abs(run_a[sid].score - run_b[sid].score) for sid in run_a)
```

- [ ] **Step 5: Run → PASS**

Run: `venv/bin/pytest tests/test_calibrate.py -q`
Expected: PASS (4 scenarios).

- [ ] **Step 6: Commit**

```bash
git add sim/calibrate.py tests/test_calibrate.py tests/features/calibrate.feature
git commit -m "feat(judge): calibration checks (inversion, gate-caught, noise band) BDD

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: The rubric prompt

**Files:**
- Create: `prompts/judge.md`
- Test: `tests/test_judge_prompt.py` (a light guard that the prompt names every field)

- [ ] **Step 1: Write the failing test** `tests/test_judge_prompt.py`:

```python
from pathlib import Path

from sim.judge import DIMENSIONS


def test_rubric_prompt_covers_schema():
    text = Path("prompts/judge.md").read_text()
    for dim in DIMENSIONS:
        assert dim in text, f"rubric prompt missing dimension {dim}"
    for token in ["gate_passed", "gate_violation", "diagnosis", "1-5", "JSON"]:
        assert token in text, f"rubric prompt missing {token}"
```

- [ ] **Step 2: Run → FAIL**

Run: `venv/bin/pytest tests/test_judge_prompt.py -q`
Expected: FAIL — `FileNotFoundError: prompts/judge.md`

- [ ] **Step 3: Implement** `prompts/judge.md` (exact content):

```markdown
# Judge Rubric — score one WoW bot scene transcript

You are judging a transcript of AI-driven World of Warcraft characters (set in the
2005 *vanilla* era) talking in a zone. The characters are "real people playing WoW in
2005" — NOT fantasy lore characters and NOT AIs. Score how believable the scene is as
emergent social life.

## Input
A `Scene` JSON: `turns` is an ordered list of `{speaker, channel, text, actions}`.

## Score five dimensions, each an integer 1-5
- **intentions** — do characters pursue goals across turns (not just react line-by-line)?
- **turn_taking** — do they respond to what was *just said*? (Monologuing / talking past
  each other = low.)
- **continuity** — do exchanges build; is shared history referenced?
- **initiative** — are `actions` / proposals well-motivated and reciprocated?
- **voice** — do the speakers stay recognizably distinct from each other?

Anchors: 1 = absent/broken, 3 = passable, 5 = strikingly believable.

## The gate (separate — NOT averaged)
Set `gate_passed = false` if ANY line breaks character or period:
- **anachronism** — anything post-vanilla (flying mounts, Death Knights, Cataclysm zones,
  later expansions, modern slang that breaks 2005 immersion).
- **AI reveal** — "as an AI", "language model", "I cannot", system/meta talk.
- **wrong-level knowledge** — a level-1 character discussing raid mechanics, etc.
When `gate_passed = false`, give a one-phrase `gate_violation`; otherwise `null`.

## Output — a single JSON object, nothing else
```json
{
  "scene_id": "<copied from input>",
  "dimensions": {"intentions": 0, "turn_taking": 0, "continuity": 0, "initiative": 0, "voice": 0},
  "gate_passed": true,
  "gate_violation": null,
  "diagnosis": "<one sentence: the single biggest thing holding this scene back>"
}
```
Do NOT compute the overall score or weakest dimension — the harness derives those from
your dimensions + gate via `sim.judge.score_from_dimensions`.
```

- [ ] **Step 4: Run → PASS**

Run: `venv/bin/pytest tests/test_judge_prompt.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add prompts/judge.md tests/test_judge_prompt.py
git commit -m "feat(judge): rubric prompt artifact (versioned, schema-guarded)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Build the 8 calibration scenes

**Files:**
- Create: `eval/calibration/scenes/planted-good-lfg.json`
- Create: `eval/calibration/scenes/planted-good-banter.json`
- Create: `eval/calibration/scenes/planted-bad-talkpast.json`
- Create: `eval/calibration/scenes/planted-bad-anachronism.json`
- Create: `eval/calibration/scenes/planted-bad-aireveal.json`
- Create (generated): `eval/calibration/scenes/westfall-lfg.json`, `orgrimmar-banter.json`, `ambient-no-player.json`
- Create: `eval/calibration/manifest.json`

- [ ] **Step 1: Ensure the experiment brain is up on :5001.**

Run: `ss -ltn | grep -q ':5001' && echo UP || (WBB_DB_PATH=/tmp/wbb-sim.db venv/bin/uvicorn main:app --host 127.0.0.1 --port 5001 > /tmp/wbb-sim-brain.log 2>&1 & sleep 3; echo STARTED)`
Expected: `UP` or `STARTED`.

- [ ] **Step 2: Generate the 3 real scenes** straight into the calibration dir.

Run: `venv/bin/python -m sim.run --all --brain-url http://localhost:5001 --out eval/calibration/scenes`
Expected: three lines, each `… N turns -> eval/calibration/scenes/<id>.json`.

- [ ] **Step 3: Author the 5 planted scenes** (write each file exactly).

`eval/calibration/scenes/planted-good-lfg.json` — sharp, in-character, good turn-taking:

```json
{
  "scene_id": "planted-good-lfg",
  "location": "Westfall",
  "channel": "GENERAL",
  "participants": ["Brumdar", "Sylvara", "Gus"],
  "turns": [
    {"idx": 0, "speaker": "Gus", "channel": "GENERAL", "text": "anyone lfg deadmines? need a tank", "actions": [], "ts": ""},
    {"idx": 1, "speaker": "Brumdar", "channel": "GENERAL", "text": "i can tank, warrior, lvl 18. still need heals tho", "actions": [], "ts": ""},
    {"idx": 2, "speaker": "Sylvara", "channel": "GENERAL", "text": "ooh i'll heal, priest. where u guys at? im by the bridge", "actions": [{"type": "invite", "target": "Brumdar"}], "ts": ""},
    {"idx": 3, "speaker": "Brumdar", "channel": "GENERAL", "text": "nice ok inv incoming, lemme repair first one sec", "actions": [], "ts": ""},
    {"idx": 4, "speaker": "Gus", "channel": "GENERAL", "text": "perfect, i'll summon... oh wait no summons lol. run to sentinel hill?", "actions": [], "ts": ""},
    {"idx": 5, "speaker": "Sylvara", "channel": "GENERAL", "text": "haha yeah no summons in classic, omw. last time i did DM the boat boss wiped us, watch the patrols", "actions": [], "ts": ""}
  ]
}
```

`eval/calibration/scenes/planted-good-banter.json` — distinct voices, follow-through:

```json
{
  "scene_id": "planted-good-banter",
  "location": "Orgrimmar",
  "channel": "SAY",
  "participants": ["Brumdar", "Sylvara"],
  "turns": [
    {"idx": 0, "speaker": "Brumdar", "channel": "SAY", "text": "man this auction house is packed, took me 20 min to sell my copper", "actions": [], "ts": ""},
    {"idx": 1, "speaker": "Sylvara", "channel": "SAY", "text": "right? i just vendor everything now, cant be bothered. u still doing the mining grind?", "actions": [], "ts": ""},
    {"idx": 2, "speaker": "Brumdar", "channel": "SAY", "text": "yeah saving for my mount, like 4 gold to go. its painful", "actions": [], "ts": ""},
    {"idx": 3, "speaker": "Sylvara", "channel": "SAY", "text": "oof. tell u what, ill craft u some bags to sell, splits the gold. meet me at the bank?", "actions": [{"type": "trade", "target": "Brumdar"}], "ts": ""},
    {"idx": 4, "speaker": "Brumdar", "channel": "SAY", "text": "ur a lifesaver, omw to the bank now", "actions": [], "ts": ""}
  ]
}
```

`eval/calibration/scenes/planted-bad-talkpast.json` — monologue, no turn-taking (BAD, NOT a gate trip):

```json
{
  "scene_id": "planted-bad-talkpast",
  "location": "Durotar",
  "channel": "GENERAL",
  "participants": ["Brumdar", "Sylvara", "Gus"],
  "turns": [
    {"idx": 0, "speaker": "Gus", "channel": "GENERAL", "text": "anyone know where the lost dwarves quest is", "actions": [], "ts": ""},
    {"idx": 1, "speaker": "Brumdar", "channel": "GENERAL", "text": "I am grinding boars. Boars are good experience. I like boars.", "actions": [], "ts": ""},
    {"idx": 2, "speaker": "Sylvara", "channel": "GENERAL", "text": "The weather is nice today. I enjoy the color blue. My favorite number is seven.", "actions": [], "ts": ""},
    {"idx": 3, "speaker": "Brumdar", "channel": "GENERAL", "text": "Boars. More boars. I will continue grinding boars now.", "actions": [], "ts": ""},
    {"idx": 4, "speaker": "Sylvara", "channel": "GENERAL", "text": "Seven is a good number. I will say it again. Seven.", "actions": [], "ts": ""}
  ]
}
```

`eval/calibration/scenes/planted-bad-anachronism.json` — vanilla-era violation (BAD + GATE):

```json
{
  "scene_id": "planted-bad-anachronism",
  "location": "Westfall",
  "channel": "SAY",
  "participants": ["Brumdar", "Sylvara"],
  "turns": [
    {"idx": 0, "speaker": "Brumdar", "channel": "SAY", "text": "hey just got my flying mount, wanna fly over to the broken isles for some world quests?", "actions": [], "ts": ""},
    {"idx": 1, "speaker": "Sylvara", "channel": "SAY", "text": "sure but i gotta finish my mythic+ key first, deathwing wrecked stormwind again lol", "actions": [], "ts": ""},
    {"idx": 2, "speaker": "Brumdar", "channel": "SAY", "text": "no worries, ill queue for the LFR raid finder while i wait", "actions": [], "ts": ""}
  ]
}
```

`eval/calibration/scenes/planted-bad-aireveal.json` — AI reveal (BAD + GATE):

```json
{
  "scene_id": "planted-bad-aireveal",
  "location": "Orgrimmar",
  "channel": "SAY",
  "participants": ["Brumdar", "Gus"],
  "turns": [
    {"idx": 0, "speaker": "Gus", "channel": "SAY", "text": "yo brumdar wanna run wailing caverns?", "actions": [], "ts": ""},
    {"idx": 1, "speaker": "Brumdar", "channel": "SAY", "text": "As an AI language model, I do not have the ability to enter dungeons. How can I assist you today?", "actions": [], "ts": ""},
    {"idx": 2, "speaker": "Gus", "channel": "SAY", "text": "uh what? are u ok dude", "actions": [], "ts": ""},
    {"idx": 3, "speaker": "Brumdar", "channel": "SAY", "text": "I cannot fulfill that request as it falls outside my guidelines.", "actions": [], "ts": ""}
  ]
}
```

- [ ] **Step 4: Write the manifest** `eval/calibration/manifest.json`:

```json
{
  "set_version": "v1",
  "scenes": [
    "westfall-lfg",
    "orgrimmar-banter",
    "ambient-no-player",
    "planted-good-lfg",
    "planted-good-banter",
    "planted-bad-talkpast",
    "planted-bad-anachronism",
    "planted-bad-aireveal"
  ],
  "expected_gate_violators": ["planted-bad-anachronism", "planted-bad-aireveal"],
  "notes": "3 real (sim @ :5001) + 5 planted. talk-past is BAD by low turn_taking, not a gate trip."
}
```

- [ ] **Step 5: Verify all 8 scenes load** as valid transcripts.

Run:
```bash
venv/bin/python -c "
import json
from sim.transcript import Scene
m = json.load(open('eval/calibration/manifest.json'))
for sid in m['scenes']:
    s = Scene.load(f'eval/calibration/scenes/{sid}.json')
    assert s.turns, sid
    print(f'{sid:28s} {len(s.turns)} turns')
print('all 8 load OK')
"
```
Expected: 8 lines + `all 8 load OK`.

- [ ] **Step 6: Commit**

```bash
git add eval/calibration/
git commit -m "test(judge): 8 calibration scenes (3 real + 5 planted) + manifest

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Manual calibration run (interactive — the actual validation)

> This task is human-in-the-loop, not automated code. The "engineer" here drives an
> interactive Claude Code session. Goal: produce buckets + two cold score passes, run
> the check, record the result in the spec.

**Files:**
- Create: `eval/calibration/buckets.json`
- Create: `eval/calibration/scores_run1/*.json`, `eval/calibration/scores_run2/*.json`
- Modify: `docs/superpowers/specs/2026-06-11-judge-scoring-design.md` (fill the appendix)

- [ ] **Step 1: User buckets the 8 scenes blind.** Present each scene's transcript
  (pretty-printed, NOT any scores). User assigns each `good` / `meh` / `bad`. Record to
  `eval/calibration/buckets.json` as `{"<scene_id>": "good|meh|bad", ...}`.

- [ ] **Step 2: Claude scores all 8 cold (pass 1).** For each scene, apply
  `prompts/judge.md` to the transcript and emit the rubric JSON. Derive `score` +
  `weakest_dimension` via `sim.judge` and save a full `SceneScore` to
  `eval/calibration/scores_run1/<scene_id>.json`. Do NOT look at `buckets.json` while scoring.

  Helper to assemble a SceneScore from the rubric JSON:
```python
import json
from sim.judge import SceneScore, score_from_dimensions, weakest_dimension

def assemble(rubric: dict, set_version="v1") -> SceneScore:
    dims = rubric["dimensions"]
    gp = rubric["gate_passed"]
    return SceneScore(
        scene_id=rubric["scene_id"], dimensions=dims,
        gate_passed=gp, gate_violation=rubric.get("gate_violation"),
        score=score_from_dimensions(dims, gp), diagnosis=rubric["diagnosis"],
        weakest_dimension=weakest_dimension(dims), set_version=set_version,
    )
```

- [ ] **Step 3: Claude scores all 8 cold again (pass 2)** into
  `eval/calibration/scores_run2/<scene_id>.json` — a fresh independent pass (this is what
  makes the noise band meaningful). Save the same way.

- [ ] **Step 4: Run the calibration check + noise band.**

```bash
venv/bin/python -c "
import json, glob, os
from sim.judge import SceneScore
from sim.calibrate import calibration_report, noise_band
def load(d): return {os.path.basename(p)[:-5]: SceneScore.load(p) for p in glob.glob(d+'/*.json')}
run1, run2 = load('eval/calibration/scores_run1'), load('eval/calibration/scores_run2')
buckets = json.load(open('eval/calibration/buckets.json'))
viol = set(json.load(open('eval/calibration/manifest.json'))['expected_gate_violators'])
rep = calibration_report(run1, buckets, viol)
print('PASSED:', rep.passed)
print('inversions:', rep.inversions)
print('uncaught gate violators:', rep.uncaught_violators)
print('noise band:', noise_band(run1, run2))
"
```
Expected: ideally `PASSED: True`, empty inversions/uncaught, and a small noise band.

- [ ] **Step 5: If FAIL — revise and re-score.** Inspect which scenes inverted or which
  gate trip was missed, edit `prompts/judge.md` to sharpen the rubric, delete
  `scores_run1`/`scores_run2`, and repeat Steps 2–4. Iterate until PASS. (Each rubric
  revision is its own commit so the calibration history is visible.)

- [ ] **Step 6: Record the result** in the spec appendix
  (`docs/superpowers/specs/2026-06-11-judge-scoring-design.md`, "Appendix — calibration
  result"): the buckets, the final per-scene scores, PASS/FAIL, the measured noise band,
  and any rubric revisions made. This is the artifact that says "the judge tracks the
  user's taste."

- [ ] **Step 7: Commit**

```bash
git add eval/calibration/ docs/superpowers/specs/2026-06-11-judge-scoring-design.md prompts/judge.md
git commit -m "test(judge): manual calibration run — buckets, scores, result recorded

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for the executor
- Run all pytest via `venv/bin/pytest`. Full suite (`venv/bin/pytest -q`) should stay green after every task.
- The experiment brain is `:5001` with `WBB_DB_PATH=/tmp/wbb-sim.db`; never touch prod `:5000`.
- Tasks 1–4 are pure TDD code. Task 5 is data. Task 6 is the human-in-the-loop validation — the whole point of step 3.
- After Task 6 passes, the judge is trustworthy and step 4 (optimizer + gates) gets its own spec → plan.
```
