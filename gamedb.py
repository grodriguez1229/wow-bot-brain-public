import pymysql
from config import MYSQL_CONFIG, RACE_NAMES, CLASS_NAMES, GENDER_NAMES, FACTION_FOR_RACE


def lookup_bot_from_game_db(bot_name: str) -> dict | None:
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT race, class, level, gender FROM characters WHERE name = %s LIMIT 1",
                (bot_name,)
            )
            row = cur.fetchone()
        conn.close()
        if not row:
            return None
        race_id, class_id, level, gender_id = row
        return {
            "race": RACE_NAMES.get(race_id, "Unknown"),
            "class_name": CLASS_NAMES.get(class_id, "Adventurer"),
            "level": level,
            "gender": GENDER_NAMES.get(gender_id, "unknown"),
            "faction": FACTION_FOR_RACE.get(race_id, "Neutral"),
        }
    except Exception as e:
        print(f"[warn] MySQL lookup failed for {bot_name}: {e}")
        return None


def lookup_bot_guild(bot_name: str) -> str:
    """Check if bot is in a guild."""
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT g.name FROM guild g
                JOIN guild_member gm ON g.guildid = gm.guildid
                JOIN characters c ON c.guid = gm.guid
                WHERE c.name = %s LIMIT 1
            """, (bot_name,))
            row = cur.fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception:
        return ""


_GR_RIGHT_INVITE = 0x04  # AzerothCore guild_rank.rights bit for inviting members


def lookup_guild_invite_right(bot_name: str) -> bool:
    """True if the bot is in a guild and its rank has the invite right."""
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gr.rights FROM characters c
                JOIN guild_member gm ON c.guid = gm.guid
                JOIN guild_rank gr ON gr.guildid = gm.guildid AND gr.rid = gm.rank
                WHERE c.name = %s LIMIT 1
            """, (bot_name,))
            row = cur.fetchone()
        conn.close()
        return bool(row and (int(row[0]) & _GR_RIGHT_INVITE))
    except Exception:
        return False
