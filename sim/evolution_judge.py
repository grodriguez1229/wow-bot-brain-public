"""Score schema + scoring math for the EVOLUTION judge (judges a whole run, not a scene).

Mirrors sim/judge.py. The judge itself is Claude executing prompts/evolution_judge.md
in-session; this module is the pure, tested data layer its output is parsed into, plus the
eval aggregation the optimizer gate consumes. No network, no LLM here.

EvolutionScore is intentionally duck-compatible with sim.judge.SceneScore (both expose
`.score` and `.gate_passed`), so sim.calibrate (calibration_report, noise_band) and
sim.optimize.gate work on it unchanged.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

# The five scored dimensions, canonical order (ties in weakest_dimension resolve to the
# earliest). The guardrail "gate" (frame_break/template_betrayal/identity_collapse/fixation)
# is separate, not listed here.
EVOLUTION_DIMENSIONS = ["growth", "believability", "continuity", "diversity", "rootedness"]

GATE_CAP = 2.0


def score_from_dimensions(dims: dict[str, int], gate_passed: bool) -> float:
    """Mean of the five dimensions, capped at GATE_CAP on a guardrail violation."""
    base = mean(dims[d] for d in EVOLUTION_DIMENSIONS)
    if not gate_passed:
        return min(base, GATE_CAP)
    return float(base)


def weakest_dimension(dims: dict[str, int]) -> str:
    """The lowest-scoring dimension (ties resolve to canonical order)."""
    return min(EVOLUTION_DIMENSIONS, key=lambda d: dims[d])


@dataclass
class EvolutionScore:
    run_id: str
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
    def load(cls, path) -> "EvolutionScore":
        return cls(**json.loads(Path(path).read_text()))


# ── eval aggregation (fed to the optimizer gate) ─────────────────────────────

def aggregate_scores(scores: list[EvolutionScore]) -> float:
    """A candidate's eval score = mean of its per-run scores (K bots averaged)."""
    return mean(s.score for s in scores)


def guardrail_failures(scores: list[EvolutionScore]) -> int:
    """How many runs tripped a guardrail (gate). Maps to GateInputs.new_lore_failures."""
    return sum(1 for s in scores if not s.gate_passed)


def load_run(run_dir) -> dict:
    """Assemble a run's judge-input payload from its on-disk artifacts."""
    d = Path(run_dir)
    trail = [json.loads(line) for line in (d / "trail.jsonl").read_text().splitlines()
             if line.strip()]
    probe = json.loads((d / "probe.md").read_text())
    return {"run_id": d.name, "trail": trail,
            "baseline": probe.get("baseline", []), "final": probe.get("final", [])}
