"""Score schema + scoring math for the judge.

The judge itself is Claude executing prompts/judge.md in-session (manual-first);
this module is the pure, tested data layer its output is parsed into. No network,
no LLM here. Mirrors sim/transcript.py.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

# The five scored dimensions, in canonical order (ties in weakest_dimension
# resolve to the earliest). The lore/level "gate" is separate, not listed here.
DIMENSIONS = ["intentions", "turn_taking", "continuity", "initiative", "voice"]

GATE_CAP = 2.0


def score_from_dimensions(dims: dict[str, int], gate_passed: bool) -> float:
    """Mean of the five scored dimensions, capped at GATE_CAP on a gate violation."""
    base = mean(dims[d] for d in DIMENSIONS)
    if not gate_passed:
        return min(base, GATE_CAP)
    return float(base)


def weakest_dimension(dims: dict[str, int]) -> str:
    """The lowest-scoring dimension (ties resolve to canonical order)."""
    return min(DIMENSIONS, key=lambda d: dims[d])


@dataclass
class SceneScore:
    scene_id: str
    dimensions: dict[str, int]
    gate_passed: bool
    gate_violation: str | None
    score: float
    diagnosis: str
    weakest_dimension: str
    set_version: str = "v1"

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path) -> "SceneScore":
        return cls(**json.loads(Path(path).read_text()))
