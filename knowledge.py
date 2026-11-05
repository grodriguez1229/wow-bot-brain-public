"""Level-appropriate game knowledge (R2). Pure.

A level -> (zones, dungeons, raids) table for vanilla. Two uses:
  build_knowledge_section: "where you've been" lines appended to the chat/tick system prompt
    (a positive list only; naming the forbidden content would prime a small model to say it).
  find_violations: runtime check on model output -- content far above the bot's level, or
    post-vanilla terms. Detection aliases are deliberately distinctive: "strat", "temple",
    "library", "DM", "ST" are ordinary words or ambiguous, so they are not matched."""
from __future__ import annotations

import re

from vanilla_guard import BANNED_TERMS

# (display name, detection aliases, lo, hi, faction or None)
ZONES = [
    ("Elwynn Forest", ("elwynn",), 1, 10, "Alliance"),
    ("Dun Morogh", ("dun morogh",), 1, 10, "Alliance"),
    ("Teldrassil", ("teldrassil",), 1, 10, "Alliance"),
    ("Durotar", ("durotar",), 1, 10, "Horde"),
    ("Mulgore", ("mulgore",), 1, 10, "Horde"),
    ("Tirisfal Glades", ("tirisfal",), 1, 10, "Horde"),
    ("Westfall", ("westfall",), 10, 20, "Alliance"),
    ("Loch Modan", ("loch modan",), 10, 20, "Alliance"),
    ("Darkshore", ("darkshore",), 10, 20, "Alliance"),
    ("The Barrens", ("barrens",), 10, 25, "Horde"),
    ("Silverpine Forest", ("silverpine",), 10, 20, "Horde"),
    ("Redridge Mountains", ("redridge",), 15, 25, "Alliance"),
    ("Stonetalon Mountains", ("stonetalon",), 15, 27, None),
    ("Ashenvale", ("ashenvale",), 18, 30, None),
    ("Duskwood", ("duskwood",), 18, 30, "Alliance"),
    ("Wetlands", ("wetlands",), 20, 30, "Alliance"),
    ("Hillsbrad Foothills", ("hillsbrad", "southshore", "tarren mill"), 20, 30, None),
    ("Thousand Needles", ("thousand needles",), 25, 35, None),
    ("Alterac Mountains", ("alterac mountains",), 30, 40, None),
    ("Arathi Highlands", ("arathi highlands",), 30, 40, None),
    ("Desolace", ("desolace",), 30, 40, None),
    ("Stranglethorn Vale", ("stranglethorn", "stv", "booty bay"), 30, 45, None),
    ("Dustwallow Marsh", ("dustwallow", "theramore"), 35, 45, None),
    ("Badlands", ("badlands",), 35, 45, None),
    ("Swamp of Sorrows", ("swamp of sorrows",), 35, 45, None),
    ("Feralas", ("feralas",), 40, 50, None),
    ("The Hinterlands", ("hinterlands",), 40, 50, None),
    ("Tanaris", ("tanaris", "gadgetzan"), 40, 50, None),
    ("Searing Gorge", ("searing gorge",), 43, 50, None),
    ("Azshara", ("azshara",), 45, 55, None),
    ("Blasted Lands", ("blasted lands",), 45, 55, None),
    ("Un'Goro Crater", ("un'goro", "ungoro"), 48, 55, None),
    ("Felwood", ("felwood",), 48, 55, None),
    ("Burning Steppes", ("burning steppes",), 50, 58, None),
    ("Western Plaguelands", ("western plaguelands", "wpl"), 51, 58, None),
    ("Eastern Plaguelands", ("eastern plaguelands", "epl"), 53, 60, None),
    ("Winterspring", ("winterspring", "everlook"), 53, 60, None),
    ("Deadwind Pass", ("deadwind",), 55, 60, None),
    ("Silithus", ("silithus",), 55, 60, None),
]

