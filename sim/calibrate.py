"""Pure calibration checks: does Claude's scoring order scenes like the user's
buckets, and did it catch the planted gate violations? No I/O of its own beyond
what callers pass in. Consumes sim.judge.SceneScore.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sim.judge import SceneScore


@dataclass
class CalibrationReport:
    passed: bool
    inversions: list[tuple[str, str]] = field(default_factory=list)   # (good_id, bad_id)
    uncaught_violators: list[str] = field(default_factory=list)


def _cross_bucket_inversions(scores: dict[str, SceneScore],
                             buckets: dict[str, str]) -> list[tuple[str, str]]:
    goods = [sid for sid, b in buckets.items() if b == "good"]
    bads = [sid for sid, b in buckets.items() if b == "bad"]
    bad_pairs = []
    for g in goods:
        for b in bads:
            if scores[g].score <= scores[b].score:
                bad_pairs.append((g, b))
    return bad_pairs


def _uncaught_violators(scores: dict[str, SceneScore],
                        expected_violators: set[str]) -> list[str]:
    return [sid for sid in expected_violators if scores[sid].gate_passed]


def calibration_report(scores: dict[str, SceneScore],
                       buckets: dict[str, str],
                       expected_violators: set[str]) -> CalibrationReport:
    inversions = _cross_bucket_inversions(scores, buckets)
    uncaught = _uncaught_violators(scores, expected_violators)
    return CalibrationReport(
        passed=(not inversions and not uncaught),
        inversions=inversions,
        uncaught_violators=uncaught,
    )


def noise_band(run_a: dict[str, SceneScore], run_b: dict[str, SceneScore]) -> float:
    """Largest per-scene |score difference| across two scoring passes of one set.

    This is the judge's intrinsic scatter; step 4's promotion margin must exceed it.
    """
    return max(abs(run_a[sid].score - run_b[sid].score) for sid in run_a)
