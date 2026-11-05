"""Earned, capped, decaying familiarity (R9).

relationships keeps chat_points (capped) and play_points (earned in shared play);
`familiarity` / `label` stay the stored effective value for existing readers.
"""
import math
import time

import db
import history
from config import (FAM_CHAT_CAP, FAM_CHAT_POINTS, FAM_DECAY_PER_DAY, FAM_FRIEND_MIN,
                    LONG_SESSION_S, WHISPER_MIN_RUNS)

DAY_S = 86400


def effective(chat: float, play: float) -> int:
    return max(0, min(100, round(min(chat, FAM_CHAT_CAP) + play)))


def label_for(fam: int) -> str:
    if fam >= 50: return "good friend"
    if fam >= 25: return "friend"
    if fam >= 10: return "acquaintance"
    if fam >= 3: return "seen around"
    return "stranger"


def _now(now):
    return time.time() if now is None else now


def migrate(conn, now: float) -> None:
    """Legacy rows: stored points become chat points; effective value is capped."""
    conn.execute("UPDATE relationships SET chat_points = COALESCE(familiarity, 0),"
                 " play_points = 0, decayed_at = ? WHERE chat_points IS NULL", (now,))
    for r in conn.execute("SELECT bot_name, player_name, chat_points, play_points"
                          " FROM relationships").fetchall():
        fam = effective(r["chat_points"], r["play_points"] or 0)
        conn.execute("UPDATE relationships SET familiarity = ?, label = ?"
                     " WHERE bot_name = ? AND player_name = ?",
                     (fam, label_for(fam), r["bot_name"], r["player_name"]))


def _load(conn, bot: str, player: str, now: float) -> dict:
    conn.execute("INSERT OR IGNORE INTO relationships (bot_name, player_name, familiarity,"
                 " label, chat_points, play_points, decayed_at)"
                 " VALUES (?, ?, 0, 'stranger', 0, 0, ?)", (bot, player, now))
    row = dict(conn.execute("SELECT * FROM relationships WHERE bot_name = ? AND player_name = ?",
                            (bot, player)).fetchone())
    # rows created elsewhere (e.g. notes) may lack the new columns
    if row["chat_points"] is None:
        row["chat_points"] = row["familiarity"] or 0
    if row["play_points"] is None:
        row["play_points"] = 0
    if row["decayed_at"] is None:
        row["decayed_at"] = now
    return row


def _decay(row: dict, now: float) -> None:
    base = max(row["last_play_at"] or 0, row["decayed_at"] or now)
    days = math.floor((now - base) / DAY_S)
    if days < 1:
        return
    loss = days * FAM_DECAY_PER_DAY
    from_play = min(loss, row["play_points"])
    row["play_points"] -= from_play
    row["chat_points"] = max(0.0, row["chat_points"] - (loss - from_play))
    row["decayed_at"] = base + days * DAY_S


def _save(conn, row: dict) -> dict:
    row["familiarity"] = effective(row["chat_points"], row["play_points"])
    row["label"] = label_for(row["familiarity"])
    conn.execute("UPDATE relationships SET familiarity = ?, label = ?, chat_points = ?,"
                 " play_points = ?, last_play_at = ?, decayed_at = ?"
                 " WHERE bot_name = ? AND player_name = ?",
                 (row["familiarity"], row["label"], row["chat_points"], row["play_points"],
                  row["last_play_at"], row["decayed_at"], row["bot_name"], row["player_name"]))
    return row


def _update(bot: str, player: str, now, mutate=None) -> dict:
    now = _now(now)
    conn = db.get_db()
    try:
        row = _load(conn, bot, player, now)
        _decay(row, now)
        if mutate:
            mutate(row, now)
        _save(conn, row)
        conn.commit()
        return row
    finally:
        conn.close()


def apply_decay(bot: str, player: str, *, now=None) -> dict:
    return _update(bot, player, now)


def add_chat(bot: str, player: str, delta: float = FAM_CHAT_POINTS, *, now=None) -> dict:
    def mutate(row, _now):
        if delta >= 0:
            row["chat_points"] = max(row["chat_points"],
                                     min(row["chat_points"] + delta, FAM_CHAT_CAP))
        else:
            row["chat_points"] = max(0.0, row["chat_points"] + delta)
    return _update(bot, player, now, mutate)


def add_play(bot: str, player: str, points: float, *, now=None) -> dict:
    def mutate(row, n):
        row["play_points"] = max(0.0, row["play_points"] + points)
        row["last_play_at"] = n
    return _update(bot, player, now, mutate)


def is_whisper_eligible(bot: str, player: str, *, now=None) -> bool:
    row = apply_decay(bot, player, now=now)
    if row["familiarity"] < FAM_FRIEND_MIN:
        return False
    return (history.runs_together(player, bot) >= WHISPER_MIN_RUNS
            or history.long_sessions(player, bot, LONG_SESSION_S) >= 1)
