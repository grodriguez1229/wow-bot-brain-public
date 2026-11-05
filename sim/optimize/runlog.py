"""Append-only JSONL audit trail: one CycleRecord per optimize cycle."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class CycleRecord:
    cycle: int
    edit_summary: str
    baseline_eval_mean: float
    candidate_eval_mean: float
    heldout_delta: float
    kept: bool
    reasons: list[str] = field(default_factory=list)
    commit_sha: str = ""


def append_record(path, rec: CycleRecord) -> None:
    with Path(path).open("a") as f:
        f.write(json.dumps(asdict(rec)) + "\n")


def read_records(path) -> list[CycleRecord]:
    p = Path(path)
    if not p.exists():
        return []
    return [CycleRecord(**json.loads(line)) for line in p.read_text().splitlines() if line.strip()]
