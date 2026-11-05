"""CLI: run one or all catalogued scenes against a (experiment) brain and save
transcripts.

Examples
--------
    # run every catalogued scene against the experiment brain on :5001
    python -m sim.run --all --brain-url http://localhost:5001 --out runs/$(date +%F)

    # run a single named scene
    python -m sim.run --scene westfall-lfg --brain-url http://localhost:5001

The brain it talks to is a sibling of the live C++ LlmBridge; point it at an
isolated experiment instance (its own WBB_DB_PATH) so eval never touches the
live game's memory.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sim import scenes
from sim.brain_client import BrainClient
from sim.scene_runner import run_scene


def run_one(spec: scenes.SceneSpec, brain, out_dir: Path):
    """Run a single scene spec and write its transcript.

    Returns (path, n_turns).
    """
    scene = run_scene(
        brain=brain,
        scene_id=spec.scene_id,
        location=spec.location,
        channel=spec.channel,
        bots=list(spec.bots),
        player=spec.player,
        turns=spec.turns,
        seed=spec.seed,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{spec.scene_id}.json"
    scene.save(path)
    return path, len(scene.turns)


def _selected(args) -> list[scenes.SceneSpec]:
    if args.all:
        return scenes.all_specs()
    if not args.scene:
        raise SystemExit("specify --scene <id> or --all (known: %s)" % scenes.ids())
    return [scenes.get(args.scene)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run offline bot scenes and save transcripts.")
    p.add_argument("--scene", help="scene id to run (see --list)")
    p.add_argument("--all", action="store_true", help="run every catalogued scene")
    p.add_argument("--list", action="store_true", help="list scene ids and exit")
    p.add_argument("--brain-url", default="http://localhost:5001",
                   help="experiment brain base URL (default: %(default)s)")
    p.add_argument("--out", default="runs", help="output directory (default: %(default)s)")
    p.add_argument("--timeout", type=float, default=60.0, help="per-request timeout seconds")
    args = p.parse_args(argv)

    if args.list:
        for sid in scenes.ids():
            print(sid)
        return 0

    try:
        specs = _selected(args)
    except KeyError as e:
        print(e, file=sys.stderr)
        return 2

    brain = BrainClient(base_url=args.brain_url, timeout=args.timeout)
    out_dir = Path(args.out)
    print(f"running {len(specs)} scene(s) against {args.brain_url} -> {out_dir}/")
    for spec in specs:
        path, n_turns = run_one(spec, brain, out_dir)
        print(f"  {spec.scene_id:24s} {n_turns:3d} turns -> {path}")
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
