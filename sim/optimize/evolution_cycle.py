"""One evolution-optimizer cycle — the mechanical scaffold around the reused 4-clause gate.

The JUDGING and the council EDIT are in-session Claude steps (like the scene optimizer), so
this function takes the already-judged EvolutionScores and the edit summary, and handles the
deterministic rest: aggregate -> gate -> keep/revert -> log. keep/revert are injected
callables (tests pass stubs; the live loop passes git commit / git checkout).
"""
from __future__ import annotations

from sim.evolution_judge import aggregate_scores, guardrail_failures
from sim.optimize.gate import GateInputs, evaluate_gate
from sim.optimize.runlog import CycleRecord, append_record


def run_cycle(cycle_num, *, edit_summary,
              baseline_eval, candidate_eval,
              baseline_heldout, candidate_heldout,
              anchor_mean, anchor_frozen_mean, margin,
              runlog_path, keep, revert) -> CycleRecord:
    """Decide keep/revert for one candidate council edit and append a CycleRecord.

    *_eval / *_heldout are list[EvolutionScore]. Any guardrail failure in the candidate
    (eval or held-out) maps to GateInputs.new_lore_failures, so a council that produces a
    frame_break/identity_collapse/etc. is rejected even if its score went up.
    `keep()` should commit and return the sha; `revert()` should restore the baseline.
    """
    base_eval_mean = aggregate_scores(baseline_eval)
    cand_eval_mean = aggregate_scores(candidate_eval)
    base_heldout_mean = aggregate_scores(baseline_heldout)
    cand_heldout_mean = aggregate_scores(candidate_heldout)
    new_guardrail = guardrail_failures(candidate_eval) + guardrail_failures(candidate_heldout)

    decision = evaluate_gate(GateInputs(
        baseline_eval_mean=base_eval_mean, candidate_eval_mean=cand_eval_mean,
        baseline_heldout_mean=base_heldout_mean, candidate_heldout_mean=cand_heldout_mean,
        new_lore_failures=new_guardrail,
        anchor_mean=anchor_mean, anchor_frozen_mean=anchor_frozen_mean, margin=margin,
    ))

    sha = keep() if decision.keep else (revert() or "")

    rec = CycleRecord(
        cycle=cycle_num, edit_summary=edit_summary,
        baseline_eval_mean=base_eval_mean, candidate_eval_mean=cand_eval_mean,
        heldout_delta=cand_heldout_mean - base_heldout_mean,
        kept=decision.keep, reasons=decision.reasons, commit_sha=sha or "",
    )
    append_record(runlog_path, rec)
    return rec
