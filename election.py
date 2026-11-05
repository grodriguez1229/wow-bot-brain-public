"""Responder election for /heard events.

Pure decision logic + a small in-memory recency state (resets on restart —
acceptable per spec: worst case is one missed 'engaged' window)."""
from collections import deque
import random
import re
import time

from config import (HEARD_ENGAGED_WINDOW_S, HEARD_CONVO_WINDOW_S, HEARD_ENGAGED_CHANCE,
                    HEARD_CANDIDATE_CHANCE, HEARD_MAX_RESPONDERS, HEARD_COOLDOWN_S,
                    HEARD_MAX_HEARERS, HEARD_MAX_NAMED,
                    FLEET_DEDUP_WINDOW_S, FLEET_DEDUP_MAXLEN, FLEET_DEDUP_THRESHOLD)

_MIN_PREFIX = 4


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def named_in(message: str, bot_names: list[str]) -> list[str]:
    """Bots addressed by name: a message word equals the name or is a >=4-char prefix of it."""
    words = set(_words(message))
    out = []
    for name in bot_names:
        low = name.lower()
        if low in words or any(len(w) >= _MIN_PREFIX and low.startswith(w) for w in words):
            out.append(name)
    return out


def cap_hearers(hearers: list[dict], message: str, cap: int = HEARD_MAX_HEARERS) -> list[dict]:
    """Bound the roster: named hearers always kept, nearest fill the remainder."""
    if len(hearers) <= cap:
        return hearers
    named = set(named_in(message, [h["bot_name"] for h in hearers]))
    keep = [h for h in hearers if h["bot_name"] in named]
    rest = sorted((h for h in hearers if h["bot_name"] not in named),
                  key=lambda h: h.get("distance", 0.0))
    return keep + rest[: max(0, cap - len(keep))]


# ── recency state ────────────────────────────────────────────────────────────
_last_spoke: dict[tuple[str, str], float] = {}    # (bot, channel) -> last line ts
_last_reply: dict[tuple[str, str], float] = {}    # (bot, channel) -> last elected reply ts

# Fleet-wide window of recently-emitted lines (token sets + timestamps) so 150 bots
# don't converge on the same phrasing. In-memory, bounded, resets on restart.
_fleet_lines: deque = deque(maxlen=FLEET_DEDUP_MAXLEN)   # (ts, frozenset[str])


def reset_state() -> None:
    _last_spoke.clear()
    _last_reply.clear()
    _fleet_lines.clear()


def note_bot_spoke(bot_name: str, channel: str, now: float | None = None) -> None:
    _last_spoke[(bot_name, channel)] = time.time() if now is None else now


def note_replied(bot_name: str, channel: str, now: float | None = None) -> None:
    _last_reply[(bot_name, channel)] = time.time() if now is None else now


def is_pass(text: str) -> bool:
    return (text or "").strip().lower() in ("", "pass", "pass.")


def _keyword_score(message: str, persona_text: str) -> int:
    msg = {w for w in _words(message) if len(w) >= _MIN_PREFIX}
    persona = {w for w in _words(persona_text) if len(w) >= _MIN_PREFIX}
    return len(msg & persona)


def elect(hearers: list[dict], message: str, speaker: str, channel: str, *,
          get_familiarity, get_persona_text, recent_convo,
          now: float | None = None, rng: random.Random | None = None) -> list[dict]:
    """Tiered election. Named: guaranteed (no cap, no cooldown). Engaged: spoke in this
    channel recently or has an open convo with the speaker -> HEARD_ENGAGED_CHANCE.
    Candidate: top-2 by familiarity + persona keyword overlap (score > 0) ->
    HEARD_CANDIDATE_CHANCE. Non-named respect HEARD_MAX_RESPONDERS and HEARD_COOLDOWN_S."""
    now = time.time() if now is None else now
    rng = rng or random
    names = [h["bot_name"] for h in hearers]
    named = set(named_in(message, names))

    elected = [{"bot_name": n, "tier": "named"} for n in names if n in named][:HEARD_MAX_NAMED]
    budget = max(0, HEARD_MAX_RESPONDERS - len(elected))

    def on_cooldown(b: str) -> bool:
        return now - _last_reply.get((b, channel), -1e18) < HEARD_COOLDOWN_S

    pool = [n for n in names if n not in named and not on_cooldown(n)]

    engaged = [b for b in pool
               if now - _last_spoke.get((b, channel), -1e18) <= HEARD_ENGAGED_WINDOW_S
               or recent_convo(b)]
    for b in engaged:
        if budget <= 0:
            break
        if rng.random() < HEARD_ENGAGED_CHANCE:
            elected.append({"bot_name": b, "tier": "engaged"})
            budget -= 1

    taken = {e["bot_name"] for e in elected}
    scored = sorted(((get_familiarity(b) + _keyword_score(message, get_persona_text(b)), b)
                     for b in pool if b not in taken), key=lambda t: -t[0])
    for score, b in scored[:2]:
        if budget <= 0 or score <= 0:
            break
        if rng.random() < HEARD_CANDIDATE_CHANCE:
            elected.append({"bot_name": b, "tier": "candidate"})
            budget -= 1

    return elected


def _line_tokens(text: str) -> frozenset:
    return frozenset(_words(text))


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def note_fleet_line(text: str, now: float | None = None) -> None:
    """Record an emitted ambient line for cross-bot dedup."""
    toks = _line_tokens(text)
    if toks:
        _fleet_lines.append((time.time() if now is None else now, toks))


def is_duplicate_line(text: str, now: float | None = None) -> bool:
    """True if `text` closely matches a still-fresh fleet line (token Jaccard >= threshold)."""
    toks = _line_tokens(text)
    if not toks:
        return False
    now = time.time() if now is None else now
    for ts, prev in _fleet_lines:
        if now - ts > FLEET_DEDUP_WINDOW_S:
            continue
        if _jaccard(toks, prev) >= FLEET_DEDUP_THRESHOLD:
            return True
    return False
