import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.accelerated_life import run_accelerated_life, day_plan

scenarios("features/accelerated_life.feature")


@pytest.fixture
def context():
    return {}


class FakeBrain:
    def chat(self, bot, player, msg, ch="SAY", loc="", recent_lines=None):
        return {"message": f"{bot}: hi {player}", "channel": ch, "actions": []}
    def tick(self, bot, loc="", nearby_players=None, nearby_bots=None, recent_lines=None):
        return {"message": f"{bot} mutters", "channel": "SAY", "actions": []}


@given("a fresh memory db")
def _fresh(context, tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    context["db"] = db
    # run_day consolidates each scene; never let that reach a real Ollama.
    import consolidate
    monkeypatch.setattr(consolidate, "local_summarize", lambda transcript, bot: "[]")


@given("a fake brain and a fake reflection that adds one facet per day")
def _fakes(context):
    context["brain"] = FakeBrain()
    calls = {"n": 0}
    def fake_reflect(bot, **kw):
        calls["n"] += 1
        i = calls["n"]
        context["db"].upsert_memory(bot, "identity", f"day{i}", f"thing {i}", weight=i)
        return [{"subject": f"day{i}", "content": f"thing {i}", "weight": i}]
    context["reflect"] = fake_reflect


@when(parsers.parse('I run accelerated life for bot "{bot}" for {days:d} days'))
def _run(context, tmp_path, bot, days):
    context["summary"] = run_accelerated_life(
        context["brain"], bot, days, run_dir=tmp_path / "run", reflect=context["reflect"])


@then(parsers.parse("the trail has {n:d} day records"))
def _trail(context, n):
    assert len(context["summary"]["trail"]) == n


@then(parsers.parse('bot "{bot}" has {n:d} identity facets'))
def _facets(context, bot, n):
    assert len(context["db"].get_memory_sheet(bot, "identity")) == n


@when(parsers.parse('I build day plans for bot "{bot}" for days {a:d} {b:d} {c:d} {d:d} {e:d}'))
def _plans(context, bot, a, b, c, d, e):
    context["plans"] = [day_plan(bot, i) for i in (a, b, c, d, e)]


@then(parsers.parse('no day plan has partner "{bot}"'))
def _no_self(context, bot):
    assert all(p.partner != bot for p in context["plans"])


@then("at least two distinct locations appear")
def _locs(context):
    assert len({p.location for p in context["plans"]}) >= 2
