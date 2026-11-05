# R1: Ground bot chatter in real game state

**Date:** 2026-07-16 · **Status:** approved design, pending implementation plan
**Roadmap:** slice R1 of `docs/superpowers/bot-realism-roadmap.md`
**Repos touched:** `mod-playerbots` (tick payload, small C++) + `wow-bot-brain` (tick model + prompts, all policy)
**Out of scope (other slices):** whisper/heard grounding, level-knowledge guard (R2), IRL-bleed dialing (R3), anti-repetition (R4), visible General chat (R5), bot↔bot threading (R6), population (R7).

## Problem

Ambient bot chatter (the `/tick` path) is disconnected from what the bot is actually doing.
A bot grinding murlocs in Westfall still types "anyone up for Molten Core?" because the tick
prompt only knows the bot's zone name — never its activity, target, or finer location. Result:
every bot sounds like it is spam-recruiting for dungeons regardless of context.

## Goal / success criteria

1. Tick chatter reflects the bot's **real current activity**: a fighting bot references the
   fight/its target; a traveling bot references the road or destination; a resting bot does
   downtime/social banter; an idle bot pursues its goal.
2. Generic LFG-recruit lines drop sharply as a share of ambient chatter.
3. Fully backward-compatible: if the new payload fields are absent (old worldserver image,
   or a state we can't classify), tick behaves exactly as it does today.
4. No new per-tick server cost beyond a few cheap accessor calls at the existing call site.

## Architecture (hear the real state in C++, shape the topic in the brain)

```
tick timer fires (PlayerbotAI.cpp ~:603)
   │  derive activity + target + subzone from the bot object (cheap accessors)
   ▼
PostTick(botName, location, subzone, activity, target, nearbyPlayers, nearbyBots, guild)
   │  (LlmBridge serializes the two new scalar fields into the /tick JSON)
   ▼
POST /tick  { …, "subzone": "...", "activity": "...", "target": "..." }
   │
   brain: TickRequest gains 3 optional fields → pick_tick_activity + TICK_PROMPT
   │        shape the topic from activity/target/subzone
   ▼
one short in-character line on the activity-appropriate channel (unchanged reply path)
```

### C++ side (mod-playerbots, module-only, no core edits)

At the tick call site (`src/Bot/PlayerbotAI.cpp`, where `location` is derived ~line 605 and
`sLlmBridge.PostTick(...)` is called ~line 641), derive three new values from `bot` (a `Player*`)
and `this` (the `PlayerbotAI*`):

- **`activity`** — a lowercase enum string, first match wins:
  - `dead` — `!bot->IsAlive()`
  - `in_combat` — `bot->IsInCombat()`
  - `resting` — `bot->HasPlayerFlag(PLAYER_FLAGS_RESTING)` (at an inn / rested zone)
  - `traveling` — `bot->isMoving()` (and not the above)
  - `idle` — none of the above (default)
  (Verify the exact rest-flag accessor name against the module's core headers during
  implementation; `HasPlayerFlag(PLAYER_FLAGS_RESTING)` is the WotLK core API. If it is not
  available, fall back to omitting `resting` and let that state read as `idle` — never block
  the slice on it.)
- **`target`** — when `in_combat` and `bot->GetVictim()` is non-null, the victim's name; else "".
- **`subzone`** — the **area** name at the bot's position (finer than zone). The current code
  looks up the **zone** via `GetZoneId`; add a parallel `GetAreaId` lookup and localized area
  name. If area == zone or lookup fails, send "".

Extend `LlmBridge::PostTick` (declaration in `src/Bot/LlmBridge.h` ~line 58, body in
`src/Bot/LlmBridge.cpp` ~line 315) with `const std::string& subzone`, `const std::string& activity`,
and `const std::string& target`, inserted after `location`. Serialize each into the `/tick` JSON
only when non-empty (mirrors how `bot_guild` is already conditionally appended), so old-shaped
payloads stay identical when a field is empty. Escape values the same way existing string fields
are handled.

### Brain side (wow-bot-brain)

- **`models.py`** — add to `TickRequest` (all optional, defaulting to today's behavior):
  `subzone: Optional[str] = None`, `activity: Optional[str] = None`, `target: Optional[str] = None`.
- **`personality.py` `pick_tick_activity`** — add an optional `activity`/`target`/`subzone` input
  and make the activity list **state-driven** instead of the current fixed LFG/Trade/General/Say/
  banter menu:
  - `in_combat` → SAY reaction to the fight / the named `target` (e.g. "these {target} keep
    dodging"). No LFG.
  - `traveling` → SAY/GENERAL about the road, the destination, the ride.
  - `resting` → GENERAL/TRADE social banter, downtime, buying/selling, guild talk — the natural
    home for the existing LFG/WTS/banter menu.
  - `idle` → goal-oriented: the existing menu, weighted by motivation (current behavior).
  - `dead` → SAY about the death / corpse run (occasionally; keep rare).
  - Use `subzone` in place of / alongside `location` in the prompt text when present, so lines
    name the specific place ("Goldshire") not just the zone ("Elwynn Forest").
  - When `activity` is absent (None), fall back to exactly the current menu — one code path,
    guarded by a presence check.
- **`prompts.py` `TICK_PROMPT`** — thread an activity/location context line so the model speaks
  *from* the state ("You are: {activity} in {subzone or location}{, fighting {target}}").
- Reply path, channels, cooldowns, semaphore, `note_bot_spoke` — all unchanged.

## Error handling

- Unknown/empty `activity` → treated as absent → today's behavior. Never 500.
- `target` present but empty → ignored.
- Malformed/oversized payload → existing FastAPI validation (422), same as today.

## Testing

- **Brain (TDD, pure functions):**
  - `pick_tick_activity` returns a combat-shaped prompt when `activity="in_combat"` and includes
    `target`; a travel-shaped prompt when `activity="traveling"`; social when `resting`.
  - Backward-compat: with `activity=None`, output matches the current menu behavior (same channels
    available, no crash, no reference to a target).
  - `TickRequest` accepts and round-trips the three new optional fields (and works without them).
- **C++:** no module test harness — manual live checklist after deploy (below).

## Deployment

1. Brain side ships first (uvicorn `--reload`, no game impact; new fields simply unused until the
   worldserver sends them).
2. C++ side needs a worldserver **image rebuild** (`docker compose build ac-worldserver`, slow),
   then `docker compose up -d ac-worldserver`. Batchable with other C++ slices (e.g. R5) to
   amortize the rebuild.
3. Manual checklist: a bot in combat mentions its fight/target in SAY · a moving bot mentions the
   road/destination · a bot at an inn does social/downtime chatter, not LFG · with an old image
   (fields absent) tick chatter is unchanged.

## Risks

- **Activity classification is coarse** (5 states) — acceptable; honest grounding beats a fake
  "questing vs grinding" split we cannot detect. Finer states can come later without breaking the
  contract (new enum values degrade to `idle`-like handling on an old brain, and absent fields
  degrade on an old image).
- **Prompt quality is unknown until live** — mitigated by brain-side tunability (no rebuild to
  iterate on `TICK_PROMPT`/`pick_tick_activity`).
