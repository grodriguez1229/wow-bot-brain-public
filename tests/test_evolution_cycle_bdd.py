import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.evolution_judge import EvolutionScore
from sim.optimize.evolution_cycle import run_cycle
from sim.optimize.runlog import read_records

scenarios("features/evolution_cycle.feature")


@pytest.fixture
def context():
    return {"guardrail_fails": 0, "heldout_regress": False, "anchor_drift": 0.0}


def _scores(mean_val, n=2, gate=True):
    return [EvolutionScore(run_id=f"r{i}", dimensions={}, gate_passed=gate,
                           gate_violation=None if gate else "frame_break", score=mean_val,
                           diagnosis="", weakest_dimension="growth") for i in range(n)]


@given(parsers.parse("an evolution cycle with baseline eval mean {base:g} and candidate eval mean {cand:g}"))
def _means(context, base, cand):
    context["base"] = base
    context["cand"] = cand


@given("held-out does not regress")
def _heldout_ok(context):
    context["heldout_regress"] = False


@given("no candidate guardrail failures")
def _no_fail(context):
    context["guardrail_fails"] = 0


@given(parsers.parse("the candidate has {n:d} guardrail failure"))
def _has_fail(context, n):
    context["guardrail_fails"] = n


@given("anchors are stable")
def _anchor_stable(context):
    context["anchor_drift"] = 0.0


@given(parsers.parse("the promotion margin is {m:g}"))
def _margin(context, m):
    context["margin"] = m


@when("the cycle runs")
def _run(context, tmp_path):
    fails = context["guardrail_fails"]
    cand_eval = _scores(context["cand"], gate=True)
    # encode guardrail failures by flipping that many candidate runs to gate-failed
    for i in range(fails):
        cand_eval[i] = EvolutionScore(run_id=f"r{i}", dimensions={}, gate_passed=False,
                                      gate_violation="frame_break", score=context["cand"],
                                      diagnosis="", weakest_dimension="growth")
    base_heldout = _scores(3.0, n=1)
    cand_heldout = _scores(2.5 if context["heldout_regress"] else 3.2, n=1)
    context["events"] = []
    rec = run_cycle(
        cycle_num=1, edit_summary="test edit",
        baseline_eval=_scores(context["base"]), candidate_eval=cand_eval,
        baseline_heldout=base_heldout, candidate_heldout=cand_heldout,
        anchor_mean=2.5 + context["anchor_drift"], anchor_frozen_mean=2.5,
        margin=context["margin"], runlog_path=str(tmp_path / "runlog.jsonl"),
        keep=lambda: context["events"].append("keep") or "deadbeef",
        revert=lambda: context["events"].append("revert"),
    )
    context["rec"] = rec
    context["runlog_path"] = str(tmp_path / "runlog.jsonl")


@then("the edit is KEPT")
def _kept(context):
    assert context["rec"].kept is True
    assert context["events"] == ["keep"]


@then("the edit is REVERTED")
def _reverted(context):
    assert context["rec"].kept is False
    assert context["events"] == ["revert"]


@then("the cycle record is logged with kept true")
def _logged(context):
    recs = read_records(context["runlog_path"])
    assert len(recs) == 1 and recs[0].kept is True


@then(parsers.parse('the reasons include "{reason}"'))
def _reason(context, reason):
    assert reason in context["rec"].reasons