DUNGEONS = [
    ("Ragefire Chasm", ("ragefire", "rfc", "bazzalan"), 13, 18, "Horde"),
    ("Wailing Caverns", ("wailing caverns", "mutanus"), 17, 24, None),
    ("Deadmines", ("deadmines", "vancleef"), 17, 26, "Alliance"),
    ("Shadowfang Keep", ("shadowfang", "sfk", "arugal"), 22, 30, None),
    ("Blackfathom Deeps", ("blackfathom", "bfd", "aku'mai"), 24, 32, None),
    ("The Stockade", ("stockade", "stockades", "stocks", "thredd"), 24, 32, "Alliance"),
    ("Gnomeregan", ("gnomeregan", "gnomer", "thermaplugg"), 29, 38, None),
    ("Razorfen Kraul", ("razorfen kraul", "rfk", "charlga"), 29, 38, None),
    ("Scarlet Monastery", ("scarlet monastery", "sm", "whitemane"), 28, 45, None),
    ("Razorfen Downs", ("razorfen downs", "rfd", "amnennar"), 37, 46, None),
    ("Uldaman", ("uldaman", "archaedas"), 41, 51, None),
    ("Zul'Farrak", ("zul'farrak", "zf", "ukorz"), 44, 54, None),
    ("Maraudon", ("maraudon", "mara", "theradras"), 46, 55, None),
    ("Sunken Temple", ("sunken temple", "eranikus"), 50, 58, None),
    ("Blackrock Depths", ("blackrock depths", "brd", "thaurissan"), 52, 60, None),
    ("Lower Blackrock Spire", ("lower blackrock spire", "lbrs", "wyrmthalak"), 55, 60, None),
    ("Upper Blackrock Spire", ("upper blackrock spire", "ubrs", "drakkisath"), 58, 60, None),
    ("Dire Maul", ("dire maul", "gordok"), 56, 60, None),
    ("Stratholme", ("stratholme", "baron run", "rivendare"), 58, 60, None),
    ("Scholomance", ("scholomance", "scholo", "gandling"), 58, 60, None),
]

FINAL_BOSSES: dict[str, str] = {
    "Ragefire Chasm": "Bazzalan",
    "Wailing Caverns": "Mutanus the Devourer",
    "Deadmines": "Edwin VanCleef",
    "Shadowfang Keep": "Archmage Arugal",
    "Blackfathom Deeps": "Aku'mai",
    "The Stockade": "Bazil Thredd",
    "Gnomeregan": "Mekgineer Thermaplugg",
    "Razorfen Kraul": "Charlga Razorflank",
    "Scarlet Monastery": "High Inquisitor Whitemane",
    "Razorfen Downs": "Amnennar the Coldbringer",
    "Uldaman": "Archaedas",
    "Zul'Farrak": "Chief Ukorz Sandscalp",
    "Maraudon": "Princess Theradras",
    "Sunken Temple": "Shade of Eranikus",
    "Blackrock Depths": "Emperor Dagran Thaurissan",
    "Lower Blackrock Spire": "Overlord Wyrmthalak",
    "Upper Blackrock Spire": "General Drakkisath",
    "Dire Maul": "King Gordok",
    "Stratholme": "Baron Rivendare",
    "Scholomance": "Darkmaster Gandling",
}

RAIDS = [
    ("Molten Core", ("molten core", "mc", "ragnaros"), 60, 60, None),
    ("Onyxia's Lair", ("onyxia", "ony"), 60, 60, None),
    ("Zul'Gurub", ("zul'gurub", "zg", "hakkar"), 60, 60, None),
    ("Blackwing Lair", ("blackwing lair", "bwl", "nefarian", "nef"), 60, 60, None),
    ("Ahn'Qiraj", ("ahn'qiraj", "aq20", "aq40", "aq", "c'thun", "cthun"), 60, 60, None),
    ("Naxxramas", ("naxxramas", "naxx", "kel'thuzad"), 60, 60, None),
]

