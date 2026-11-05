"""parse_response: action/emote tag parsing + scrubbing, channel inference."""
from llm import parse_response


def test_plain_message_passes_through():
    r = parse_response("hey whats up", "SAY")
    assert r["message"] == "hey whats up"
    assert r["channel"] == "SAY"
    assert r["actions"] == []


def test_action_tag_parsed_and_removed():
    r = parse_response("sure lets go [ACTION:invite Gus]", "SAY")
    assert r["message"] == "sure lets go"
    assert {"type": "invite", "target": "Gus"} in r["actions"]


def test_emote_tag_parsed_and_scrubbed():
    # Regression: "[EMOTE:wave]" used to leak into the visible chat text.
    r = parse_response("lol same man [EMOTE:wave] brb food", "SAY")
    assert "[EMOTE" not in r["message"]
    assert "EMOTE" not in r["message"]
    assert r["message"] == "lol same man brb food"
    assert {"type": "emote", "target": "wave"} in r["actions"]


def test_lowercase_emote_also_scrubbed():
    r = parse_response("hey [emote:laugh]", "SAY")
    assert "emote" not in r["message"].lower()
    assert {"type": "emote", "target": "laugh"} in r["actions"]


def test_multiple_tags():
    r = parse_response("hi [EMOTE:wave] ok [ACTION:emote cheer]", "SAY")
    assert "[" not in r["message"]
    assert len(r["actions"]) == 2


def test_all_caps_short_stays_channel():
    # Short all-caps shouldn't trip the YELL heuristic (needs len > 10).
    r = parse_response("OK", "SAY")
    assert r["channel"] == "SAY"
