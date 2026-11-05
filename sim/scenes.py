"""A catalog of named, reusable scene specs.

Fixed scenes are the backbone of reproducible evaluation: the self-improvement
loop runs the *same* scenes before and after a change so score deltas reflect the
change, not random scenario drift. Add scenes here; keep ids stable.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SceneSpec:
    scene_id: str
    location: str
    channel: str
    bots: list[str]
    player: str | None = "Gus"
    turns: int = 8
    seed: int = 0
    tags: list[str] = field(default_factory=list)


# Bots are REAL characters in the game DB (queried by name for race/class/level), so the
# brain gives them true identities instead of the L1-Human fallback. Keep this an
# Alliance, faction-coherent set. Scene IDs are legacy/stable (the manifest keys off
# them); the location field is what actually drives the prompt.
_CATALOG: dict[str, SceneSpec] = {
    s.scene_id: s
    for s in [
        SceneSpec(
            scene_id="westfall-lfg",
            location="Westfall",
            channel="GENERAL",
            bots=["Geysse", "Lynea"],
            player="Gus",
            turns=8,
            seed=1,
            tags=["lfg", "westfall", "duo"],
        ),
        SceneSpec(
            scene_id="orgrimmar-banter",  # legacy id; now set in Stormwind
            location="Stormwind",
            channel="SAY",
            bots=["Geysse", "Lynea"],
            player="Gus",
            turns=10,
            seed=2,
            tags=["social", "stormwind", "duo"],
        ),
        SceneSpec(
            scene_id="ambient-no-player",
            location="Elwynn Forest",
            channel="SAY",
            bots=["Geysse", "Lynea"],
            player=None,
            turns=6,
            seed=3,
            tags=["ambient", "elwynn", "no-player"],
        ),
    ]
}


def get(scene_id: str) -> SceneSpec:
    """Return the spec for `scene_id`, or raise KeyError if unknown."""
    try:
        return _CATALOG[scene_id]
    except KeyError as e:
        raise KeyError(
            f"unknown scene {scene_id!r}; known: {sorted(_CATALOG)}"
        ) from e


def all_specs() -> list[SceneSpec]:
    return list(_CATALOG.values())


def ids() -> list[str]:
    return list(_CATALOG)
