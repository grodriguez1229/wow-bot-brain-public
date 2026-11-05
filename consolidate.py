"""Write-path skeleton: turn a finished Scene transcript into durable memory.

Phase 1 wires ONE layer (relationships) end-to-end. `summarize` is an injectable
callable (transcript_text, bot_name) -> raw JSON string, so tests mock it and a
richer backend (Claude / fan-out critique agents) swaps in later behind the same
signature. Parsing is pure and defensive: bad entries are dropped, never raised.
"""
from __future__ import annotations

import json

_DELTA_MIN, _DELTA_MAX = -5, 5


def parse_consolidation(raw: str) -> list[dict]:
    """Parse summarizer output into validated relationship updates.

    Expected shape: a JSON list of {subject:str, note:str, familiarity_delta:int}.
    Entries missing subject/note, or non-dict items, are dropped. Delta is clamped.
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
        try:
            delta = int(item.get("familiarity_delta", 0))
        except (TypeError, ValueError):
            delta = 0
        delta = max(_DELTA_MIN, min(_DELTA_MAX, delta))
        out.append({"subject": str(subject), "note": str(note), "familiarity_delta": delta})
    return out


import httpx

import db
from config import OLLAMA_URL, OLLAMA_MODEL


def _transcript_text(scene) -> str:
    return "\n".join(f"{t.speaker}: {t.text}" for t in scene.turns)


def local_summarize(transcript_text: str, bot_name: str) -> str:
    """Default backend: ask the local model, as `bot_name`, for relationship
    updates as a JSON list. Synchronous (consolidation runs outside request
    handling). Never called in tests — they inject a fake summarize."""
    system = (
        f"You are {bot_name}. Read this WoW zone chat you took part in and output ONLY a "
        f"JSON list of relationship updates about OTHER people, each "
        f'{{"subject": name, "note": short memory, "familiarity_delta": -5..5}}. '
        f"No prose, JSON only."
    )
    resp = httpx.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL, "think": False, "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": transcript_text},
        ],
        "options": {"num_predict": 200, "temperature": 0.3},
    }, timeout=60.0)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def consolidate_scene(scene, *, summarize=None, bots=None) -> list[dict]:
    """For each bot participant, derive + persist relationship updates from the
    scene transcript. Returns the flat list of applied updates.

    `summarize` resolves to `local_summarize` at CALL time (not as a default-arg
    value) so monkeypatching `consolidate.local_summarize` in tests takes effect."""
    if summarize is None:
        summarize = local_summarize
    if bots is None:
        bots = list(scene.participants)
    transcript = _transcript_text(scene)
    applied: list[dict] = []
    for bot in bots:
        raw = summarize(transcript, bot)
        for upd in parse_consolidation(raw):
            subject, note, delta = upd["subject"], upd["note"], upd["familiarity_delta"]
            db.set_relationship_notes(bot, subject, note)
            if delta:
                db.update_relationship(bot, subject, familiarity_delta=delta)
            db.upsert_memory(bot, "relationship", subject, note)
            applied.append({"bot": bot, **upd})
    return applied
