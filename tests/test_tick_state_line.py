from main import build_tick_state_line


def test_combat_state_line_names_target():
    line = build_tick_state_line("in_combat", "Kobold Vermin", "Goldshire")
    assert "fighting" in line.lower() and "Kobold Vermin" in line and "Goldshire" in line


def test_traveling_state_line():
    assert "traveling" in build_tick_state_line("traveling", None, "Westfall").lower()


def test_resting_state_line():
    line = build_tick_state_line("resting", None, "Stormwind")
    assert "resting" in line.lower()
    assert "Stormwind" in line


def test_dead_state_line():
    line = build_tick_state_line("dead", None, "The Deadmines")
    assert "corpse" in line.lower()
    assert "The Deadmines" in line


def test_idle_and_none_state_line_is_empty():
    for act in (None, "idle"):
        line = build_tick_state_line(act, None, "Elwynn Forest")
        assert line == ""
