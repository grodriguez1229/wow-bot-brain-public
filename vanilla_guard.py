"""Post-vanilla term list (R8). Pure.

Guards the authored example bank and the LFG/TRADE ad templates: nothing from The
Burning Crusade or later (zones, races, classes, mechanics, materials) may appear in text
that the brain writes itself. Matching is case-insensitive on whole words/phrases.
Not a runtime filter on model output (that is R2, knowledge guard)."""
from __future__ import annotations

import re

BANNED_TERMS = (
    # expansions
    "burning crusade", "tbc", "wrath", "wotlk", "lich king", "cataclysm", "pandaria", "draenor",
    # TBC zones / cities / instances
    "outland", "hellfire", "zangarmarsh", "terokkar", "nagrand", "blade's edge", "netherstorm",
    "shadowmoon valley", "shattrath", "shatt", "quel'danas", "eversong", "silvermoon",
    "ghostlands", "azuremyst", "bloodmyst", "exodar", "karazhan", "kara", "gruul", "magtheridon",
    "serpentshrine", "ssc", "tempest keep", "black temple", "sunwell", "zul'aman", "auchindoun",
    "coilfang", "sethekk", "shadow labs", "mechanar", "botanica", "arcatraz", "slave pens",
    "underbog", "steamvault", "mana tombs", "ramparts", "blood furnace", "shattered halls",
    "sunfury", "aldor", "scryers", "illidan",
    # WotLK zones / instances
    "northrend", "borean", "howling fjord", "dragonblight", "grizzly hills", "zul'drak",
    "sholazar", "storm peaks", "icecrown", "icc", "crystalsong", "wintergrasp", "ulduar",
    "utgarde", "the nexus", "violet hold", "gundrak", "halls of stone", "halls of lightning",
    "azjol", "ahn'kahet", "culling of stratholme", "trial of the crusader", "toc",
    "ruby sanctum", "obsidian sanctum", "vault of archavon", "argent tournament",
    # races / classes
    "draenei", "blood elf", "blood elves", "belf", "death knight", "dk", "dks",
    # mechanics that did not exist
    "ilvl", "item level", "gearscore", "lfd", "dungeon finder", "queue", "queued", "queueing",
    "achievement", "achievements", "daily", "dailies", "heroic", "heroics", "flying",
    "flyer", "flying mount", "dual spec", "glyph", "glyphs", "inscription", "jewelcrafting",
    "jc", "gem", "gems", "socket", "sockets", "badge of justice", "badges", "emblems",
    "transmog", "guild bank", "arena team", "2v2", "3v3", "5v5", "barber",
    # post-vanilla materials
    "netherweave", "frostweave", "fel iron", "adamantite", "khorium", "eternium",
    "saronite", "titanium", "cobalt", "primal", "mote of",
)

_BANNED_RE = re.compile(
    r"(?<![a-z0-9'])(?:" + "|".join(re.escape(t) for t in sorted(BANNED_TERMS, key=len, reverse=True))
    + r")(?![a-z0-9'])", re.IGNORECASE)


def find_banned(text: str) -> list[str]:
    """Return the post-vanilla terms found in `text` (lowercased), in order."""
    return [m.group(0).lower() for m in _BANNED_RE.finditer(text or "")]
