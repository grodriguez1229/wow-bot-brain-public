"""Scene-level transcript model for the offline eval substrate.

A Scene is an ordered, multi-speaker conversation (bots + optional synthetic
player) that the judge later scores for emergent social life.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Turn:
    idx: int
    speaker: str
    channel: str
    text: str
    actions: list = field(default_factory=list)
    ts: str = ""


@dataclass
class Scene:
    scene_id: str
    location: str
    channel: str
    participants: list
    turns: list = field(default_factory=list)

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path) -> "Scene":
        data = json.loads(Path(path).read_text())
        turns = [Turn(**t) for t in data.get("turns", [])]
        return cls(
            scene_id=data["scene_id"],
            location=data["location"],
            channel=data["channel"],
            participants=data["participants"],
            turns=turns,
        )
