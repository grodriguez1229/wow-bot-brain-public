"""Fleet-wide chat log of recent channel lines + reply threads (R8). In-memory.

The worldserver never sends `recent_lines` on /tick (LlmBridge::PostTick), so the brain
keeps its own ring buffer of what was said: every emitted tick line, every /heard
incoming line and every heard reply. A ticking bot can then reply to a line it could
plausibly see in-game:
  GENERAL  same zone + faction        TRADE / LFG  same faction
  GUILD    same guild                 SAY          same zone, speaker within ~40yd (nearby)
Lines from real players carry faction None (unknown) and match either faction.
Reply chains are tracked (root line + depth) and capped at REPLY_DEPTH_CAP; a line takes
at most MAX_DIRECT_REPLIES replies. Bounded; resets on reload (refills in minutes)."""
from __future__ import annotations

import itertools
import random
import re
import time
from collections import deque

from config import CHAT_LOG_MAXLEN, CHAT_LOG_TTL_S, REPLY_DEPTH_CAP

MAX_DIRECT_REPLIES = 2
VISIBLE = ("GENERAL", "TRADE", "LFG", "GUILD", "SAY")
_QUESTION = re.compile(r"\?\s*$|^(?:any(?:one|1|body)?|who|what|where|when|how|why|is|does|"
                       r"can|u|do|wanna|want)\b", re.IGNORECASE)

_log: deque = deque(maxlen=CHAT_LOG_MAXLEN)
_by_id: dict[int, dict] = {}
_ids = itertools.count(1)


def reset_state() -> None:
    _log.clear()
    _by_id.clear()


def _norm_channel(ch: str) -> str:
    ch = (ch or "SAY").upper()
    return "SAY" if ch in ("YELL", "PARTY") else ch


def record_line(speaker: str, channel: str, text: str, *, faction: str | None = None,
                zone: str | None = None, guild: str | None = None, reply_to: int | None = None,
                now: float | None = None) -> int:
    now = time.time() if now is None else now
    parent = _by_id.get(reply_to) if reply_to else None
    eid = next(_ids)
    e = {"id": eid, "ts": now, "speaker": speaker, "channel": _norm_channel(channel),
         "text": text, "faction": faction, "zone": zone or "", "guild": guild or "",
         "root": parent["root"] if parent else eid, "depth": parent["depth"] + 1 if parent else 0,
         "reply_to": parent["id"] if parent else None, "replies": 0, "repliers": set()}
    if parent:
        parent["replies"] += 1
        parent["repliers"].add(speaker)
    if len(_log) == _log.maxlen:
        _by_id.pop(_log[0]["id"], None)
    _log.append(e)
    _by_id[eid] = e
    return eid


def get(eid: int) -> dict | None:
    return _by_id.get(eid)


def _in_scope(e: dict, channel: str, faction, zone, guild, nearby) -> bool:
    if e["channel"] != channel:
        return False
    fac_ok = e["faction"] is None or faction is None or e["faction"] == faction
    if channel == "GENERAL":
        return fac_ok and bool(zone) and e["zone"] == zone
    if channel in ("TRADE", "LFG"):
        return fac_ok
    if channel == "GUILD":
        return bool(guild) and e["guild"] == guild
    if channel == "SAY":
        return bool(zone) and e["zone"] == zone and e["speaker"] in nearby
    return False


def reply_candidates(bot_name: str, *, faction: str | None, zone: str | None,
                     guild: str | None = None, nearby=(), channels=VISIBLE,
                     now: float | None = None) -> list[dict]:
    """Fresh lines by OTHER speakers this bot could see, still open for a reply."""
    now = time.time() if now is None else now
    nearby = set(nearby or ())
    out = []
    for e in _log:
        if (e["speaker"] == bot_name or now - e["ts"] > CHAT_LOG_TTL_S
                or e["depth"] >= REPLY_DEPTH_CAP or e["replies"] >= MAX_DIRECT_REPLIES
                or bot_name in e["repliers"]):
            continue
        if any(_in_scope(e, ch, faction, zone, guild, nearby) for ch in channels):
            out.append(e)
    return out


def is_question(text: str) -> bool:
    return bool(_QUESTION.search((text or "").strip()))


def pick_reply_target(cands: list[dict], rng=None, now: float | None = None) -> dict | None:
    """Prefer questions (x3) and lines nobody answered yet (x2); newer lines weigh more."""
    if not cands:
        return None
    rng = rng or random
    now = time.time() if now is None else now
    weights = []
    for e in cands:
        w = 1.0
        if is_question(e["text"]):
            w *= 3
        if e["replies"] == 0:
            w *= 2
        w *= 1 + max(0.0, 1 - (now - e["ts"]) / CHAT_LOG_TTL_S)
        weights.append(w)
    return rng.choices(cands, weights=weights, k=1)[0]


def recent_context(target: dict, n: int = 4) -> list[dict]:
    """Up to `n` lines of the target's channel scope ending with the target itself."""
    same = [e for e in _log if e["channel"] == target["channel"] and e["ts"] <= target["ts"]
            and _same_scope(e, target)]
    same = [e for e in same if e["id"] != target["id"]][-(n - 1):] if n > 1 else []
    return same + [target]


def _same_scope(a: dict, b: dict) -> bool:
    ch = a["channel"]
    if ch in ("GENERAL", "SAY"):
        return a["zone"] == b["zone"]
    if ch == "GUILD":
        return a["guild"] == b["guild"]
    return a["faction"] is None or b["faction"] is None or a["faction"] == b["faction"]
