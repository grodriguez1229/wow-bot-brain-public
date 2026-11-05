"""Whitelist guard: only these brain-config files may change in a cycle.

MVP excludes sim orchestration on purpose — editing the scene generator would let
the optimizer game its own eval. Tune the brain; keep the exam fixed.
"""
from __future__ import annotations

# Relative to repo root, matching `git diff --name-only` output.
ALLOWED_PATHS = {"prompts.py", "personality.py", "llm.py"}


def out_of_scope(changed_paths: list[str], allowed: set[str]) -> list[str]:
    """Return changed paths that are NOT in the whitelist (order preserved)."""
    return [p for p in changed_paths if p not in allowed]
