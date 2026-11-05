"""Evolving self-memory: a bot's changing sense of itself over time.

Mirrors consolidate.py. `summarize` is an injectable seam (tests mock it; a richer
backend — Claude / fan-out self-critique agents — swaps in later behind the same
signature). Parsing is pure and defensive: bad entries are dropped, never raised.
"""
from __future__ import annotations

import json

import httpx

import db
from config import OLLAMA_URL, OLLAMA_MODEL

_MAX_NOTES = 4


def parse_self_notes(raw: str) -> list[dict]:
    """Parse summarizer output into validated self-notes.

    Expected shape: a JSON list of {subject:str, note:str}. Entries missing
    subject/note, or non-dict items, are dropped. Capped at _MAX_NOTES.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject")
        note = item.get("note")
        if not subject or not note:
            continue
        out.append({"subject": str(subject), "note": str(note)})
        if len(out) >= _MAX_NOTES:
            break
    return out


def _format_current(notes: list[dict]) -> str:
    if not notes:
        return "(nothing yet — this is the first time you're reflecting)"
    return "; ".join(f"{n['subject']}: {n['content']}" for n in notes)


def local_summarize_self(transcript: str, name: str, who: str, current: str) -> str:
    """Default backend: ask the local model, AS the bot, for its UPDATED self-view as
    a JSON list. Synchronous (runs off the request path). Never called in tests."""
    system = (
        f"You are {name}, a real person playing WoW in 2005. Off the game you are: {who}. "
        f"This is your private self-reflection — how you see YOURSELF right now (your mood, "
        f"what you're into lately, how you feel about your character and the grind), NOT about "
        f"other people. Here is how you saw yourself before: {current}. "
        f"Read your recent chat below and output your UPDATED self-view as ONLY a JSON list "
        f'of up to {_MAX_NOTES} short notes, each {{"subject": one-word key like mood/interests/'
        f'outlook, "note": a short first-person line}}. Let it evolve from before — keep what '
        f"still fits, change what shifted. No prose, JSON only."
    )
    resp = httpx.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL, "think": False, "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": transcript or "(quiet session, not much said)"},
        ],
        "options": {"num_predict": 220, "temperature": 0.4},
    }, timeout=60.0)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def consolidate_self(bot_name: str, *, summarize=None, who: str = "",
                     recent_limit: int = 12) -> list[dict]:
    """Derive + persist + prune the bot's self-view from its recent messages.

    `summarize` resolves to `local_summarize_self` at CALL time so tests can inject a
    fake. Returns the applied notes. Evolution = the model rewrites its self-view each
    pass from (old self-view + recent behavior); subjects overwrite, sheet pruned to 4.
    """
    if summarize is None:
        summarize = local_summarize_self
    msgs = db.get_recent_messages(bot_name, limit=recent_limit)
    transcript = "\n".join(
        f"{'You' if m['role'] == 'assistant' else m['player_name']}: {m['content']}"
        for m in msgs
    )
    current = _format_current(db.get_memory_sheet(bot_name, "self"))
    raw = summarize(transcript, bot_name, who, current)
    applied = parse_self_notes(raw)
    for note in applied:
        db.upsert_memory(bot_name, "self", note["subject"], note["note"])
    db.prune_memory(bot_name, "self", keep=_MAX_NOTES)
    return applied
