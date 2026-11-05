"""R9 shared-history store: sessions, events, moments and player presence.

All SQLite access goes through db.get_db(). Times are unix epoch seconds.
"""
import json
import time

import db


def _now(now):
    return time.time() if now is None else now


def _run(sql: str, params=()):
    conn = db.get_db()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _rows(sql: str, params=()) -> list[dict]:
    conn = db.get_db()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _scalar(sql: str, params=()) -> int:
    conn = db.get_db()
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


# --- sessions -------------------------------------------------------------

def open_session(player: str, bot: str, kind: str, *, instance: str | None = None,
                 zone: str | None = None, now: float | None = None) -> int:
    return _run(
        "INSERT INTO play_sessions (player_name, bot_name, kind, instance, zone, started_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (player, bot, kind, instance, zone, _now(now)))


def open_sessions(player: str, kind: str | None = None) -> list[dict]:
    sql = "SELECT * FROM play_sessions WHERE player_name = ? AND ended_at IS NULL"
    params: list = [player]
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    return _rows(sql + " ORDER BY started_at, id", params)


def close_session(session_id: int, *, ended_at: float, outcome: str | None = None) -> dict:
    _run("UPDATE play_sessions SET ended_at = ?, outcome = COALESCE(?, outcome) WHERE id = ?",
         (ended_at, outcome, session_id))
    return _rows("SELECT * FROM play_sessions WHERE id = ?", (session_id,))[0]


def recent_closed_run(player: str, bot: str, instance: str, *, since: float) -> dict | None:
    rows = _rows(
        "SELECT * FROM play_sessions WHERE player_name = ? AND bot_name = ? AND kind = 'run'"
        " AND instance = ? AND ended_at IS NOT NULL AND ended_at >= ?"
        " ORDER BY ended_at DESC, id DESC LIMIT 1", (player, bot, instance, since))
    return rows[0] if rows else None


def reopen_session(session_id: int) -> None:
    """Clear ended_at; a non-cleared outcome is dropped so the final close decides it."""
    _run("UPDATE play_sessions SET ended_at = NULL,"
         " outcome = CASE WHEN outcome = 'cleared' THEN outcome ELSE NULL END WHERE id = ?",
         (session_id,))


def delete_moments(source: str, source_id: int, *, text_prefix: str = "") -> None:
    _run("DELETE FROM moments WHERE source = ? AND source_id = ? AND text LIKE ?",
         (source, source_id, text_prefix + "%"))


def bump_session(session_id: int, *, bosses: int = 0, wipes: int = 0,
                 outcome: str | None = None) -> None:
    _run("UPDATE play_sessions SET bosses = bosses + ?, wipes = wipes + ?,"
         " outcome = COALESCE(?, outcome) WHERE id = ?",
         (bosses, wipes, outcome, session_id))


def runs_together(player: str, bot: str) -> int:
    return _scalar(
        "SELECT COUNT(*) FROM play_sessions WHERE player_name = ? AND bot_name = ?"
        " AND kind = 'run' AND ended_at IS NOT NULL AND COALESCE(outcome, '') != 'bounce'",
        (player, bot))


def long_sessions(player: str, bot: str, min_s: float) -> int:
    return _scalar(
        "SELECT COUNT(*) FROM play_sessions WHERE player_name = ? AND bot_name = ?"
        " AND kind = 'group' AND ended_at IS NOT NULL AND ended_at - started_at >= ?",
        (player, bot, min_s))


# --- events ---------------------------------------------------------------

def add_event(player: str, bot: str, kind: str, *, instance: str | None = None,
              zone: str | None = None, detail: str = "", session_id: int | None = None,
              now: float | None = None) -> int:
    return _run(
        "INSERT INTO shared_events (ts, player_name, bot_name, kind, instance, zone, detail,"
        " session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (_now(now), player, bot, kind, instance, zone, detail, session_id))


def count_events(player: str, bot: str, kind: str, *, since: float) -> int:
    return _scalar(
        "SELECT COUNT(*) FROM shared_events WHERE player_name = ? AND bot_name = ?"
        " AND kind = ? AND ts >= ?", (player, bot, kind, since))


def last_event(player: str, bot: str, kind: str) -> dict | None:
    rows = _rows(
        "SELECT * FROM shared_events WHERE player_name = ? AND bot_name = ? AND kind = ?"
        " ORDER BY ts DESC, id DESC LIMIT 1", (player, bot, kind))
    return rows[0] if rows else None


# --- moments --------------------------------------------------------------

def add_moment(player: str, bot: str, text: str, *, source: str, source_id: int,
               places: list[str], now: float | None = None) -> int:
    return _run(
        "INSERT INTO moments (player_name, bot_name, ts, text, source, source_id, places)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (player, bot, _now(now), text, source, source_id, json.dumps(places)))


def moments_for(player: str, bot: str, limit: int = 3) -> list[dict]:
    rows = _rows(
        "SELECT * FROM moments WHERE player_name = ? AND bot_name = ?"
        " ORDER BY cited_at IS NOT NULL, cited_at, ts DESC, id DESC LIMIT ?",
        (player, bot, limit))
    for r in rows:
        r["places"] = json.loads(r["places"] or "[]")
    return rows


def mark_cited(ids: list[int], *, now: float | None = None) -> None:
    if not ids:
        return
    marks = ",".join("?" * len(ids))
    _run(f"UPDATE moments SET cited_at = ? WHERE id IN ({marks})", [_now(now), *ids])


# --- player presence ------------------------------------------------------

def note_player_seen(player: str, *, level: int | None = None, faction: str | None = None,
                     zone: str | None = None, login: bool = False, logout: bool = False,
                     now: float | None = None) -> None:
    t = _now(now)
    _run(
        "INSERT INTO player_seen (player_name, last_seen, last_login, last_logout, level,"
        " faction, zone) VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(player_name) DO UPDATE SET last_seen = excluded.last_seen,"
        " last_login = COALESCE(excluded.last_login, last_login),"
        " last_logout = COALESCE(excluded.last_logout, last_logout),"
        " level = COALESCE(excluded.level, level),"
        " faction = COALESCE(excluded.faction, faction),"
        " zone = COALESCE(excluded.zone, zone)",
        (player, t, t if login else None, t if logout else None, level, faction, zone))


def player_seen(player: str) -> dict | None:
    rows = _rows("SELECT * FROM player_seen WHERE player_name = ?", (player,))
    return rows[0] if rows else None
