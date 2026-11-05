"""A seeded, deterministic stand-in for a real human player.

Seeds scenes with plausible 2005-WoW chatter so bots have something to react
to. Pure (no network) so orchestration tests stay fast and reproducible.
"""
from __future__ import annotations

import random

DUNGEONS = [
    "Deadmines", "Wailing Caverns", "SFK", "Scarlet Monastery", "Gnomeregan",
    "RFK", "Uldaman", "Zul'Farrak", "Maraudon", "SM Cath",
]
OPENERS = [
    "anyone lfg {dng}?",
    "wts linen cloth cheap pst",
    "where do i turn in the {loc} quests lol",
    "anyone know a good grind spot around here?",
    "wtb str food pst",
    "is {loc} alliance or horde side? im new",
    "lf healer for {dng}, almost full grp",
]
FOLLOWUPS = [
    "haha yeah",
    "nice, where u at?",
    "oh cool how long u been playin?",
    "lol same",
    "wanna group up?",
    "any of u know where the flight master is",
    "brb gettin food",
    "ok inv me then",
]


class SyntheticPlayer:
    def __init__(self, name: str = "Gus", seed: int = 0):
        self.name = name
        self._r = random.Random(seed)

    def opener(self, location: str) -> str:
        return self._r.choice(OPENERS).format(dng=self._r.choice(DUNGEONS), loc=location)

    def followup(self, history) -> str:
        return self._r.choice(FOLLOWUPS)
