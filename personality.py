import json
import random
import time
from config import ROLE_FOR_CLASS
from capabilities import MOTIVATIONS
from db import get_db, set_motivation, set_irl
from gamedb import lookup_bot_from_game_db, lookup_bot_guild, lookup_guild_invite_right
from irl_identity import IRL_IDENTITIES, compose_identity  # noqa: F401  (re-exported)

# Moods used when the fleet IRL budget is spent: nothing that invites a real-life aside.
IN_GAME_MOODS = ["chill", "focused", "bored", "in a good mood", "a bit impatient",
                 "relaxed", "determined", "curious"]


def pick_goal_for_level(level: int, class_name: str) -> str:
    if level <= 10:
        return random.choice([
            "figure out where to go next",
            "get some better gear",
            "find the trainer and learn new abilities",
            "stop dying to everything lol",
            "make it to the next town",
            "find someone to group with for these hard quests",
        ])
    elif level <= 20:
        return random.choice([
            "run Deadmines or Wailing Caverns",
            "save up for new skills, theyre getting expensive",
            "get to level 20 for the next tier of abilities",
            "find a decent group for the dungeon nearby",
            "figure out what professions to take",
            "get enough money to actually afford abilities",
        ])
    elif level <= 30:
        return random.choice([
            "survive Stranglethorn Vale without getting ganked",
            "run Scarlet Monastery",
            "save up for a mount at 40",
            "find a good guild",
            f"figure out the best talent spec for {class_name}",
            "get through this level range, it feels so slow",
        ])
    elif level <= 40:
        return random.choice([
            "get my mount at 40, im so close",
            "run Scarlet Monastery Cathedral",
            "do Uldaman or Zul'Farrak",
            "farm some gold, im completely broke",
            "find a guild that actually raids",
            "push through to 40 for the mount",
        ])
    elif level <= 50:
        return random.choice([
            "run Maraudon or Sunken Temple",
            "start saving for epic mount (lol yeah right)",
            "get pre-raid BiS gear",
            "do BRD, theres so much stuff in there",
            "start the Onyxia attunement chain",
            "hit 60 already, this grind is real",
        ])
    elif level <= 58:
        return random.choice([
            "grind these last few levels to 60",
            "start running LBRS/UBRS for gear",
            "finish the Onyxia attunement",
            "run Stratholme for pre-raid gear",
            "find a raid guild thats still recruiting",
            "do Scholomance, need stuff from there",
        ])
    else:
        return random.choice([
            "get into Molten Core",
            "finish my pre-raid BiS set",
            "farm gold for epic mount or consumes",
            "get attuned for everything",
            "find a solid raid guild",
            "run UBRS for the last few upgrades",
            "do PvP for the blue set",
            "help guildies catch up so we can raid",
        ])


