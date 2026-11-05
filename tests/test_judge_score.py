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
