import random

import typing_transform as tt

NAMES = [f"Bot{i}" for i in range(60)]
LINE = "Thank you, are you going to Ironforge tonight? I don't know the way."


def test_style_deterministic_and_varied():
    assert tt.style_for("Gungran") == tt.style_for("Gungran")
    caps = {tt.style_for(n)["caps"] for n in NAMES}
    assert caps == {"lower", "sentence", "asis"}
    assert len({tt.style_for(n)["abbrevs"] for n in NAMES}) > 30


def test_transform_changes_some_lines_and_never_empties():
    rng = random.Random(0)
    outs = [tt.transform(LINE, n, rng=rng) for n in NAMES]
    assert all(o.strip() for o in outs)
    assert sum(o != LINE for o in outs) > 40
    assert any(" u " in f" {o} " for o in outs)


def test_item_links_names_numbers_protected():
    rng = random.Random(1)
    line = "Thanks Esterini, WTS [Heavy Linen Bandage] x20 for 5s, really cheap you know"
    for n in NAMES:
        for _ in range(5):
            o = tt.transform(line, n, protect=("Esterini",), rng=rng)
            assert "[Heavy Linen Bandage]" in o
            assert "Esterini" in o
            assert "x20" in o and "5s" in o


def test_light_mode_no_abbrev_typos_or_laughs():
    rng = random.Random(2)
    line = "you are really going to love this place, thank you for asking"
    for n in NAMES:
        o = tt.transform(line, n, light=True, rng=rng)
        assert o.lower().rstrip(".!?") == line.lower().rstrip(".!?")


def test_length_bound_and_max_len():
    rng = random.Random(3)
    for n in NAMES:
        o = tt.transform(LINE, n, rng=rng)
        assert len(o) <= len(LINE) + 6
        short = tt.transform("x" * 20, n, rng=rng, max_len=20)
        assert len(short) <= 21     # typo "double" may add one char


def test_empty_passthrough():
    assert tt.transform("", "A") == ""
    assert tt.transform("   ", "A") == "   "


def test_lower_style_lowercases_but_keeps_links():
    name = next(n for n in NAMES if tt.style_for(n)["caps"] == "lower")
    o = tt.transform("Selling [Linen Cloth] In Orgrimmar", name, rng=random.Random(4))
    assert "[Linen Cloth]" in o and "orgrimmar" in o
