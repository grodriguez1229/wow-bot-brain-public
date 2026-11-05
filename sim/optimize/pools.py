"""Load the three optimizer scene pools and guarantee they never overlap.

golden = drift ruler (never optimized against); eval = what candidates are scored
on; heldout = the anti-overfit gate. Overlap would let the loop train and grade on
the same scenes, so it is a hard error.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from sim.judge import SceneScore


class PoolsError(ValueError):
    pass


@dataclass
class Pools:
    golden: list[str]
    eval: list[str]
    heldout: list[str]
    golden_dir: str
    scenes_dir: str
    gate_margin: float
    set_version: str


def load_pools(manifest_path) -> Pools:
    m = json.loads(Path(manifest_path).read_text())
    p = Pools(golden=m["golden"], eval=m["eval"], heldout=m["heldout"],
              golden_dir=m["golden_dir"], scenes_dir=m["scenes_dir"],
              gate_margin=m["gate_margin"], set_version=m["set_version"])
    for a, b in (("golden", "eval"), ("eval", "heldout"), ("golden", "heldout")):
        overlap = set(getattr(p, a)) & set(getattr(p, b))
        if overlap:
            raise PoolsError(f"pools {a} and {b} overlap: {sorted(overlap)}")
    return p


def pool_mean(scores: dict[str, SceneScore], ids: list[str]) -> float:
    return float(mean(scores[i].score for i in ids))
