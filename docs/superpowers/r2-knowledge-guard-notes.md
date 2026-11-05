# R2: level-appropriate knowledge guard (2026-10-27)

Roadmap slice R2 (`bot-realism-roadmap.md`). Brain-only; no worldserver rebuild.

## What it does
- **Prompt.** Chat, heard and tick system prompts get a `WHAT YOUR LEVEL N CHARACTER KNOWS`
  block (`knowledge.build_knowledge_section`): up to 6 zones and 5 dungeons near the bot's
  level, own-faction plus contested, raids only from level 52. Below 60 it adds one line
  saying higher content is "only heard of", and every prompt forbids inventing place names.
- **Post-filter.** `knowledge.find_violations(text, level, allowed_from=...)` flags
  - zones/dungeons/raids/attunement named more than SLACK levels above the bot
    (zones 12, dungeons/raids 8), and
  - post-vanilla terms: the R8 `vanilla_guard` list minus words that are ordinary at runtime
    (Heroic Strike, flight paths, BG queues, Wrath, Hellfire, WC3 lore, "daily walk").
  Content the other speaker named (the heard message, or the line being replied to) is exempt.
- **Wiring.** `generate_deduped(knowledge=...)` re-rolls once with `KNOWLEDGE_NUDGE`. If it
  still violates: ticks and heard replies stay silent, whispers keep the line (logged).
  Log tag: `[filter] <bot> knowledge <terms>`.
- **Live levels.** Stored levels were frozen at first contact, so `get_or_create_personality`
  now re-reads level from the game DB every 10 min per bot (`[level] <bot> a -> b`),
  persists it, and re-picks the level-derived goal. A failed lookup keeps the stored level.

## Rulings (my calls)
- Positive list only in the prompt. Listing the forbidden raids would prime a 9B model to
  name them; the post-filter catches what slips through.
- Detection aliases are deliberately distinctive. "strat", "temple", "library", "DM", "ST"
  are ordinary words or ambiguous, so they aren't matched. "MC" is matched (rare otherwise).
- Invented zone names ("Sunken Sea") are discouraged in the prompt but not detected; there's
  no cheap reliable detector.

## Baseline (before R2)
`venv/bin/python eval/knowledge_audit.py brain.log`. These levels come from the stale
first-contact snapshot, so they are approximate.
- All of brain.log: 5,257 of 81,135 tick lines (6.5%).
- After R8: 123 of 15,287 (0.8%). Examples: L7 "anyone want molten core group", L22
  "heading back for dailies rn", L34 "rip saronite prices", L40 "Lol northrend?".

## Measure after deploy
1. Merge to master; uvicorn `--reload` picks it up. Print an `R2 DEPLOYED` marker into brain.log.
2. Let ~200+ tick lines accumulate, then
   `venv/bin/python eval/knowledge_audit.py brain.log --after "R2 DEPLOYED"`.
   Target: 0 violations. Also count the re-roll rate:
   `grep -c '\[filter\] .* knowledge' brain.log`.
3. Check the silent-tick share didn't jump (`chatter_metrics.py`).

## Rollback
`git revert` the R2 commits on master. There are no schema changes; the level refresh only
updates the existing `level` / `current_goal` columns.
