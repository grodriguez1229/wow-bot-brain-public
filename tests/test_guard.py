import pytest
from pytest_bdd import scenarios, given, then, parsers

from sim.optimize.guard import ALLOWED_PATHS, out_of_scope

scenarios("features/guard.feature")


def _csv(s):
    return [x.strip().strip('"') for x in s.split(",")]


@pytest.fixture
def ctx():
    return {}


@given(parsers.parse("changed paths {paths}"))
def _changed(ctx, paths):
    ctx["changed"] = _csv(paths)


@then("no paths are out of scope")
def _none(ctx):
    assert out_of_scope(ctx["changed"], ALLOWED_PATHS) == []


@then(parsers.parse("the out-of-scope paths are {paths}"))
def _some(ctx, paths):
    assert out_of_scope(ctx["changed"], ALLOWED_PATHS) == _csv(paths)
