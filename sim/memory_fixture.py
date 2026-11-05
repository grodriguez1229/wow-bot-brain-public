"""Restore bot memory to a fixed, checked-in state before a scored eval run.

Persistent memory would make eval runs incomparable; loading this fixture (and
running scored generation with consolidation OFF) makes the relationship layer
contribute identically across candidates, preserving attribution.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import db


def load_memory_fixture(path: str, db_path: str | None = None) -> None:
    data = json.loads(Path(path).read_text())
    if db_path is None:
        conn = db.get_db()
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    try:
        conn.execute("DELETE FROM relationships")
        conn.execute("DELETE FROM bot_memory")
        for r in data.get("relationships", []):
            conn.execute(
                """INSERT INTO relationships (bot_name, player_name, familiarity, label, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (r["bot_name"], r["player_name"], r["familiarity"], r["label"], r["notes"]),
            )
        for m in data.get("bot_memory", []):
            conn.execute(
                """INSERT INTO bot_memory (bot_name, kind, subject, content, weight)
                   VALUES (?, ?, ?, ?, ?)""",
                (m["bot_name"], m["kind"], m["subject"], m["content"], m.get("weight", 1)),
            )
        conn.commit()
    finally:
        conn.close()


_CAST_COLS = ("bot_name", "race", "class_name", "level", "gender", "faction",
              "identity_id", "who", "typing_style", "current_goal")


def seed_cast(path: str, db_path: str | None = None) -> None:
    """Pin a fixed evaluation cast: write full bot_personalities rows so the base persona
    never re-rolls between optimizer cycles (the brain uses an existing row as-is, no
    IRL_IDENTITIES re-roll, no game-DB lookup). Idempotent (INSERT OR REPLACE)."""
    data = json.loads(Path(path).read_text())
    if db_path is None:
        conn = db.get_db()
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    try:
        cols = ", ".join(_CAST_COLS + ("irl_json",))
        placeholders = ", ".join("?" for _ in range(len(_CAST_COLS) + 1))
        for bot in data.get("bots", []):
            conn.execute(
                f"INSERT OR REPLACE INTO bot_personalities ({cols}) VALUES ({placeholders})",
                tuple(bot[c] for c in _CAST_COLS) + ('{"pinned": true}',),
            )
        conn.commit()
    finally:
        conn.close()
