import sim.brain_client as bc


class _Resp:
    status_code = 200
    def raise_for_status(self): pass
    def json(self): return {"message": "ok", "channel": "SAY", "actions": []}


def test_chat_forwards_recent_lines(monkeypatch):
    captured = {}
    def fake_post(url, json, timeout):
        captured["json"] = json
        return _Resp()
    monkeypatch.setattr(bc.httpx, "post", fake_post)

    client = bc.BrainClient()
    client.chat("Geysse", "Gus", "hi", "SAY", "Elwynn Forest",
                recent_lines=[{"speaker": "Lynea", "text": "hey"}])
    assert captured["json"]["recent_lines"] == [{"speaker": "Lynea", "text": "hey"}]


def test_tick_forwards_recent_lines(monkeypatch):
    captured = {}
    monkeypatch.setattr(bc.httpx, "post", lambda url, json, timeout: (captured.update(json=json) or _Resp()))
    client = bc.BrainClient()
    client.tick("Geysse", "Elwynn Forest", [], ["Lynea"],
                recent_lines=[{"speaker": "Lynea", "text": "hey"}])
    assert captured["json"]["recent_lines"] == [{"speaker": "Lynea", "text": "hey"}]


def test_recent_lines_omitted_when_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(bc.httpx, "post", lambda url, json, timeout: (captured.update(json=json) or _Resp()))
    bc.BrainClient().chat("Geysse", "Gus", "hi")
    assert captured["json"].get("recent_lines") in (None, [])
