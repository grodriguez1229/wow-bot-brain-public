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
