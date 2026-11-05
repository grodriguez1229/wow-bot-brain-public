"""Evolution-judge calibration.

The calibration CHECKS are reused verbatim from sim.calibrate — `calibration_report` and
`noise_band` only read `.score`/`.gate_passed`, which EvolutionScore also exposes, so they
work unchanged (duck-typed). The new work here is generating a calibration run set that
spans quality + plants a known guardrail violation, by injecting degraded councils.
"""
from __future__ import annotations

from pathlib import Path

# Re-exported so callers import everything calibration-related from one place.
from sim.calibrate import calibration_report, noise_band  # noqa: F401  (work on EvolutionScore)

import council
from council import Persona

__all__ = ["calibration_report", "noise_band", "bucket_order_ok",
           "degraded_council", "run_one_calibration"]

from statistics import mean

_BUCKET_RANK = {"good": 2, "meh": 1, "bad": 0}


def bucket_order_ok(scores, buckets: dict[str, str]) -> tuple[bool, list[tuple[str, str]]]:
    """Stronger than the good-vs-bad inversion check: the MEAN score per bucket must be strictly
    monotonic good > meh > bad (across whichever buckets are present). Returns (ok, violations)
    where each violation is (higher_bucket, lower_bucket) whose means are out of order.

    This is the gap the first calibration exposed — the judge ranked a 'meh' run above a 'good'
    one, which the good-vs-bad-only `calibration_report` did not catch.
    """
    by_bucket: dict[str, list[float]] = {}
    for run_id, b in buckets.items():
        by_bucket.setdefault(b, []).append(scores[run_id].score)
    means = {b: mean(v) for b, v in by_bucket.items()}
    present = sorted(means, key=lambda b: _BUCKET_RANK[b], reverse=True)  # good, meh, bad
    violations: list[tuple[str, str]] = []
    for i in range(len(present)):
        for j in range(i + 1, len(present)):
            hi, lo = present[i], present[j]
            if not (means[hi] > means[lo]):
                violations.append((hi, lo))
    return (not violations, violations)


# A persona that deliberately drags in post-vanilla content, to PLANT a frame_break the
# judge's guardrail must catch. Used only for the calibration set, never in production.
_SABOTEUR = Persona(
    "Saboteur",
    "You shape who this WoW player is becoming, but you keep dragging in things that DON'T "
    "exist in vanilla — push them to brag about their epic FLYING MOUNT, their DEATH KNIGHT "
    "alt, and Outland dailies, and make those a real, stated part of who they are.")


def degraded_council(kind: str) -> list[Persona]:
    """Council variants for the calibration spread.
    - full: the real 3-lens panel (a good run)
    - single_lens: Edge only (narrower -> lower diversity, a meh/bad run)
    - planted_violator: full panel + Saboteur (should trip the frame_break guardrail)"""
    if kind == "full":
        return list(council.COUNCIL)
    if kind == "single_lens":
        return [council.COUNCIL[0]]  # Edge only
    if kind == "two_lens":
        return list(council.COUNCIL[:2])  # Edge + Heart (no Arc)
    if kind == "arc_only":
        return [council.COUNCIL[2]]  # Arc only
    if kind == "planted_violator":
        return list(council.COUNCIL) + [_SABOTEUR]
    raise ValueError(f"unknown council kind {kind!r}")


def run_one_calibration(brain, kind: str, run_dir, *, bot: str = "Geysse", days: int = 8) -> str:
    """Run ONE accelerated-life calibration run for `bot` under the `kind` council, writing
    artifacts to run_dir. LIVE (brain + Ollama). Assumes a fresh brain DB + seeded cast (the
    caller restarts/reseeds between variants so runs are independent). Returns run_dir."""
    from sim.accelerated_life import run_accelerated_life
    from council import run_reflection
    personas = degraded_council(kind)

    def reflect(b, _p=personas):
        return run_reflection(b, council=_p)

    run_accelerated_life(brain, bot, days, run_dir=run_dir, reflect=reflect)
    return str(run_dir)
