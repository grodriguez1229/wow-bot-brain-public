from personality import pick_tick_activity


def _base(**kw):
    return pick_tick_activity(20, "Warrior", "Westfall", True, **kw)


def test_in_combat_names_target_and_uses_say():
    out = _base(activity="in_combat", target="Murloc Oracle", subzone="Murloc Camp")
    assert out["channel"] == "SAY"
    assert "Murloc Oracle" in out["prompt"]
    assert "LFG" not in out["prompt"]


def test_traveling_is_about_the_road():
    out = _base(activity="traveling", subzone="Sentinel Hill")
    assert out["channel"] == "SAY"
    assert "Sentinel Hill" in out["prompt"]


def test_dead_is_a_corpse_run_line():
    out = _base(activity="dead", subzone="The Deadmines")
    assert out["channel"] == "SAY"
    assert "died" in out["prompt"].lower() or "corpse" in out["prompt"].lower()


def test_resting_is_social_general():
    out = _base(activity="resting")
    assert out["channel"] == "GENERAL"


def test_idle_and_none_fall_through_to_menu():
    # No grounded state -> one of the legacy menu channels, never a combat target line.
    for act in (None, "idle"):
        out = _base(activity=act)
        assert out["channel"] in {"LFG", "TRADE", "GENERAL", "SAY", "GUILD"}
        assert "against" not in out["prompt"]  # no combat framing leaked in