# Endgame-only concepts, matched like content; lo is when a player starts caring.
CONCEPTS = [
    ("attunement", ("attunement", "attuned"), 55, 60, None),
    ("tier sets", ("tier 1", "tier 2", "t1", "t2", "t3"), 60, 60, None),
]

# How far above its level a bot may talk about something (heard of it, heading there next).
SLACK = {"zone": 12, "dungeon": 8, "raid": 8, "concept": 8}

# The authored-text guard (vanilla_guard) is strict; at runtime these words are ordinary
# vanilla or real-life usage: Heroic Strike, flight paths, BG queues, the druid spell Wrath,
# the warlock spell Hellfire, Warcraft 3 lore, "my daily walk", a power socket.
RUNTIME_EXEMPT = {"queue", "queued", "queueing", "flying", "flyer", "heroic", "daily", "wrath",
                  "hellfire", "illidan", "draenor", "achievement", "socket", "badges", "primal"}
RUNTIME_EXTRA = ("daily quest", "daily quests", "hellfire peninsula", "heroic mode",
                 "heroic dungeon", "heroic dungeons")


def _alias_re(terms) -> re.Pattern:
    return re.compile(
        r"(?<![a-z0-9'])(?:" + "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
        + r")(?![a-z0-9'])", re.IGNORECASE)


_POSTVANILLA_RE = _alias_re([t for t in BANNED_TERMS if t not in RUNTIME_EXEMPT] + list(RUNTIME_EXTRA))

# alias -> (canonical name, min level at which it's fair game)
_GATED: dict[str, tuple[str, int]] = {}
for _kind, _table in (("zone", ZONES), ("dungeon", DUNGEONS), ("raid", RAIDS), ("concept", CONCEPTS)):
    for _name, _aliases, _lo, _hi, _fac in _table:
        for _a in _aliases:
            _GATED[_a] = (_name, _lo - SLACK[_kind])
_GATED_RE = _alias_re(_GATED)


def find_postvanilla(text: str) -> list[str]:
    """Post-vanilla terms in model output, lowercased, in order."""
    return [m.group(0).lower() for m in _POSTVANILLA_RE.finditer(text or "")]


def find_violations(text: str, level: int, *, allowed_from: str = "") -> list[str]:
    """Content `text` mentions that a level-`level` character shouldn't talk about, plus any
    post-vanilla terms. Content the other person brought up (`allowed_from`) is exempt, so a
    level 20 can answer "you been to MC?" with "never been to MC"."""
    allowed = {_GATED[m.group(0).lower()][0] for m in _GATED_RE.finditer(allowed_from or "")}
    out = []
    for m in _GATED_RE.finditer(text or ""):
        name, min_level = _GATED[m.group(0).lower()]
        if level < min_level and name not in allowed:
            out.append(m.group(0).lower())
    return out + find_postvanilla(text)


def _fits(faction: str | None, entry_faction: str | None) -> bool:
    return entry_faction is None or faction is None or entry_faction == faction


def _nearest(table, level: int, faction: str | None, *, ahead: int, behind: int, cap: int) -> list[str]:
    rows = [(name, lo, hi) for name, _a, lo, hi, fac in table
            if _fits(faction, fac) and lo <= level + ahead and hi >= level - behind]
    rows.sort(key=lambda r: abs((r[1] + r[2]) / 2 - level))
    return [r[0] for r in rows[:cap]]