def pick_tick_activity(level: int, class_name: str, location: str, has_guild: bool,
                       bias_say: bool = False, motivation: str = "",
                       *, activity: str | None = None, target: str | None = None,
                       subzone: str | None = None, irl_ok: bool = True) -> dict:
    """Returns a tick prompt and suggested channel based on what the bot would naturally do.

    When `activity` names a grounded state (in_combat/traveling/resting/dead) the topic is
    shaped from that real state. When it is None or "idle", falls through to the goal-driven
    menu (legacy behavior)."""

    place = subzone or location or "somewhere"

    if activity == "in_combat":
        tgt = f" against {target}" if target else ""
        return {"channel": "SAY",
                "prompt": (f"You're in a fight{tgt} in {place}. Mutter a short in-character "
                           f"reaction to THIS fight — name the enemy, a close call, low health, "
                           f"the pull. One line — just react to the fight, no group-hunting.")}
    if activity == "traveling":
        return {"channel": "SAY",
                "prompt": (f"You're traveling through {place}. Say one short line about the road, "
                           f"where you're headed, or the scenery — not looking for a group. One line.")}
    if activity == "dead":
        return {"channel": "SAY",
                "prompt": (f"You just died in {place}. One short in-character reaction — the corpse "
                           f"run, what killed you, frustration. One line.")}
    if activity == "resting":
        aside = "banter, a real-life aside, an opinion, guild talk" if irl_ok else \
                "banter, an opinion about the game, guild talk — keep it about the game"
        return {"channel": "GENERAL",
                "prompt": (f"You're resting at an inn in {place}, taking a break. Say something "
                           f"social and relaxed — {aside}. Not an errand. One short line.")}

    activities = []

    # LFG messages — bots looking for groups (level-appropriate dungeons)
    if level >= 15:
        dungeons = []
        if level <= 25: dungeons = ["Deadmines", "Wailing Caverns", "Shadowfang Keep"]
        elif level <= 35: dungeons = ["Scarlet Monastery", "Gnomeregan", "Razorfen Kraul"]
        elif level <= 45: dungeons = ["Uldaman", "Zul'Farrak", "Maraudon"]
        elif level <= 55: dungeons = ["Sunken Temple", "BRD", "Stratholme", "Scholomance"]
        else: dungeons = ["UBRS", "LBRS", "Stratholme", "Scholomance", "DM"]
        if dungeons:
            dng = random.choice(dungeons)
            role = ROLE_FOR_CLASS.get(class_name, "dps")
            activities.append({
                "channel": "LFG",
                "prompt": f"Write a short LFG message for {dng}. You're a level {level} {class_name} ({role}). Keep it authentic — like 'LFG {dng} need tank and healer' or 'L{level} {class_name} LFG {dng} pst'. One line, abbreviations are fine.",
            })

    # Trade chat — buying/selling stuff
    if level >= 10:
        activities.append({
            "channel": "TRADE",
            "prompt": f"Write a short trade chat message. You're a level {level} {class_name}. Maybe WTB or WTS something level-appropriate, or offer a profession service. Like 'WTS 4x linen bags 5s each' or 'WTB wool cloth PST'. One line.",
        })

    # General chat — random banter, questions, server drama
    activities.append({
        "channel": "GENERAL",
        "prompt": f"Write a short general chat message. You're in {location}. Could be a question about quests, a random comment, complaining about something, asking for help, or just banter. Name a real thing in your zone. Avoid generic filler and made-up quest names. One line.",
    })

    # Say chat — talking to yourself or nearby people
    activities.append({
        "channel": "SAY",
        "prompt": f"You're in {location}. Mutter a short, specific reaction to what you're actually doing — name the mob, quest, or thing in front of you. Avoid generic filler. One line.",
    })

    # Banter / IRL bleed — NOT an errand. Breaks the LFG/WTS monotony with the
    # real person behind the keyboard: a real-life aside, an opinion, or a joke.
    if irl_ok:
        activities.append({
            "channel": "GENERAL",
            "prompt": ("Say something that ISN'T about quests, loot, or looking for a group. "
                       "Let the real person behind the keyboard show — a real life aside "
                       "(work, school, food, music, being tired), an opinion about the game, "
                       "a joke, or a reaction. One short casual line."),
        })

    # Guild chat — if they have a guild
    if has_guild:
        activities.append({
            "channel": "GUILD",
            "prompt": f"Write a short guild chat message. Could be asking guildies to run something, commenting on the game, or just casual banter. Like 'anyone wanna do SM?' or 'just hit 40 finally lol'. One line.",
        })

    # Per-motivation channel boosts (added on top of the baseline weights).
    boost = {
        "gold_maker": {"TRADE": 6},
        "dungeon_seeker": {"LFG": 6},
        "guild_recruiter": {"GUILD": 6},
        "helper_social": {"GENERAL": 5},
        "world_explorer": {"SAY": 6},
        "farmer": {"SAY": 6},
    }.get(motivation, {})

    weights = []
    for a in activities:
        ch = a["channel"]
        if bias_say and ch == "SAY":
            w = 5
        elif ch == "LFG":
            w = 3
        elif ch in ("TRADE", "GENERAL", "GUILD"):
            w = 2
        else:
            w = 1
        weights.append(w + boost.get(ch, 0))

    return random.choices(activities, weights=weights, k=1)[0]


def pick_mood(identity: dict, *, irl_ok: bool = True) -> str:
    if not irl_ok:
        return random.choice(IN_GAME_MOODS)
    return random.choice(identity["mood_pool"])


_GROUP_CLASSES = {"Warrior", "Paladin", "Priest", "Druid", "Shaman"}


def pick_motivation(class_name: str, level: int, has_guild: bool = False,
                    can_guild_invite: bool = False) -> str:
    """Game-state-weighted motivation pick. guild_recruiter only when the bot holds
    guild-invite rank (else weight 0). Uses the module `random` (seed in tests)."""
    w = {m: 1 for m in MOTIVATIONS}          # baseline variety
    w["gold_maker"] += 1
    w["helper_social"] += 1
    if class_name in _GROUP_CLASSES:
        w["dungeon_seeker"] += 3
    if level <= 15:
        w["world_explorer"] += 2
        w["farmer"] += 2
    if can_guild_invite:
        w["guild_recruiter"] += 4
    else:
        w["guild_recruiter"] = 0             # can't recruit without rank
    return random.choices(list(w), weights=list(w.values()), k=1)[0]


