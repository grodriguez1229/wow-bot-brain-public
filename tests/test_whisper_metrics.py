import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "eval"))

import whisper_metrics  # noqa: E402

LINES = [
    "boot noise",
    '[chat] Gus -> Thaldrun (L34 Dwarf Warrior, office_worker, mood=ok, rel=stranger)',
    '  IN:  "hey"',
    '  OUT: "sup"',
    '[chat:whisper] Gus -> Mirela (L20 Human Priest, college_kid, mood=ok, rel=friend, shape=short)',
    '  IN:  "u around"',
    '  OUT: "yeah just doing wc"',
    '  ACT: []',
    '[chat:heard] Gus -> Brannic (L12 Gnome Mage, x, mood=ok, rel=stranger, shape=short)',
    '  IN:  "anyone"',
    '  OUT: "im Brannic the level 12 mage"',
    '[whisper] Thaldrun -> Gus [callback] (+7s): "yo that wipe was brutal"',
    '[whisper] Mirela -> Gus [invite] (+12s): "wanna run wc"',
    '=== R9 DEPLOYED 2026-11-03 ===',
    '[chat:whisper] Gus -> Thaldrun (L34 Dwarf Warrior, a, mood=ok, rel=friend, shape=short)',
    '  IN:  "hi"',
    '  OUT: "hey you"',
    '[whisper] Thaldrun -> Gus [checkin] (+9s): "u alive"',
]


def test_parses_old_and_new_chat_headers():
    rows = [r for r in whisper_metrics.parse_chat_lines(LINES) if r["source"] == "chat"]
    assert [(r["lane"], r["bot"], r["level"], r["msg"]) for r in rows[:3]] == [
        ("chat", "Thaldrun", 34, "sup"),
        ("whisper", "Mirela", 20, "yeah just doing wc"),
        ("heard", "Brannic", 12, "im Brannic the level 12 mage")]


def test_parses_whisper_lines_with_kind():
    rows = [r for r in whisper_metrics.parse_chat_lines(LINES) if r["source"] == "whisper"]
    assert [(r["bot"], r["kind"], r["msg"]) for r in rows[:2]] == [
        ("Thaldrun", "callback", "yo that wipe was brutal"), ("Mirela", "invite", "wanna run wc")]
    assert rows[0]["lane"] == "login" and rows[0]["level"] is None


def test_after_marker_filters():
    rows = whisper_metrics.parse_chat_lines(LINES, after="R9 DEPLOYED")
    assert [r["msg"] for r in rows] == ["hey you", "u alive"]


def test_summary_rates():
    rows = [
        {"lane": "whisper", "source": "chat", "bot": "Brannic", "level": 12, "msg": "im Brannic the mage", "kind": None},
        {"lane": "whisper", "source": "chat", "bot": "Mirela", "level": 20, "msg": "lol ya", "kind": None},
        {"lane": "whisper", "source": "chat", "bot": "Mirela", "level": 20, "msg": "same here", "kind": None},
        {"lane": "whisper", "source": "chat", "bot": "Mirela", "level": 20, "msg": "ok", "kind": None},
    ]
    personas = {"Brannic": {"race": "Gnome", "class_name": "Mage", "level": 12}}
    s = whisper_metrics.summarize(rows, personas)["whisper"]
    assert s["count"] == 4
    assert s["median_len"] == statistics_median([19, 6, 9, 2])
    assert s["short_share"] == 1.0
    assert s["self_intro_rate"] == 0.25
    assert s["violation_rate"] == 0.0


def test_summary_kind_mix_and_violations():
    rows = [
        {"lane": "login", "source": "whisper", "bot": "X", "level": None, "msg": "MC tonight?", "kind": "invite"},
        {"lane": "login", "source": "whisper", "bot": "X", "level": None, "msg": "hey", "kind": "checkin"},
    ]
    personas = {"X": {"race": "Orc", "class_name": "Rogue", "level": 15}}
    s = whisper_metrics.summarize(rows, personas)["login"]
    assert s["kinds"] == {"invite": 1, "checkin": 1}
    assert s["violation_rate"] == 0.5


def test_load_personas_read_only(tmp_path):
    p = tmp_path / "m.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE bot_personalities (bot_name TEXT, race TEXT, class_name TEXT, level INTEGER)")
    c.execute("INSERT INTO bot_personalities VALUES ('A','Orc','Rogue',15)")
    c.commit()
    c.close()
    assert whisper_metrics.load_personas(str(p)) == {"A": {"race": "Orc", "class_name": "Rogue", "level": 15}}
    assert whisper_metrics.load_personas(str(tmp_path / "missing.db")) == {}


def statistics_median(v):
    import statistics
    return statistics.median(v)
