"""/heard wire models."""
from models import HeardHearer, HeardRequest, HeardReply, HeardResponse


def test_heard_request_defaults():
    req = HeardRequest(speaker="Abril", message="hi all",
                       hearers=[{"bot_name": "Vivi"}])
    assert req.channel == "SAY" and req.location is None
    assert req.hearers[0].distance == 0.0 and req.hearers[0].same_party is False


def test_heard_response_shape():
    r = HeardResponse(responses=[HeardReply(bot_name="Vivi", message="yo", channel="SAY")])
    d = r.model_dump()
    assert d["responses"][0]["bot_name"] == "Vivi"
    assert d["responses"][0]["emote"] is None
