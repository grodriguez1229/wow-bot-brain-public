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
