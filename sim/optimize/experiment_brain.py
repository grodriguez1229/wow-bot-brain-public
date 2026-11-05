"""Start/stop the experiment brain on :5001 with a FRESH DB each apply.

A fresh DB is required because identities are copied into bot_personalities rows at
creation, so prompt/identity edits only take effect on a clean DB. This module is
mechanical (subprocess); only uvicorn_cmd is unit-tested, the rest is exercised live.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx


def uvicorn_cmd(port: int = 5001, db_path: str = "/tmp/wbb-exp.db") -> list[str]:
    # db_path goes through env (WBB_DB_PATH), not argv — see start_experiment_brain.
    return ["venv/bin/uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)]


def start_experiment_brain(port: int = 5001, db_path: str = "/tmp/wbb-exp.db",
                           log_path: str = "/tmp/wbb-exp-brain.log",
                           ready_timeout: float = 20.0) -> subprocess.Popen:
    """Delete any old DB, launch a fresh brain, block until it answers /docs."""
    Path(db_path).unlink(missing_ok=True)
    env = {**os.environ, "WBB_DB_PATH": db_path}
    log = open(log_path, "w")
    proc = subprocess.Popen(uvicorn_cmd(port, db_path), env=env, stdout=log, stderr=log)
    deadline = time.time() + ready_timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/docs", timeout=2).status_code == 200:
                return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"experiment brain did not become ready on :{port}")


def stop_experiment_brain(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
