#!/usr/bin/env bash
# Start wow-bot-brain sidecar
# Run once: sudo apt install python3.12-venv python3-pip

cd "$(dirname "$0")"

if [ ! -d venv ]; then
    echo "[setup] Creating virtualenv..."
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
fi

echo "[start] Launching wow-bot-brain on :5000"
export WBB_GUILD_ACTIONS="${WBB_GUILD_ACTIONS:-1}"
venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 --reload