def build_knowledge_section(level: int, faction: str | None) -> str:
    """'Where you've been' block for the system prompt: zones and dungeons near the bot's
    level (its faction's, plus contested), raids once a bot may talk about them."""
    zones = _nearest(ZONES, level, faction, ahead=2, behind=8, cap=6)
    dungeons = _nearest(DUNGEONS, level, faction, ahead=6, behind=10, cap=5)
    lines = [f"WHAT YOUR LEVEL {level} CHARACTER KNOWS:"]
    if zones:
        lines.append(f"- Zones you've been questing in: {', '.join(zones)}.")
    if dungeons:
        lines.append(f"- Dungeons at your level: {', '.join(dungeons)}.")
    if level >= RAIDS[0][2] - SLACK["raid"]:
        lines.append(f"- Raids: {', '.join(r[0] for r in RAIDS)}.")
    if level < 60:
        lines.append("- Anything higher level (later zones, dungeons, raids, attunements) you've "
                     "only heard of. You've never been there and don't know the details.")
    lines.append("- Only name real places from the game. Never make up a zone or dungeon name.")
    return "\n".join(lines)


# --- R9 grounding helpers -------------------------------------------------------------------
# Short names real players type. Used only for grounding (what a bot may mention given stored
# shared history), NOT for find_violations: "st"/"dm"/"wc" are too ambiguous to gate on level.
# "dm" is also Dire Maul; at the low levels where friends talk about it, Deadmines is the common
# meaning, so it maps to Deadmines. "blackrock spire" is ambiguous (lower/upper) -> Lower.
_GROUND_EXTRA = {
    "wc": "Wailing Caverns", "dm": "Deadmines", "vc": "Deadmines", "vancleef": "Deadmines",
    "the deadmines": "Deadmines", "ragefire chasm": "Ragefire Chasm",
    "sfk": "Shadowfang Keep", "rfk": "Razorfen Kraul", "rfd": "Razorfen Downs",
    "bfd": "Blackfathom Deeps", "zf": "Zul'Farrak", "st": "Sunken Temple",
    "the temple of atal'hakkar": "Sunken Temple", "temple of atal'hakkar": "Sunken Temple",
    "brd": "Blackrock Depths", "blackrock spire": "Lower Blackrock Spire",
    "lbrs": "Lower Blackrock Spire", "ubrs": "Upper Blackrock Spire",
    "strat": "Stratholme", "scholo": "Scholomance", "sm": "Scarlet Monastery",
    "mc": "Molten Core", "bwl": "Blackwing Lair", "zg": "Zul'Gurub", "ony": "Onyxia's Lair",
    "ulda": "Uldaman", "mara": "Maraudon", "gnomer": "Gnomeregan", "stocks": "The Stockade",
    "the stockade": "The Stockade", "the barrens": "The Barrens",
}
_GROUND: dict[str, str] = {a: v[0] for a, v in _GATED.items()}
_GROUND.update({a.lower(): n for a, n in _GROUND_EXTRA.items()})
_GROUND_RE = _alias_re(_GROUND)


def canonical_place(name: str) -> str | None:
    """Canonical ZONES/DUNGEONS/RAIDS name for a map/zone name or alias, else None."""
    m = _GROUND_RE.search(name or "")
    return _GROUND[m.group(0).lower()] if m else None


def mentioned_places(text: str) -> set[str]:
    """Canonical names of every place (or alias) mentioned in `text`."""
    return {_GROUND[m.group(0).lower()] for m in _GROUND_RE.finditer(text or "")}


def ungrounded_mentions(text: str, allowed_text: str) -> list[str]:
    """Canonical places `text` mentions that `allowed_text` (stored shared history) does not."""
    allowed = mentioned_places(allowed_text)
    out: list[str] = []
    for m in _GROUND_RE.finditer(text or ""):
        name = _GROUND[m.group(0).lower()]
        if name not in allowed and name not in out:
            out.append(name)
    return out


def zones_for_level(level: int, faction: str | None, slack: int = 3) -> list[str]:
    return [n for n, _a, lo, hi, fac in ZONES
            if _fits(faction, fac) and lo - slack <= level <= hi + slack]


def dungeons_for_level(level: int, faction: str | None) -> list[str]:
    return [n for n, _a, lo, hi, fac in DUNGEONS if _fits(faction, fac) and lo - 5 <= level <= hi]
