"""Step definitions for tests/features/scene_catalog.feature."""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim import scenes

scenarios("features/scene_catalog.feature")


@pytest.fixture
def context():
    return {}


@given("the scene catalog")
def _catalog(context):
    context["all"] = scenes.all_specs()


@when(parsers.parse('I look up the scene "{scene_id}"'))
def _lookup(context, scene_id):
    try:
        context["spec"] = scenes.get(scene_id)
    except Exception as e:  # noqa: BLE001 - the spec asserts the error type below
        context["error"] = e


@then(parsers.parse('I get a spec located in "{location}"'))
def _located(context, location):
    assert context["spec"].location == location


@then(parsers.parse("the spec has at least {n:d} bots"))
def _min_bots(context, n):
    assert len(context["spec"].bots) >= n


@then("every scene has a unique id")
def _unique(context):
    ids = [s.scene_id for s in context["all"]]
    assert len(ids) == len(set(ids))
    assert ids, "catalog must not be empty"


@then("every scene has at least one bot and a positive turn count")
def _runnable(context):
    for s in context["all"]:
        assert len(s.bots) >= 1, s.scene_id
        assert s.turns > 0, s.scene_id


@then("a lookup error is raised")
def _error(context):
    assert isinstance(context.get("error"), KeyError)


@then("every scene has a tags list")
def _has_tags(context):
    for s in context["all"]:
        assert isinstance(s.tags, list), s.scene_id
