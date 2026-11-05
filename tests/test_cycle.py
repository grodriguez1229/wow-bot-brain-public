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
    assert any(k == "commit" for k, _ in ctx["git_calls"])


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
