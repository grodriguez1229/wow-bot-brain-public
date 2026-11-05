import json
import pytest

from sim.evolution_judge import (
    EVOLUTION_DIMENSIONS, GATE_CAP, EvolutionScore,
    score_from_dimensions, weakest_dimension,
    aggregate_scores, guardrail_failures, load_run,
)


def _dims(g=4, b=4, c=4, d=4, r=4):
    return {"growth": g, "believability": b, "continuity": c, "diversity": d, "rootedness": r}


# ── scoring math ─────────────────────────────────────────────────────────────

def test_dimensions_canonical_order():
    assert EVOLUTION_DIMENSIONS == ["growth", "believability", "continuity", "diversity", "rootedness"]


def test_score_is_mean_when_gate_passes():
    assert score_from_dimensions(_dims(5, 5, 5, 5, 5), True) == 5.0
    assert score_from_dimensions(_dims(1, 2, 3, 4, 5), True) == 3.0


def test_gate_violation_caps_score():
    # mean would be 5.0 but a gate violation caps at 2.0
    assert score_from_dimensions(_dims(5, 5, 5, 5, 5), False) == GATE_CAP


def test_gate_cap_does_not_raise_a_low_score():
    assert score_from_dimensions(_dims(1, 1, 1, 1, 1), False) == 1.0


def test_weakest_dimension_ties_resolve_canonically():
    assert weakest_dimension(_dims(2, 2, 5, 5, 5)) == "growth"
    assert weakest_dimension(_dims(5, 5, 5, 1, 5)) == "diversity"


def test_evolution_score_round_trips(tmp_path):
    s = EvolutionScore(run_id="r1", dimensions=_dims(), gate_passed=True,
                       gate_violation=None, score=4.0, diagnosis="solid drift",
                       weakest_dimension="growth")
    p = tmp_path / "s.json"
    s.save(p)
    loaded = EvolutionScore.load(p)
    assert loaded.run_id == "r1" and loaded.score == 4.0 and loaded.gate_passed is True


# ── eval aggregation ─────────────────────────────────────────────────────────

def _score(score, gate=True):
    return EvolutionScore(run_id="x", dimensions=_dims(), gate_passed=gate,
                          gate_violation=None if gate else "fixation", score=score,
                          diagnosis="", weakest_dimension="growth")


def test_aggregate_scores_is_mean():
    assert aggregate_scores([_score(3.0), _score(4.0)]) == 3.5


def test_guardrail_failures_counts_gate_violations():
    assert guardrail_failures([_score(2.0, gate=False), _score(4.0), _score(1.5, gate=False)]) == 2


def test_load_run_reads_trail_and_probe(tmp_path):
    d = tmp_path / "run1"
    d.mkdir()
    (d / "trail.jsonl").write_text(
        json.dumps({"day": 1, "identity_facets": [{"subject": "a", "content": "x"}],
                    "applied_edits": []}) + "\n")
    (d / "probe.md").write_text(json.dumps(
        {"baseline": [{"q": "hi", "a": "day0"}], "final": [{"q": "hi", "a": "dayN"}]}))
    run = load_run(d)
    assert run["run_id"] == "run1"
    assert len(run["trail"]) == 1
    assert run["baseline"][0]["a"] == "day0"
    assert run["final"][0]["a"] == "dayN"
