from sim.synthetic_player import SyntheticPlayer


def test_opener_and_followups_are_short_strings():
    p = SyntheticPlayer(name="Gus", seed=1)
    o = p.opener("Westfall")
    assert isinstance(o, str) and 0 < len(o) <= 120
    f = p.followup(["hey", "sup"])
    assert isinstance(f, str) and len(f) > 0


def test_seed_is_deterministic():
    a = SyntheticPlayer(seed=42).opener("Durotar")
    b = SyntheticPlayer(seed=42).opener("Durotar")
    assert a == b
