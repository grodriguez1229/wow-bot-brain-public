import sqlite3
import time
from config import DB_PATH, MEMORY_WINDOW


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_name TEXT NOT NULL,
            player_name TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_personalities (
            bot_name TEXT PRIMARY KEY,
            race TEXT NOT NULL,
            class_name TEXT NOT NULL,
            level INTEGER NOT NULL,
            gender TEXT NOT NULL,
            faction TEXT NOT NULL,
            identity_id TEXT NOT NULL,
            who TEXT NOT NULL,
            typing_style TEXT NOT NULL,
            current_goal TEXT NOT NULL,
            guild_name TEXT DEFAULT '',
            in_group INTEGER DEFAULT 0,
            motivation TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            bot_name TEXT NOT NULL,
            player_name TEXT NOT NULL,
            familiarity INTEGER DEFAULT 0,
            label TEXT DEFAULT 'stranger',
            notes TEXT DEFAULT '',
            PRIMARY KEY (bot_name, player_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_memory (
            bot_name   TEXT NOT NULL,
            kind       TEXT NOT NULL,
            subject    TEXT NOT NULL,
            content    TEXT NOT NULL,
            weight     INTEGER DEFAULT 1,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (bot_name, kind, subject)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS play_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT, bot_name TEXT, kind TEXT, instance TEXT, zone TEXT,
            started_at REAL, ended_at REAL, outcome TEXT,
            bosses INTEGER DEFAULT 0, wipes INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_play_sessions_pair ON play_sessions (player_name, bot_name)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shared_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, player_name TEXT, bot_name TEXT, kind TEXT, instance TEXT, zone TEXT,
            detail TEXT, session_id INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shared_events_pair ON shared_events (player_name, bot_name, kind)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS moments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT, bot_name TEXT, ts REAL, text TEXT, source TEXT,
            source_id INTEGER, places TEXT, cited_at REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_moments_pair ON moments (player_name, bot_name)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_seen (
            player_name TEXT PRIMARY KEY,
            last_seen REAL, last_login REAL, last_logout REAL,
            level INTEGER, faction TEXT, zone TEXT
        )
    """)
    # Migrate: add guild_name and in_group if missing
    try:
        conn.execute("ALTER TABLE bot_personalities ADD COLUMN guild_name TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE bot_personalities ADD COLUMN in_group INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE bot_personalities ADD COLUMN motivation TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE bot_personalities ADD COLUMN irl_json TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    for col in ("chat_points REAL", "play_points REAL DEFAULT 0",
                "last_play_at REAL", "decayed_at REAL"):
        try:
            conn.execute(f"ALTER TABLE relationships ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    import friendship  # local: friendship imports db
    friendship.migrate(conn, time.time())
    conn.commit()
    conn.close()


def get_memory(bot_name: str, player_name: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """SELECT role, content FROM messages
           WHERE bot_name = ? AND player_name = ?
           ORDER BY timestamp DESC LIMIT ?""",
        (bot_name, player_name, MEMORY_WINDOW * 2)
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def save_message(bot_name: str, player_name: str, role: str, content: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (bot_name, player_name, role, content) VALUES (?, ?, ?, ?)",
        (bot_name, player_name, role, content)
    )
    conn.commit()
    conn.close()


def get_relationship(bot_name: str, player_name: str) -> dict:
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM relationships WHERE bot_name = ? AND player_name = ?",
        (bot_name, player_name)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"bot_name": bot_name, "player_name": player_name, "familiarity": 0, "label": "stranger", "notes": ""}


def update_relationship(bot_name: str, player_name: str, familiarity_delta: int = 1):
    import friendship  # local: friendship imports db
    friendship.add_chat(bot_name, player_name, familiarity_delta)


def describe_relationship(rel: dict) -> str:
    fam = rel["familiarity"]
    if fam == 0:
        return "stranger — never talked before"
    elif fam < 5:
        return "you've seen them around a few times"
    elif fam < 15:
        return "acquaintance — you recognize the name"
    elif fam < 30:
        return "friendly — you'd group with them"
    elif fam < 50:
        return "friend — you like them, you'd help them out"
    else:
        return "good friend — one of your favorite people on the server"


def set_relationship_notes(bot_name: str, player_name: str, notes: str):
    conn = get_db()
    conn.execute("""
        INSERT INTO relationships (bot_name, player_name, notes)
        VALUES (?, ?, ?)
        ON CONFLICT(bot_name, player_name) DO UPDATE SET notes = excluded.notes
    """, (bot_name, player_name, notes))
    conn.commit()
    conn.close()


def upsert_memory(bot_name: str, kind: str, subject: str, content: str, weight: int = 1):
    conn = get_db()
    conn.execute("""
        INSERT INTO bot_memory (bot_name, kind, subject, content, weight)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(bot_name, kind, subject) DO UPDATE SET
            content = excluded.content,
            weight = excluded.weight,
            updated_at = CURRENT_TIMESTAMP
    """, (bot_name, kind, subject, content, weight))
    conn.commit()
    conn.close()


def get_memory_sheet(bot_name: str, kind: str | None = None) -> list[dict]:
    conn = get_db()
    if kind is None:
        rows = conn.execute(
            "SELECT * FROM bot_memory WHERE bot_name = ? ORDER BY updated_at DESC",
            (bot_name,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM bot_memory WHERE bot_name = ? AND kind = ? ORDER BY updated_at DESC",
            (bot_name, kind)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_messages(bot_name: str, limit: int = 12) -> list[dict]:
    """The bot's last `limit` messages across ALL players, chronological. Input for
    self-reflection (its recent activity, not one pairwise thread)."""
    conn = get_db()
    rows = conn.execute(
        """SELECT player_name, role, content FROM messages
           WHERE bot_name = ? ORDER BY timestamp DESC, id DESC LIMIT ?""",
        (bot_name, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def prune_memory(bot_name: str, kind: str, keep: int):
    """Keep only the `keep` most-recently-updated memories of `kind`; delete the rest.
    Bounds the self-sheet so it evolves (stale themes fade) instead of piling up."""
    conn = get_db()
    conn.execute("""
        DELETE FROM bot_memory
        WHERE bot_name = ? AND kind = ?
          AND rowid NOT IN (
            SELECT rowid FROM bot_memory
            WHERE bot_name = ? AND kind = ?
            ORDER BY updated_at DESC, rowid DESC LIMIT ?
          )
    """, (bot_name, kind, bot_name, kind, keep))
    conn.commit()
    conn.close()


def set_motivation(bot_name: str, motivation: str):
    conn = get_db()
    conn.execute("UPDATE bot_personalities SET motivation = ? WHERE bot_name = ?",
                 (motivation, bot_name))
    conn.commit()
    conn.close()


def delete_memory(bot_name: str, kind: str, subject: str):
    conn = get_db()
    conn.execute(
        "DELETE FROM bot_memory WHERE bot_name = ? AND kind = ? AND subject = ?",
        (bot_name, kind, subject))
    conn.commit()
    conn.close()


def prune_memory_by_weight(bot_name: str, kind: str, keep: int):
    """Keep the `keep` STRONGEST memories of `kind` (highest weight, ties broken by most
    recent), delete the rest. Identity prunes by conviction so a strongly-held trait
    survives a flurry of weak new ones (unlike prune_memory, which is recency-only)."""
    conn = get_db()
    conn.execute("""
        DELETE FROM bot_memory
        WHERE bot_name = ? AND kind = ?
          AND rowid NOT IN (
            SELECT rowid FROM bot_memory
            WHERE bot_name = ? AND kind = ?
            ORDER BY weight DESC, updated_at DESC, rowid DESC LIMIT ?
          )
    """, (bot_name, kind, bot_name, kind, keep))
    conn.commit()
    conn.close()


def get_who(bot_name: str) -> str:
    """The frozen IRL persona text seeded at creation; '' if the bot has no row yet."""
    conn = get_db()
    row = conn.execute(
        "SELECT who FROM bot_personalities WHERE bot_name = ?", (bot_name,)).fetchone()
    conn.close()
    return row["who"] if row else ""


def set_irl(bot_name: str, irl: dict) -> None:
    """Persist a composed IRL identity (R3) and the persona fields derived from it."""
    import json
    conn = get_db()
    conn.execute(
        "UPDATE bot_personalities SET irl_json = ?, who = ?, typing_style = ?, identity_id = ? "
        "WHERE bot_name = ?",
        (json.dumps(irl), irl["who"], irl["typing_style"], irl["archetype"], bot_name))
    conn.commit()
    conn.close()


def get_bot_names() -> list[str]:
    conn = get_db()
    rows = conn.execute("SELECT bot_name FROM bot_personalities").fetchall()
    conn.close()
    return [r["bot_name"] for r in rows]
