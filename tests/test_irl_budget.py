import pytest

import irl_budget


def setup_function(_):
    irl_budget.reset_state()


@pytest.mark.parametrize("line", [
    "closing shift at Best Buy, my feet are killing me",
    "my gf says hi",
    "night shift again ugh",
    "paper due tomorrow and im in Westfall lol",
    "cat knocked over my beer",
    "sorry brb kid woke up",
    "gtg wife aggro",
    "mom made pizza",
    "just got off work",
    "my boss is the worst",
    "so tired, need to sleep soon",
    "irl stuff, back in 5",
])
def test_irl_positives(line):
    assert irl_budget.is_irl_line(line)


@pytest.mark.parametrize("line", [
    "anyone want to run Deadmines?",
    "WTS four Linen Bags 5s each",
    "this murloc camp is brutal",
    "what class should i roll for pvp",
    "does this rotation even work",
    "LF healer for SM Cathedral",
    "just hit 30 finally",
    "Scholomance runs tonight?",
])
def test_irl_negatives(line):
    assert not irl_budget.is_irl_line(line)


def test_extra_terms_match_as_words():
    assert irl_budget.is_irl_line("Biscuit is sitting on my keyboard again", ["biscuit"])
    assert not irl_budget.is_irl_line("biscuits from the innkeeper", ["biscuit"])


def test_cold_start_allows():
    assert irl_budget.share() == 0.0
    assert irl_budget.irl_allowed()


def test_budget_denies_above_target_and_recovers(monkeypatch):
    monkeypatch.setattr(irl_budget, "IRL_TARGET", 0.15)
    for _ in range(3):
        irl_budget.note_ambient_line("my gf says hi")
    for _ in range(17):
        irl_budget.note_ambient_line("anyone for Deadmines")
    assert irl_budget.share() == pytest.approx(0.15)
    assert not irl_budget.irl_allowed()           # at target -> denied
    irl_budget.note_ambient_line("anyone for Deadmines")
    assert irl_budget.irl_allowed()               # 3/21 < 0.15


def test_target_zero_never_allows(monkeypatch):
    monkeypatch.setattr(irl_budget, "IRL_TARGET", 0.0)
    assert not irl_budget.irl_allowed()


def test_window_is_bounded():
    for _ in range(irl_budget.IRL_WINDOW + 50):
        irl_budget.note_ambient_line("my gf says hi")
    assert len(irl_budget._window) == irl_budget.IRL_WINDOW


def test_note_returns_classification():
    assert irl_budget.note_ambient_line("my boss called") is True
    assert irl_budget.note_ambient_line("murlocs everywhere") is False


def test_config_defaults():
    import config
    assert config.IRL_TARGET == 0.15 and config.IRL_WINDOW == 200
    assert config.SIGNATURE_RATE == 0.1
    assert config.TICK_MAX_CHARS == 140 and config.HEARD_MAX_CHARS == 200


@pytest.mark.parametrize("line", [
    "where is Mankrik's wife",
    "my cat pulled aggro again",
    "these scrubs cant pvp",
    "does this addon work today",
    "Sergeant Bly is camping the gate",
    "regroup at base camp before the next push",
])
def test_irl_fix_negatives(line):
    assert not irl_budget.is_irl_line(line)


@pytest.mark.parametrize("line", [
    "barely got five hours sleep at base tonight",
    "u want me to run ubrs? im tired but i need gear lol",
    "gtg wife aggro",
    "my mom made cookies",
    "i can’t sleep",
])
def test_irl_fix_positives(line):
    assert irl_budget.is_irl_line(line)


def test_tired_of_is_not_irl():
    assert not irl_budget.is_irl_line("so tired of this grind")
    assert not irl_budget.is_irl_line("im tired of wolves")
    assert irl_budget.is_irl_line("im tired but i need gear")
