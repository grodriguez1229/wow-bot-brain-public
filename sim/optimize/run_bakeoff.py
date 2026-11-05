"""One-shot Phase A driver: for each candidate model, start a fresh-DB experiment brain
on that model, regenerate the 16 eval scenes, and record per-scene generation latency.

Scoring (Claude-as-judge) happens afterward by reading the saved scenes; this script only
produces scenes + latencies. Run from the repo root with the venv python.
"""
import json
import os
import time
from pathlib import Path

from sim.optimize.bakeoff import timed_regen
from sim.optimize.experiment_brain import start_experiment_brain, stop_experiment_brain

MODELS = ["qwen3.5:9b", "gemma4:latest", "mistral-small:22b"]
MANIFEST = "eval/optimizer/manifest.json"
OUT_ROOT = "/tmp/wbb-bakeoff"
SUMMARY = "/tmp/wbb-bakeoff/latency.json"


def slug(model: str) -> str:
    return model.replace(":", "_").replace(".", "_").replace("/", "_")


def main() -> None:
    results = {}
    for model in MODELS:
        os.environ["WBB_OLLAMA_MODEL"] = model
        print(f"\n=== {model}: starting fresh brain ===", flush=True)
        proc = start_experiment_brain()
        try:
            out_dir = f"{OUT_ROOT}/{slug(model)}/scenes"
            t0 = time.time()
            paths, sps = timed_regen(MANIFEST, out_dir, pool="eval")
            print(f"{model}: {len(paths)} scenes, {sps:.2f}s/scene, "
                  f"{time.time()-t0:.0f}s total", flush=True)
            results[model] = {"scenes": len(paths), "seconds_per_scene": round(sps, 2),
                              "out_dir": out_dir}
        finally:
            stop_experiment_brain(proc)
            time.sleep(2)  # let :5001 free before the next bind
    Path(SUMMARY).parent.mkdir(parents=True, exist_ok=True)
    Path(SUMMARY).write_text(json.dumps(results, indent=2))
    print(f"\nwrote {SUMMARY}\n{json.dumps(results, indent=2)}", flush=True)


if __name__ == "__main__":
    main()
