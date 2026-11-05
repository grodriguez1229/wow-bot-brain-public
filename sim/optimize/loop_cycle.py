"""Driver helpers for the self-improving /loop.

The loop is **Claude-in-the-loop**: each wake, the `/loop` session (Claude) performs
one cycle by following `prompts/optimizer.md`, using the helpers here. Scoring is done
by Claude in-session (the judge is manual-first), so it is NOT a function call inside an
autonomous loop — these helpers cover only the mechanical, testable parts. The verified
manual run in the plan's Task 9 is the integration test for `regen_eval`.

Per-cycle sequence the /loop session follows:
  1. Read the lowest-scoring eval transcripts + the current config; make ONE whitelisted
     edit per `prompts/optimizer.md`.
  2. Guard: ``out_of_scope(git_changed_paths(), ALLOWED_PATHS)`` must be empty, else
     ``git checkout -- .`` and skip (the edit strayed outside the whitelist).
  3. Restart the experiment brain on a FRESH DB (``experiment_brain.start_experiment_brain``)
     so the edited config loads, then ``regen_eval(...)`` to regenerate the eval scenes.
  4. Claude scores the regenerated eval scenes against `prompts/judge.md` -> candidate
     eval mean; re-score the 8 golden anchors (fixed transcripts) for the drift check.
  5. Short-circuit: only if the candidate clears the cheap clauses (eval gain > M, no new
     lore failures, anchors within M) does Claude regenerate + score the held-out pool.
     Otherwise pass ``candidate_heldout_mean = baseline_heldout_mean + 1e-3`` so the
     held-out clause stays neutral and the real failing clause is the only logged reason.
  6. ``cycle.finalize(...)`` runs the gate and commits-or-reverts, appending a CycleRecord.
  7. ``should_stop(read_records(runlog))`` -> stop the loop on convergence; also stop on a
     finalize reason of ``"golden-anchor drift"`` (self-deception tripwire).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from sim.optimize.runlog import CycleRecord


def should_stop(records: list[CycleRecord], k: int = 8) -> bool:
    """True when the last k cycles all reverted (converged / plateaued)."""
    if len(records) < k:
        return False
    return all(not r.kept for r in records[-k:])


def git_changed_paths() -> list[str]:
    """Paths with unstaged changes in the working tree (for the whitelist guard)."""
    return subprocess.check_output(["git", "diff", "--name-only"]).decode().split()


def regen_eval(manifest_path: str, out_dir: str,
               brain_url: str = "http://localhost:5001",
               pool: str = "eval",
               memory_fixture: str | None = None,
               brain_db_path: str = "/tmp/wbb-exp.db") -> list[str]:
    """Regenerate the chosen pool's scenes with the CURRENT (candidate) config.

    The caller must have (re)started a fresh-DB experiment brain first so the edited
    config is loaded. Returns the written scene file paths. Mechanical; the plan's
    Task 9 manual run is its integration test.

    When `memory_fixture` is given, the brain's DB (`brain_db_path`) is seeded with
    that fixed relationship state before generation, so scored runs are comparable;
    default None preserves prior behavior. Lazy import keeps module import cheap.
    """
    if memory_fixture:
        from sim.memory_fixture import load_memory_fixture
        load_memory_fixture(memory_fixture, db_path=brain_db_path)
    from sim import scenes
    from sim.brain_client import BrainClient
    from sim.scene_runner import run_scene
    m = json.loads(Path(manifest_path).read_text())
    spec_by_base = {sp.scene_id: sp for sp in scenes.all_specs()}
    brain = BrainClient(base_url=brain_url)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for sid in m[pool]:
        base, seed = sid.rsplit("-s", 1)
        sp = spec_by_base[base]
        sc = run_scene(brain=brain, scene_id=sid, location=sp.location, channel=sp.channel,
                       bots=list(sp.bots), player=sp.player, turns=sp.turns, seed=int(seed))
        p = out / f"{sid}.json"
        sc.save(p)
        paths.append(str(p))
    return paths
