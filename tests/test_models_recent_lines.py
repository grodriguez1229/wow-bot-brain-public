from models import ChatRequest, TickRequest, RecentLine


def test_chat_request_accepts_recent_lines():
    req = ChatRequest(
        bot_name="Geysse", player_name="Gus", message="hi",
        recent_lines=[{"speaker": "Lynea", "text": "anyone running Deadmines?"}],
    )
    assert isinstance(req.recent_lines[0], RecentLine)
    assert req.recent_lines[0].speaker == "Lynea"
    assert req.recent_lines[0].text == "anyone running Deadmines?"


def test_tick_request_recent_lines_defaults_none():
    req = TickRequest(bot_name="Geysse", location="Elwynn Forest")
    assert req.recent_lines is None
