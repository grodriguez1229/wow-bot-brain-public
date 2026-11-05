"""Pure builders for the memory prompt sections. No I/O — unit-testable.

Both builders accept plain dicts so callers (main.py converts Pydantic
RecentLine via .model_dump(); db rows are sqlite3.Row -> dict) and tests share
one code path. Empty input renders an empty string, preserving prior prompts.
"""
from __future__ import annotations


def build_nearby_section(recent_lines: list[dict] | None) -> str:
    if not recent_lines:
        return ""
    lines = [f"  {rl['speaker']}: {rl['text']}" for rl in recent_lines]
    return ("OVERHEARD NEARBY (react to this, don't repeat it — say something new "
            "or do your own thing):\n" + "\n".join(lines))


def build_relationship_section(rel: dict | None) -> str:
    notes = ((rel or {}).get("notes") or "").strip()
    if not notes:
        return ""
    return f"WHAT YOU REMEMBER ABOUT THEM: {notes}"


def build_self_section(self_notes: list[dict] | None) -> str:
    """The bot's evolving self-view (kind='self' rows). Empty -> '' so prompts are
    unchanged for a bot that hasn't reflected yet."""
    if not self_notes:
        return ""
    parts = [(n.get("content") or "").strip() for n in self_notes]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return "HOW YOU'VE BEEN FEELING / HOW YOU SEE YOURSELF LATELY: " + "; ".join(parts)


def build_identity_section(identity_facets: list[dict] | None) -> str:
    """The bot's accumulated, drifting identity (kind='identity' rows), strongest first.
    Empty -> '' so a never-reflected bot prompts exactly as before."""
    if not identity_facets:
        return ""
    facets = sorted(identity_facets, key=lambda f: -int(f.get("weight", 1) or 1))
    lines = [f"- {c}" for f in facets if (c := (f.get("content") or "").strip())]
    if not lines:
        return ""
    return ("WHO YOU'VE BECOME (this grew out of your time on the server — let it color "
            "how you talk, what you care about, who you like):\n" + "\n".join(lines))
