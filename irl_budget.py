"""Fleet-wide IRL budget for ambient chatter (R3) + the shared IRL-line classifier.

A rolling window of the last IRL_WINDOW emitted ambient lines (tick + heard) records
whether each one referenced real life. While the IRL share is below IRL_TARGET the
prompt may offer the bot's real-life details; otherwise it asks for an in-game line.
In-memory, bounded, resets on reload (refills within minutes)."""
from __future__ import annotations

import re
from collections import deque

from config import IRL_TARGET, IRL_WINDOW

_IRL_RE = re.compile("|".join([
    r"\birl\b", r"\breal life\b",
    r"\b(?:at|from|after|before|off|for) work\b", r"\bwork (?:tomorrow|tonight|sucked|was)\b",
    r"\bmy (?:job|boss|shift|manager|coworkers?|commute)\b",
    r"\b(?:night|closing|double|morning|day|12[- ]hour) shift\b", r"\bshift (?:today|tomorrow|tonight)\b",
    r"\bcustomers?\b", r"\bclock(?:ed)? (?:in|out)\b",
    r"\b(?:homework|exams?|midterms?|essay|paper due|lecture|professor|teacher|dorm|campus)\b",
    r"\b(?:school|college) (?:today|tomorrow|tonight)\b", r"\bafter school\b",
    r"\bmy (?:gf|bf|girlfriend|boyfriend|wife|husband|partner|kids?|son|daughter|mom|dad|parents|"
    r"roommates?|brother|sister)\b",
    r"\b(?:gf|bf|hubby|kiddo|toddler)\b",
    r"\bwife aggro\b", r"\b(?:mom|dad) (?:says|said|made|called|is|wants|yelling|yelled)\b",
    r"\bkid woke\b", r"\bthe kids\b",
    r"\b(?:beer|coffee|pizza|dinner|lunch|breakfast|takeout|snacks?)\b",
    r"\b(?:go(?:ing)? to bed|need (?:to )?sleep|feet are killing|can['’]?t sleep)\b",
    r"\b(?:no|got|get|barely|need|some|any) sleep\b",
    r"\b(?:hours?|hrs?) (?:of )?sleep\b",
    r"\b(?:i'?m|im|so|really|super) tired\b(?!\s+of\b)",
    r"\b(?:netflix|youtube|spotify|my phone|traffic|rent|bills)\b",
    r"\b(?:on base|my unit|hospital|patients?)\b",
]), re.IGNORECASE)

_window: deque = deque(maxlen=IRL_WINDOW)


def is_irl_line(text: str, extra_terms=()) -> bool:
    """True if `text` references the real person's life. `extra_terms` are a bot's own
    distinctive IRL words (pet/partner names, workplace), matched as whole words."""
    text = text or ""
    if _IRL_RE.search(text):
        return True
    return any(re.search(rf"\b{re.escape(t)}\b", text, re.IGNORECASE) for t in extra_terms if t)


def reset_state() -> None:
    _window.clear()


def share() -> float:
    return sum(_window) / len(_window) if _window else 0.0


def irl_allowed() -> bool:
    return share() < IRL_TARGET


def note_ambient_line(text: str, extra_terms=()) -> bool:
    v = is_irl_line(text, extra_terms)
    _window.append(v)
    return v
