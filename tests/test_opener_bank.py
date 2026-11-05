"""R9 Task 9: authored login-whisper opener examples and fallbacks."""
import statistics

import knowledge
from postfilter import is_self_intro
from vanilla_guard import find_banned
import re

from voice_examples import OPENER_EXAMPLES, OPENER_FALLBACKS, OPENER_LONG_ABSENCE_EXAMPLES

PERSONAS = [dict(bot_name="Trean", race="Night Elf", class_name="Hunter", level=12),
            dict(bot_name="Grokk", race="Orc", class_name="Warrior", level=40),
            dict(bot_name="Vexira", race="Undead", class_name="Rogue", level=60)]


def test_opener_bank():
    assert set(OPENER_EXAMPLES) == {"callback", "invite", "checkin"}
    assert set(OPENER_FALLBACKS) == {"callback", "invite", "checkin"}
    for kind, lines in OPENER_EXAMPLES.items():
        assert len(lines) >= 15, kind
        assert len(set(lines)) == len(lines), kind
        assert statistics.median(len(x) for x in lines) <= 30, kind
    for kind in ("callback", "invite", "checkin"):
        assert OPENER_FALLBACKS[kind], kind
    assert {"yo", "hey u on"} <= set(OPENER_FALLBACKS["callback"])
    assert {"want an inv?", "u wanna group?"} <= set(OPENER_FALLBACKS["invite"])
    assert {"yo", "hey", "o/", "sup", "where u been"} <= set(OPENER_FALLBACKS["checkin"])
    every = [x for v in OPENER_EXAMPLES.values() for x in v] + \
            [x for v in OPENER_FALLBACKS.values() for x in v] + list(OPENER_LONG_ABSENCE_EXAMPLES)
    for line in every:
        assert find_banned(line) == [], line
        assert knowledge.mentioned_places(line) == set(), line
        assert knowledge.find_violations(line, 1) == [], line
        assert len(line) <= 60, line
        for p in PERSONAS:
            assert not is_self_intro(line, **p), (line, p["bot_name"])


# A callback example must not claim an outcome or a time: the model copies the register,
# and any specific (a wipe, a boss, loot, when) has to come from the stored moments.
_CLAIM = re.compile(r"\b(?:wipe\w*|died|die|dying|death|dead|drop\w*|loot\w*|last night|yesterday|"
                    r"last time|pull\w*|pat|pats|boss\w*|repair\w*|saved|killed|kill|ninja\w*|"
                    r"aggro|tank\w*|heal\w*)\b", re.IGNORECASE)
_ABSENCE = re.compile(r"\b(?:stranger|about time|been a while|long time|where u been|missed)\b")


def test_callback_examples_claim_no_specifics():
    for line in OPENER_EXAMPLES["callback"] + OPENER_FALLBACKS["callback"]:
        assert not _CLAIM.search(line), line


def test_absence_lines_only_in_long_absence_pool():
    for kind, lines in OPENER_EXAMPLES.items():
        for line in lines:
            assert not _ABSENCE.search(line), (kind, line)
    assert OPENER_LONG_ABSENCE_EXAMPLES
    for line in OPENER_LONG_ABSENCE_EXAMPLES:
        assert line not in OPENER_EXAMPLES["checkin"]
