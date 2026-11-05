from consolidate import parse_consolidation


def test_parses_valid_json_list():
    raw = '[{"subject": "Lynea", "note": "ran Deadmines together", "familiarity_delta": 2}]'
    out = parse_consolidation(raw)
    assert out == [{"subject": "Lynea", "note": "ran Deadmines together", "familiarity_delta": 2}]


def test_drops_malformed_entries_and_clamps_delta():
    raw = '''[
        {"subject": "Lynea", "note": "ok", "familiarity_delta": 999},
        {"note": "no subject"},
        {"subject": "Bob", "note": "", "familiarity_delta": 1},
        "garbage"
    ]'''
    out = parse_consolidation(raw)
    assert out == [{"subject": "Lynea", "note": "ok", "familiarity_delta": 5}]


def test_non_json_returns_empty():
    assert parse_consolidation("the model rambled") == []
    assert parse_consolidation("") == []


import pytest
from sim.transcript import Scene, Turn
from consolidate import consolidate_scene


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_consolidate_scene_persists_relationship(fresh_db):
    scene = Scene(
        scene_id="s1", location="Elwynn Forest", channel="SAY",
        participants=["Geysse", "Lynea"],
        turns=[
            Turn(idx=0, speaker="Geysse", channel="SAY", text="wanna run Deadmines?"),
            Turn(idx=1, speaker="Lynea", channel="SAY", text="yeah lets go"),
        ],
    )

    def fake_summarize(transcript_text, bot_name):
        other = "Lynea" if bot_name == "Geysse" else "Geysse"
        return f'[{{"subject": "{other}", "note": "agreed to run Deadmines", "familiarity_delta": 2}}]'

    updates = consolidate_scene(scene, summarize=fake_summarize, bots=["Geysse", "Lynea"])

    assert len(updates) == 2
    rel = fresh_db.get_relationship("Geysse", "Lynea")
    assert rel["notes"] == "agreed to run Deadmines"
    assert rel["familiarity"] >= 2
    sheet = fresh_db.get_memory_sheet("Geysse", kind="relationship")
    assert any(r["subject"] == "Lynea" for r in sheet)


from fastapi.testclient import TestClient


def test_reflect_endpoint_runs_consolidation(fresh_db, monkeypatch):
    import consolidate
    monkeypatch.setattr(
        consolidate, "local_summarize",
        lambda transcript, bot: '[{"subject": "Lynea", "note": "helped me quest", "familiarity_delta": 1}]',
    )
    import main
    client = TestClient(main.app)
    payload = {
        "scene": {
            "scene_id": "s1", "location": "Elwynn Forest", "channel": "SAY",
            "participants": ["Geysse", "Lynea"],
            "turns": [{"idx": 0, "speaker": "Geysse", "channel": "SAY", "text": "ty"}],
        },
        "bots": ["Geysse"],
    }
    r = client.post("/reflect", json=payload)
    assert r.status_code == 200
    assert r.json()["applied"] >= 1
    assert fresh_db.get_relationship("Geysse", "Lynea")["notes"] == "helped me quest"
