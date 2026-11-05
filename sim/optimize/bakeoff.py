import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from sim.optimize.loop_cycle import regen_eval  # noqa: E402  (re-exported so timed_regen is monkeypatchable)


@dataclass
class BakeoffRow:
    model: str
    eval_mean: float
    seconds_per_scene: float


def record_row(path: str, row: BakeoffRow) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(asdict(row)) + "\n")


def read_rows(path: str) -> list[BakeoffRow]:
    p = Path(path)
    if not p.exists():
        return []
    return [BakeoffRow(**json.loads(line))
            for line in p.read_text().splitlines() if line.strip()]


def pick_winner(rows: list[BakeoffRow], *, baseline_model: str,
                baseline_mean: float, margin: float,
                max_seconds_per_scene: float) -> str:
    """Highest-scoring model that clears the noise margin over the baseline AND is
    fast enough to be live-viable. Falls back to the baseline model if none qualify."""
    viable = [r for r in rows
              if r.eval_mean - baseline_mean > margin
              and r.seconds_per_scene <= max_seconds_per_scene]
    if not viable:
        return baseline_model
    return max(viable, key=lambda r: r.eval_mean).model


def timed_regen(manifest_path: str, out_dir: str,
                brain_url: str = "http://localhost:5001",
                pool: str = "eval") -> tuple[list[str], float]:
    """Regenerate a pool and return (paths, seconds_per_scene). The brain must already
    be running on the candidate model with a fresh DB."""
    start = time.perf_counter()
    paths = regen_eval(manifest_path, out_dir, brain_url=brain_url, pool=pool)
    elapsed = time.perf_counter() - start
    per_scene = elapsed / len(paths) if paths else 0.0
    return paths, per_scene
