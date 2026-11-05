import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from knowledge_audit import audit, tick_lines  # noqa: E402

LOG = [
    '[tick] Trean -> GENERAL [fragment]: "anyone for MC"\n',
    "[tick] Trean -> GENERAL: (silent)\n",
    "R2 DEPLOYED\n",
    '[tick] Trean -> TRADE [reaction] (re Bob): "lol"\n',
    '[tick] Olak -> GENERAL [fragment]: "doing dailies"\n',
    '[tick] Nobody -> GENERAL [fragment]: "MC"\n',
]


def test_tick_lines_parses_tags_and_skips_silence():
    assert tick_lines(LOG) == [("Trean", "anyone for MC"), ("Trean", "lol"),
                               ("Olak", "doing dailies"), ("Nobody", "MC")]


def test_tick_lines_after_marker():
    assert tick_lines(LOG, after="R2 DEPLOYED")[0] == ("Trean", "lol")


def test_audit_uses_levels_and_skips_unknown_bots():
    checked, bad = audit(tick_lines(LOG), {"Trean": 20, "Olak": 60})
    assert checked == 3
    assert [(b, v) for b, _l, _m, v in bad] == [("Trean", ["mc"]), ("Olak", ["dailies"])]
