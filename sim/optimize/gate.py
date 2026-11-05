"""The promotion gate — the optimizer's pure safety core.

A candidate edit is kept only if ALL four clauses hold. This is the entire
"don't degrade / don't fool yourself" argument, in one tested function.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateInputs:
    baseline_eval_mean: float
    candidate_eval_mean: float
    baseline_heldout_mean: float
    candidate_heldout_mean: float
    new_lore_failures: int
    anchor_mean: float
    anchor_frozen_mean: float
    margin: float  # M


@dataclass
class GateDecision:
    keep: bool
    reasons: list[str] = field(default_factory=list)  # failed clauses; empty == keep


def evaluate_gate(i: GateInputs) -> GateDecision:
    reasons: list[str] = []
    if not (i.candidate_eval_mean - i.baseline_eval_mean > i.margin):
        reasons.append("eval gain <= margin")
    if not (i.candidate_heldout_mean > i.baseline_heldout_mean):
        reasons.append("held-out regressed")
    if i.new_lore_failures > 0:
        reasons.append("new lore-gate failures")
    if abs(i.anchor_mean - i.anchor_frozen_mean) > i.margin:
        reasons.append("golden-anchor drift")
    return GateDecision(keep=not reasons, reasons=reasons)
