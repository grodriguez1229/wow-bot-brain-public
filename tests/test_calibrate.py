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
