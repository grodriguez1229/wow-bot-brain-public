"""HTTP client for an (experiment) brain instance — a sibling of the C++ LlmBridge.

Calls the same /chat and /tick endpoints the game calls, but driven by the
simulator's orchestration instead of the game's random hooks.
"""
from __future__ import annotations

import httpx


class BrainClient:
    def __init__(self, base_url: str = "http://localhost:5001", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(self, bot_name, player_name, message, channel="SAY", location="", recent_lines=None):
        payload = {
            "bot_name": bot_name, "player_name": player_name,
            "message": message, "channel": channel, "location": location,
        }
        if recent_lines:
            payload["recent_lines"] = recent_lines
        r = httpx.post(f"{self.base_url}/chat", json=payload, timeout=self.timeout)
        r.raise_for_status()
        d = r.json()
        return {"message": d.get("message", ""), "channel": d.get("channel", channel),
                "actions": d.get("actions", [])}

    def tick(self, bot_name, location="", nearby_players=None, nearby_bots=None, recent_lines=None):
        payload = {
            "bot_name": bot_name, "location": location,
            "nearby_players": nearby_players or [], "nearby_bots": nearby_bots or [],
        }
        if recent_lines:
            payload["recent_lines"] = recent_lines
        r = httpx.post(f"{self.base_url}/tick", json=payload, timeout=self.timeout)
        r.raise_for_status()
        d = r.json()
        return {"message": d.get("message", ""), "channel": d.get("channel", "SAY"),
                "actions": d.get("actions", [])}
