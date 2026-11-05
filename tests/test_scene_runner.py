"""Step definitions for tests/features/scene_runner.feature.

`scenarios(...)` turns every `Scenario:` in the feature file into a pytest test.
Each Gherkin line below is bound to a function via @given/@when/@then; the steps
share state through the `context` fixture (a plain dict). This is the BDD split:
the .feature is the spec (what), this module is the wiring (how).
"""
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from sim.scene_runner import run_scene

scenarios("features/scene_runner.feature")


class FakeBrain:
    """Deterministic stand-in for a brain HTTP endpoint.

    Echoes a numbered reply so we can assert ordering/non-emptiness without a
    network or an LLM, and so a fixed seed yields identical transcripts.
    """

    def __init__(self):
        self.chat_calls = 0
        self.tick_calls = 0

    def chat(self, bot, player, msg, ch, loc, recent_lines=None):
        self.chat_calls += 1
        return {"message": f"{bot} says hi #{self.chat_calls}", "channel": ch, "actions": []}

    def tick(self, bot, loc, np_, nb, recent_lines=None):
        self.tick_calls += 1
        return {"message": f"{bot} emotes #{self.tick_calls}", "channel": "SAY", "actions": []}


@pytest.fixture
def context():
    return {"player": "Gus"}


# --- Given -------------------------------------------------------------------

@given("a fake brain")
def _fake_brain(context):
    context["brain"] = FakeBrain()


@given(parsers.parse('bots "{a}" and "{b}"'))
def _bots(context, a, b):
    context["bots"] = [a, b]


@given(parsers.parse('a synthetic player "{name}"'))
def _player(context, name):
    context["player"] = name


@given("no synthetic player")
def _no_player(context):
    context["player"] = None


# --- When --------------------------------------------------------------------

@when(parsers.parse("I run a {turns:d}-turn scene with seed {seed:d}"))
def _run(context, turns, seed):
    context["turns"] = turns
    context["seed"] = seed
    context["scene"] = run_scene(
        brain=context["brain"], scene_id="t1", location="Westfall", channel="GENERAL",
        bots=context["bots"], player=context["player"], turns=turns, seed=seed,
    )


@when("I run the scene again with the same seed")
def _run_again(context):
    context["scene2"] = run_scene(
        brain=FakeBrain(), scene_id="t1", location="Westfall", channel="GENERAL",
        bots=context["bots"], player=context["player"],
        turns=context["turns"], seed=context["seed"],
    )


# --- Then --------------------------------------------------------------------

@then(parsers.parse("the scene has {n:d} ordered non-empty turns"))
def _ordered_nonempty(context, n):
    turns = context["scene"].turns
    assert len(turns) == n
    assert [t.idx for t in turns] == list(range(n))
    assert all(t.text.strip() for t in turns)


@then(parsers.parse('turn 0 is spoken by "{name}"'))
def _turn0_speaker(context, name):
    assert context["scene"].turns[0].speaker == name


@then("at least one bot has spoken")
def _a_bot_spoke(context):
    bots = set(context["bots"])
    assert any(t.speaker in bots for t in context["scene"].turns)


@then("both scenes have identical speakers and text")
def _identical(context):
    a = [(t.speaker, t.text) for t in context["scene"].turns]
    b = [(t.speaker, t.text) for t in context["scene2"].turns]
    assert a == b


@then("every turn is spoken by a bot")
def _only_bots(context):
    bots = set(context["bots"])
    assert all(t.speaker in bots for t in context["scene"].turns)


@then(parsers.parse('"{name}" is not a participant'))
def _not_participant(context, name):
    assert name not in context["scene"].participants


@then("the brain's chat endpoint was never called")
def _chat_never_called(context):
    # Regression: /chat requires a non-null player_name, so a player-less scene
    # must drive bots via tick only. FakeBrain.chat tolerated None, which once
    # masked a real HTTP 422 against the live brain.
    assert context["brain"].chat_calls == 0
