"""One optimize cycle's mechanical half: gate a candidate and record the outcome.

The smart half (diagnose + edit source files) is done by Claude in the /loop before
calling finalize(). Here we only run the pure gate and commit-or-revert via injected
callbacks, so this is fully testable without git/Claude/Ollama.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sim.optimize.gate import GateInputs, GateDecision, evaluate_gate
from sim.optimize.runlog import CycleRecord, append_record


@dataclass
class CandidateResult:
    eval_mean: float
    heldout_mean: float
    new_lore_failures: int


def finalize(*, cycle: int, edit_summary: str, candidate: CandidateResult,
             baseline_eval_mean: float, baseline_heldout_mean: float,
             anchor_mean: float, anchor_frozen_mean: float, margin: float,
             runlog_path, commit: Callable[[str], str], revert: Callable[[], None]
             ) -> GateDecision:
    decision = evaluate_gate(GateInputs(
        baseline_eval_mean=baseline_eval_mean, candidate_eval_mean=candidate.eval_mean,
        baseline_heldout_mean=baseline_heldout_mean, candidate_heldout_mean=candidate.heldout_mean,
        new_lore_failures=candidate.new_lore_failures, anchor_mean=anchor_mean,
        anchor_frozen_mean=anchor_frozen_mean, margin=margin))
    if decision.keep:
        sha = commit(edit_summary)
    else:
        revert()
        sha = ""
    append_record(runlog_path, CycleRecord(
        cycle=cycle, edit_summary=edit_summary,
        baseline_eval_mean=baseline_eval_mean, candidate_eval_mean=candidate.eval_mean,
        heldout_delta=candidate.heldout_mean - baseline_heldout_mean,
        kept=decision.keep, reasons=decision.reasons, commit_sha=sha))
    return decision
