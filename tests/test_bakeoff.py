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


def test_timed_regen_returns_seconds_per_scene(monkeypatch):
    from sim.optimize import bakeoff

    def fake_regen(manifest_path, out_dir, brain_url="http://localhost:5001", pool="eval"):
        return ["a.json", "b.json", "c.json", "d.json"]  # pretend 4 scenes

    monkeypatch.setattr(bakeoff, "regen_eval", fake_regen)
    paths, secs = bakeoff.timed_regen("m.json", "/tmp/x", pool="eval")
    assert len(paths) == 4
    assert secs >= 0.0  # 4 scenes, near-instant fake -> ~0
