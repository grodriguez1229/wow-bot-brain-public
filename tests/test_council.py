import json
from council import parse_nudges, parse_edits, merge_nudges


# ── parse_nudges ─────────────────────────────────────────────────────────────

def test_parse_nudges_valid_and_clamped():
    raw = json.dumps([
        {"subject": "Pugs", "content": "done with pugs", "weight_delta": 9},
        {"subject": "mood", "content": "lighter lately", "weight_delta": -1},
    ])
    out = parse_nudges(raw)
    assert out == [
        {"subject": "pugs", "content": "done with pugs", "weight_delta": 3},   # clamped, lowercased
        {"subject": "mood", "content": "lighter lately", "weight_delta": -1},
    ]


def test_parse_nudges_drops_bad():
    raw = json.dumps([{"subject": "x"}, {"content": "y"}, "garbage",
                      {"subject": "ok", "content": "good"}])
    assert parse_nudges(raw) == [{"subject": "ok", "content": "good", "weight_delta": 1}]


def test_parse_nudges_bad_json():
    assert parse_nudges("nope") == []
    assert parse_nudges(json.dumps({"not": "a list"})) == []


# ── parse_edits ──────────────────────────────────────────────────────────────

def test_parse_edits_valid_and_clamped():
    raw = json.dumps([{"subject": "Outlook", "content": "cynical", "weight": 99}])
    assert parse_edits(raw) == [{"subject": "outlook", "content": "cynical", "weight": 5}]


def test_parse_edits_weight_zero_is_drop_content_optional():
    raw = json.dumps([{"subject": "gone", "weight": 0}])
    assert parse_edits(raw) == [{"subject": "gone", "content": "", "weight": 0}]


def test_parse_edits_drops_contentless_positive():
    raw = json.dumps([{"subject": "x", "weight": 3}])  # positive weight needs content
    assert parse_edits(raw) == []


# ── merge_nudges (deterministic fallback) ────────────────────────────────────

def test_merge_adds_new_and_strengthens_existing():
    current = [{"subject": "pugs", "content": "wary of pugs", "weight": 2}]
    nudges = [
        {"subject": "pugs", "content": "done with pugs", "weight_delta": 2},  # 2+2 -> 4
        {"subject": "music", "content": "into metal lately", "weight_delta": 1},  # new
    ]
    edits = {e["subject"]: e for e in merge_nudges(current, nudges)}
    assert edits["pugs"]["weight"] == 4
    assert edits["pugs"]["content"] == "done with pugs"
    assert edits["music"] == {"subject": "music", "content": "into metal lately", "weight": 1}


def test_merge_negative_delta_can_drop_to_zero():
    current = [{"subject": "grind", "content": "obsessed with grinding", "weight": 1}]
    nudges = [{"subject": "grind", "content": "", "weight_delta": -3}]  # 1-3 -> 0
    edits = merge_nudges(current, nudges)
    assert edits == [{"subject": "grind", "content": "obsessed with grinding", "weight": 0}]