_personality_cache: dict = {}


# The stored level is a snapshot from first contact; bots keep leveling, and R2's knowledge
# guard and the level-derived goal need the real one. Re-read it from the game DB at most
# this often per bot.
LEVEL_TTL_S = 600
_level_checked: dict[str, float] = {}


def _refresh_level(bot_name: str, data: dict) -> None:
    now = time.monotonic()
    if now - _level_checked.get(bot_name, float("-inf")) < LEVEL_TTL_S:
        return
    _level_checked[bot_name] = now
    info = lookup_bot_from_game_db(bot_name)
    if not info or info["level"] == data["level"]:
        return
    print(f"[level] {bot_name} {data['level']} -> {info['level']}")
    data["level"] = info["level"]
    data["current_goal"] = pick_goal_for_level(info["level"], data["class_name"])
    conn = get_db()
    conn.execute("UPDATE bot_personalities SET level = ?, current_goal = ? WHERE bot_name = ?",
                 (data["level"], data["current_goal"], bot_name))
    conn.commit()
    conn.close()


def get_or_create_personality(bot_name: str) -> dict:
    if bot_name in _personality_cache:
        _refresh_level(bot_name, _personality_cache[bot_name])
        return _personality_cache[bot_name]

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM bot_personalities WHERE bot_name = ?", (bot_name,)
    ).fetchone()
    conn.close()

    if row:
        data = dict(row)
        raw = data.get("irl_json") or ""
        if raw:
            data["irl"] = json.loads(raw)
        else:
            irl = compose_identity(bot_name, data.get("identity_id"))
            set_irl(bot_name, irl)
            data.update(irl=irl, who=irl["who"], typing_style=irl["typing_style"],
                        identity_id=irl["archetype"], irl_json=json.dumps(irl))
        can_inv = lookup_guild_invite_right(bot_name)
        data["can_guild_invite"] = can_inv
        if not data.get("motivation"):
            data["motivation"] = pick_motivation(
                data["class_name"], data["level"],
                has_guild=bool(data.get("guild_name")), can_guild_invite=can_inv)
            set_motivation(bot_name, data["motivation"])
        _refresh_level(bot_name, data)
        _personality_cache[bot_name] = data
        return data

    game_info = lookup_bot_from_game_db(bot_name)
    _level_checked[bot_name] = time.monotonic()
    if not game_info:
        game_info = {
            "race": "Human", "class_name": "Adventurer",
            "level": 1, "gender": "unknown", "faction": "Alliance",
        }

    irl = compose_identity(bot_name)
    goal = pick_goal_for_level(game_info["level"], game_info["class_name"])
    guild = lookup_bot_guild(bot_name)
    can_inv = lookup_guild_invite_right(bot_name)
    motivation = pick_motivation(game_info["class_name"], game_info["level"],
                                 has_guild=bool(guild), can_guild_invite=can_inv)

    data = {
        "bot_name": bot_name,
        "race": game_info["race"],
        "class_name": game_info["class_name"],
        "level": game_info["level"],
        "gender": game_info["gender"],
        "faction": game_info["faction"],
        "identity_id": irl["archetype"],
        "who": irl["who"],
        "typing_style": irl["typing_style"],
        "irl": irl,
        "current_goal": goal,
        "guild_name": guild,
        "in_group": 0,
        "motivation": motivation,
        "can_guild_invite": can_inv,
    }

    conn = get_db()
    conn.execute("""
        INSERT OR IGNORE INTO bot_personalities
        (bot_name, race, class_name, level, gender, faction, identity_id, who, typing_style, current_goal, guild_name, in_group, motivation, irl_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        bot_name, data["race"], data["class_name"], data["level"],
        data["gender"], data["faction"], data["identity_id"],
        data["who"], data["typing_style"], data["current_goal"],
        data["guild_name"], data["in_group"], data["motivation"], json.dumps(irl),
    ))
    conn.commit()
    conn.close()

    _personality_cache[bot_name] = data
    print(f"[new person] {bot_name} = L{game_info['level']} {game_info['race']} {game_info['class_name']}, IRL: {irl['archetype']}, guild: {guild or 'none'}")
    return data
