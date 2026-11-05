import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.scene_runner import run_scene
from sim.transcript import Scene, Turn

scenarios("features/memory.feature")


class RecordingBrain:
    def __init__(self):
        self.recent_seen = []
    def chat(self, bot, player, msg, ch, loc, recent_lines=None):
        self.recent_seen.append(recent_lines or [])
        return {"message": f"{bot} replies", "channel": ch, "actions": []}
    def tick(self, bot, loc, np_, nb, recent_lines=None):
        self.recent_seen.append(recent_lines or [])
        return {"message": f"{bot} mutters", "channel": "SAY", "actions": []}


@pytest.fixture
def context():
    return {}


@given("a recording fake brain")
def _rec_brain(context):
    context["brain"] = RecordingBrain()


@given(parsers.parse('bots "{a}" and "{b}"'))
def _bots(context, a, b):
    context["bots"] = [a, b]


@when(parsers.parse("I run a {turns:d}-turn no-player scene with seed {seed:d}"))
def _run(context, turns, seed):
    context["scene"] = run_scene(
        brain=context["brain"], scene_id="m1", location="Elwynn Forest",
        channel="SAY", bots=context["bots"], player=None, turns=turns, seed=seed,
    )


@then("at least one brain call received non-empty recent_lines")
def _saw_recent(context):
    assert any(len(r) > 0 for r in context["brain"].recent_seen)


@given("a fresh memory db")
def _fresh(context, tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    context["db"] = db


@given("a two-bot transcript where they agree to group up")
def _transcript(context):
    context["scene"] = Scene(
        scene_id="m2", location="Elwynn Forest", channel="SAY",
        participants=["Geysse", "Lynea"],
        turns=[
            Turn(idx=0, speaker="Geysse", channel="SAY", text="group up?"),
            Turn(idx=1, speaker="Lynea", channel="SAY", text="sure"),
        ],
    )


@when("I consolidate the scene with a canned summarizer")
def _consolidate(context):
    from consolidate import consolidate_scene
    canned = lambda transcript, bot: '[{"subject": "Lynea", "note": "grouped up in Elwynn", "familiarity_delta": 2}]'
    consolidate_scene(context["scene"], summarize=canned, bots=["Geysse"])


@then(parsers.parse('"{bot}" remembers a note about "{subject}"'))
def _remembers(context, bot, subject):
    rel = context["db"].get_relationship(bot, subject)
    assert rel["notes"]
    sheet = context["db"].get_memory_sheet(bot, kind="relationship")
    assert any(r["subject"] == subject for r in sheet)
