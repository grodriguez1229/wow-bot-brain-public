"""Driver state + stop conditions for the evolution optimizer loop.

The loop is Claude-in-the-loop (ScheduleWakeup-paced): each cycle I read the runlog, propose
ONE council.py edit (prompts/evolution_optimizer.md), run the K×D eval, judge in-session,
then call sim.optimize.evolution_cycle.run_cycle. This module holds the small pure helpers
(loop state + stop conditions) and the whitelist; the per-cycle choreography lives in
docs/evolution-optimizer-runbook.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from sim.optimize.runlog import CycleRecord

# Only council.py may change in a cycle (guard.out_of_scope enforces it). The day-plan,
# judge rubric, brain prompts, and identity injection are all out of scope this round.
COUNCIL_WHITELIST = {"council.py"}


def _trailing_reverts(records: list[CycleRecord]) -> int:
    n = 0
    for rec in reversed(records):
        if rec.kept:
            break
        n += 1
    return n


def should_stop(records: list[CycleRecord], *, max_cycles: int,
                max_consecutive_reverts: int) -> tuple[bool, str]:
    """Stop the loop when it stalls (too many reverts in a row) or hits the cycle cap.
    (Golden-anchor drift is enforced per-cycle by the gate itself, not here.)"""
    if len(records) >= max_cycles:
        return True, f"cycle cap reached ({max_cycles})"
    cr = _trailing_reverts(records)
    if cr >= max_consecutive_reverts:
        return True, f"{cr} consecutive reverts"
    return False, ""


def load_state(path) -> dict:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def save_state(path, state: dict) -> None:
    Path(path).write_text(json.dumps(state, indent=2))
