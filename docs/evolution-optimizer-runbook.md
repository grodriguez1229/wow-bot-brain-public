# Evolution Optimizer — Runbook

How to run the evolution optimizer loop (Claude-in-the-loop, ScheduleWakeup-paced). Mirrors the
scene optimizer-run runbook. **Nothing here merges to master or touches the live `:5000` brain.**

## Prereqs
- Game DB up: `docker start ac-database`.
- Ollama reachable on `<ollama-host>:11434`.
- On branch `evolution-council`.
- The judge must be **calibrated** (see calibration package) before this is trusted; a
  pre-calibration run is "provisional" only.

## Start the experiment brain (fresh DB, self-reflect OFF, cast seeded)
```bash
cd ~/wow-bot-brain
PORT=5001; DB=/tmp/wbb-evo-opt.db
rm -f "$DB"
WBB_DB_PATH=$DB WBB_SELF_REFLECT=0 WBB_GUILD_ACTIONS=1 \
  setsid nohup venv/bin/uvicorn main:app --host 127.0.0.1 --port $PORT >/tmp/wbb-evo-opt.log 2>&1 &
# wait for ready, then seed the fixed cast:
WBB_DB_PATH=$DB venv/bin/python -c "from sim.memory_fixture import seed_cast; seed_cast('eval/evolution/fixtures/cast.json', db_path='$DB')"
```
**NEVER `pkill uvicorn`** (kills prod :5000, exit 144). Stop this one by its PID:
`kill $(ss -ltnp | grep ':5001' | grep -oP 'pid=\K[0-9]+' | head -1)`.

## One cycle (per prompts/evolution_optimizer.md)
1. Read `eval/evolution/optimizer/runlog.jsonl`; note the weakest dimension + diagnoses.
2. Make ONE `council.py` edit. Verify scope: `git diff --name-only` must be only `council.py`.
3. Run the eval — for each eval-cast bot (K=2: Geysse, Lynea) run D=8 days; restart+reseed the
   brain between bots so runs are independent:
   ```bash
   WBB_DB_PATH=$DB venv/bin/python -m sim.accelerated_life --bot Geysse --days 8 \
     --brain-url http://127.0.0.1:5001 --run optimizer/cN_geysse
   ```
   Also run the held-out bot (Tomaslin). Re-run the baseline council the same way for comparison
   (or reuse the prior baseline if council baseline is unchanged).
4. **Judge each run in-session** via `prompts/evolution_judge.md` (read its REPORT.md/trail/probe),
   emit the JSON, parse into `EvolutionScore`, derive score via `evolution_judge.score_from_dimensions`.
5. Call `evolution_cycle.run_cycle(...)` with the baseline/candidate eval + held-out scores, the
   frozen anchor mean, and the calibrated margin M. It commits (keep) or `git checkout`s (revert)
   and appends to the runlog. `keep` = `git commit` returning sha; `revert` = `git checkout -- council.py`.
6. Re-score the golden anchors; if `|anchor_mean - frozen| > M`, stop (judge drift).
7. `evolution_loop.should_stop(records, max_cycles=…, max_consecutive_reverts=8)` → stop or schedule
   the next wakeup (~12+ min/cycle).

## State / artifacts
- `eval/evolution/optimizer/runlog.jsonl` — one CycleRecord per cycle.
- `eval/evolution/optimizer/loop_state.json` — cycle counter, baseline mean, frozen anchor mean, M.
- Per-cycle run dirs under `eval/evolution/optimizer/`.

Promotion (merging a winning `council.py` to master / live) is always the user's explicit call.
