"""Pure mapping from a bot's motivation (+ hard permissions) to capability tokens.

A capability token gates a behavior the brain may offer/encourage. Hard permissions
overlay the motivation: guild_invite is granted ONLY when the bot actually holds
guild-invite rank (mirrors the engine's GR_RIGHT_INVITE), regardless of motivation.
"""
from __future__ import annotations

MOTIVATIONS = ["gold_maker", "dungeon_seeker", "guild_recruiter",
               "helper_social", "world_explorer", "farmer"]

_BASE: dict[str, set[str]] = {
    "gold_maker": {"sell_goods"},
    "dungeon_seeker": {"party_recruit"},
    "guild_recruiter": set(),      # guild_invite added only with rank
    "helper_social": {"help"},
    "world_explorer": {"explore"},
    "farmer": {"farm"},
}


def capabilities(motivation: str, *, can_guild_invite: bool = False) -> set[str]:
    caps = set(_BASE.get(motivation, set()))
    caps.add("party_invite")  # every bot can invite you to a party if you ask
    if motivation == "guild_recruiter" and can_guild_invite:
        caps.add("guild_invite")
    return caps
