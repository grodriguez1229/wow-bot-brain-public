import json
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.judge import SceneScore, DIMENSIONS
from sim.optimize.pools import load_pools, pool_mean, PoolsError

scenarios("features/pools.feature")


def _score(sid, val):
    return SceneScore(scene_id=sid, dimensions={d: int(val) for d in DIMENSIONS},
                      gate_passed=True, gate_violation=None, score=val,
                      diagnosis="", weakest_dimension="intentions")


def _csv(s):  # 'a','b' -> ["a","b"]
    return [x.strip().strip('"') for x in s.split(",")]


@pytest.fixture
def ctx(tmp_path):
    return {"tmp": tmp_path}


@given(parsers.parse('a manifest with golden {g} eval {e} heldout {h}'))
def _manifest(ctx, g, e, h):
    m = {"set_version": "v1", "gate_margin": 0.6,
         "golden_dir": "eval/calibration/scenes", "golden": _csv(g),
         "scenes_dir": "eval/optimizer/scenes", "eval": _csv(e), "heldout": _csv(h)}
    p = ctx["tmp"] / "manifest.json"
    p.write_text(json.dumps(m))
    ctx["manifest"] = p


@when("I load the pools")
def _load(ctx):
    try:
        ctx["pools"] = load_pools(ctx["manifest"])
    except PoolsError as e:
        ctx["error"] = e


@then(parsers.parse("golden has {a:d}, eval has {b:d}, heldout has {c:d}"))
def _sizes(ctx, a, b, c):
    p = ctx["pools"]
    assert (len(p.golden), len(p.eval), len(p.heldout)) == (a, b, c)


@then("the pools are disjoint")
def _disjoint(ctx):
    p = ctx["pools"]
    assert set(p.golden).isdisjoint(p.eval)
    assert set(p.eval).isdisjoint(p.heldout)
    assert set(p.golden).isdisjoint(p.heldout)


@then("loading raises a disjointness error")
def _raises(ctx):
    assert isinstance(ctx.get("error"), PoolsError)


@given(parsers.parse("scores e1={a:f} e2={b:f} e3={c:f}"))
def _scores(ctx, a, b, c):
    ctx["scores"] = {"e1": _score("e1", a), "e2": _score("e2", b), "e3": _score("e3", c)}


@then(parsers.parse('the mean of eval {ids} is {expected:f}'))
def _mean(ctx, ids, expected):
    assert pool_mean(ctx["scores"], _csv(ids)) == pytest.approx(expected)
