import json
import pytest

from self_memory import parse_self_notes, consolidate_self


# ── parse_self_notes (pure) ──────────────────────────────────────────────────

def test_parse_valid():
    raw = json.dumps([{"subject": "mood", "note": "burned out on grinding"},
                      {"subject": "interests", "note": "really into fishing lately"}])
    out = parse_self_notes(raw)
    assert out == [{"subject": "mood", "note": "burned out on grinding"},
                   {"subject": "interests", "note": "really into fishing lately"}]


def test_parse_drops_bad_entries():
    raw = json.dumps([{"subject": "mood"},            # missing note
                      {"note": "no subject"},          # missing subject
                      "garbage",                        # not a dict
                      {"subject": "ok", "note": "good"}])
    assert parse_self_notes(raw) == [{"subject": "ok", "note": "good"}]


def test_parse_caps_at_four():
    raw = json.dumps([{"subject": f"s{i}", "note": f"n{i}"} for i in range(8)])
    assert len(parse_self_notes(raw)) == 4


def test_parse_bad_json():
    assert parse_self_notes("not json") == []
    assert parse_self_notes(json.dumps({"not": "a list"})) == []


# ── consolidate_self (write-path, fake summarize) ────────────────────────────

@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    db.save_message("Bot", "Gus", "user", "rough day?")
    db.save_message("Bot", "Gus", "assistant", "yeah work sucked")
    return db


def test_consolidate_persists_self_notes(fresh_db):
    notes = [{"subject": "mood", "note": "wiped out from work"},
             {"subject": "interests", "note": "starting to like helping lowbies"}]
    applied = consolidate_self("Bot", summarize=lambda *a, **k: json.dumps(notes))
    assert len(applied) == 2
    rows = fresh_db.get_memory_sheet("Bot", "self")
    assert {r["subject"] for r in rows} == {"mood", "interests"}
    assert any("lowbies" in r["content"] for r in rows)


def test_consolidate_evolves_same_subject(fresh_db):
    consolidate_self("Bot", summarize=lambda *a, **k: json.dumps(
        [{"subject": "mood", "note": "tired"}]))
    consolidate_self("Bot", summarize=lambda *a, **k: json.dumps(
        [{"subject": "mood", "note": "actually feeling good today"}]))
    rows = fresh_db.get_memory_sheet("Bot", "self")
    moods = [r for r in rows if r["subject"] == "mood"]
    assert len(moods) == 1  # overwritten, not duplicated
    assert moods[0]["content"] == "actually feeling good today"


def test_consolidate_prunes_to_four(fresh_db):
    big = [{"subject": f"s{i}", "note": f"n{i}"} for i in range(6)]
    # parse caps at 4, so even a 6-item summary lands 4
    consolidate_self("Bot", summarize=lambda *a, **k: json.dumps(big))
    assert len(fresh_db.get_memory_sheet("Bot", "self")) == 4
