# Live chatter check — 2026-10-14 (handoff brief)

Handed off from a desktop Claude session. Untracked on purpose; fold the findings into the
R3/R4 spec and delete or commit this file as you see fit.

## State as of handoff
- **Running now:** AzerothCore (ac-database, ac-authserver, ac-worldserver) via
  `docker compose up -d ac-database ac-db-import ac-client-data-init ac-authserver ac-worldserver`
  in `~/azerothcore/azerothcore-wotlk`. Worldserver image is from 2026-07-16 22:28, so it already
  includes the R1 payload commit in mod-playerbots (`c0bddfe3`). No rebuild needed for brain-only work.
- **Brain:** started with `setsid nohup bash start.sh >> brain.log 2>&1 < /dev/null &` from
  `~/wow-bot-brain` (uvicorn :5000 with `--reload`, so code edits hot-reload live).
  Ollama `qwen3.5:9b` on the desktop (<ollama-host>:11434). 242 tests pass (`venv/bin/python -m pytest -q`).
- **Git:** `evolution-council` was fast-forwarded into `master` and both were pushed (`d1ff527`);
  `master` is checked out. `brain.log` and `logs/` are now gitignored. The old 867MB log is
  `logs/brain-2026-07-27.log.gz`.
- Throughput: ~50 tick lines/min with 150 bots, no errors.

## What 40 minutes of live chatter showed
The fleet dedup (token Jaccard ≥ 0.6, 180s window) works but almost never fires: <1% of tick lines
were near-copies of a recent line, both in July's log and now. Repetition is **thematic**, not lexical.
`venv/bin/python logs/rep_metrics.py logs/july-ticks-baseline.txt brain.log` reproduces the numbers (max-similarity buckets
vs the previous 100 lines + top 2-word openers).

Ranked by impact:

1. **IRL bleed (R3) — the dominant immersion problem.** Roughly half of GENERAL lines are real-life
   asides. The IRL backstories look like a small shared pool: many bots independently say near-identical
   things — "closing shift at Best Buy, my feet are killing me", "my gf says hi", "night shift",
   "paper due tomorrow", "cat knocked over my beer", "kid woke up sorry brb", "wife aggro", "mom made pizza".
   In one 30s batch, 8 different bots said they'd just finished a shift.
   Also: **persona inconsistency** (Trean says "my gf" then "my bf says he…"; Caramian flips too) and a
   **verbal tic spreading across bots** ("copy roger" / "roger out" from ~10 unrelated bots — likely one
   persona's military quirk leaking into shared prompt text).
   → Fleet-wide IRL-mention budget (not per-bot), per-bot persistent IRL identity, bigger/disjoint pool.
2. **Topic variety (R4 second half).** ~1/3 of tick lines are LFG-style ("anyone want to run…").
   TRADE is stuck on one template: "four Linen Bags at five silver apiece" from 10+ bots over 30 min;
   because the heard lane makes bots respond, others started WTB-ing Linen Bags — a repeated topic
   now self-amplifies (R6 without R4). Lexical dedup can't catch this (spaced >180s, reworded).
   → topic/slot-level recency (item+channel), and a varied trade-goods pool by level band.
3. **Knowledge guard (R2) must include expansion, not just level.** Seen live: Shattrath, Nagrand,
   Zul'Aman, Sunfury Spire, Hawkstrider, netherowls, Azuremyst, Earth Shield (TBC); taunka (WotLK);
   Twilight Highlands (Cata); "need a dk" (DKs disabled); flying / "winged horse"; "queuing";
   "lvl 62+" (cap 60); "ilvl"; Final Fantasy "gil"; invented places (Molthar, Camp Orelia,
   Strahnbrund, Fizzlebottom). Low-level bots name raids (Lelindea keeps returning to
   "Onyxia attunement"; MC/ZG from level 30s–40).
4. **Output post-filter (small, cheap):** cap length (many lines run on 200+ chars), strip emoji
   (one line ended in 16 emoji), drop tokens that look like mashed bot names
   ("montacedo neimocedrocetroh"), and reject third-person narration ("…sighs Pazuwo softly while walking…").

What already works well: SAY lines are well grounded in real activity/targets (R1 is paying off),
and bots do sometimes reply to each other by name (proto-R6).

## Suggested next step
Brainstorm → spec → plan for **R3 (+ the post-filter)** per the roadmap's execution model in
`docs/superpowers/bot-realism-roadmap.md`, then R4 topic variety, then R2 with expansion coverage.
Brain-only, hot-reloads, measure with `logs/rep_metrics.py` before/after.
