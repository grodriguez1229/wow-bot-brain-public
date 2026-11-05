# Bot realism roadmap

**Status:** strategy / backlog — 2026-07-16. Each slice is independent and spec-able on its own.
Slices are ordered by realism-gain per effort. Most are brain-side (Python, hot-reload, no
worldserver rebuild); C++ items are flagged because they cost a multi-hour image build.

## What's wrong today (evidence from brain.log tick samples + live DB)

1. **Chatter is disconnected from what the bot is actually doing.** Bots narrate generic
   intentions ("anyone free for SM?") regardless of their real zone/activity/target. Every
   bot sounds like it's spamming LFG.
2. **Level-inappropriate knowledge leaks.** Samples reference content the bot's level would
   never know: "MC at level 15", "Onyxia attunement" from low levels, invented zones
   ("Sunken Sea", "Molthar"). The existing level-knowledge guard is too weak.
3. **IRL-persona bleed is too heavy.** "my gf plates up steaks", "Best Buy customers",
   "beer is cold", "paper due tomorrow" show up almost every line and break immersion.
4. **Repetition.** Many near-identical "anyone up for <dungeon>?" templates.
5. **General/Trade chat is invisible to the player.** Zone-scoped channels + 150 bots spread
   across 40+ zones (~5–12/zone) means the player shares General with only a handful.
6. **No bot↔bot threading.** Channels are a wall of disconnected one-liners, not conversation.

## Slices

### Slice R1 — Ground chatter in real game state  (brain + small C++)  ★ highest value
Feed the tick/heard prompt the bot's ACTUAL situation and force chatter to reflect it.
- C++: extend the tick/heard payload with activity (questing/grinding/traveling/combat/vendor/
  resting), current target mob/npc, and quest-in-progress if any. `location` already flows.
- Brain: rewrite TICK_PROMPT to speak *from* that state ("grinding murlocs in Westfall")
  instead of generic LFG. Bias topic to what's happening now.
- Acceptance: tick lines reference the bot's real zone/activity; LFG-recruit lines drop sharply.

### Slice R2 — Level-appropriate knowledge guard  (brain only)
- Build a level→(zones, dungeons) whitelist table. Inject "You have been to: …" and a hard
  "You have NOT seen and must NOT mention: …" list into the prompt.
- Post-filter: drop/regenerate replies naming content above the bot's level band.
- Acceptance: no references to raids/zones/attunements above the bot's level in a 200-line sample.

### Slice R3 — Dial down IRL-persona bleed  (brain only)
- Make real-life references rare seasoning, not every line. Add an in-character:ooc ratio
  (e.g. ~1 in 6 lines may reference real life, briefly). Tune IRL_IDENTITIES usage in prompts.
- Acceptance: <20% of tick lines contain a real-world reference; none feel jarring.

### Slice R4 — Anti-repetition & topic variety  (brain only)
- Track recent lines per bot and per channel; penalize repeated templates ("anyone free for").
- Broaden tick activities beyond LFG: crafting, exploring, reacting to surroundings, banter,
  complaints, buying/selling. Weight by motivation + real activity (pairs with R1).
- Acceptance: no template phrase exceeds N% of lines in a rolling window.

### Slice R5 — Make General chat visible to the player  (C++ + brain)
- Option A: cluster a rotating subset of bots into the player's current zone.
- Option B: bias "nearby player" ticks toward SAY / the player's zone-General.
- Option C: route a fraction of ambient chatter to a channel the player shares (LFG/World).
- Acceptance: standing in a capital or quest hub, the player sees steady in-zone bot chatter.

### Slice R7 — Raise bot population  (config + DB, ~minutes)
- Capacity is NOT the limiter: 1306 rndbot accounts / ~13.5k characters exist; only 71 accounts
  tagged type-1 today (=150 bots). Raise `AC_AI_PLAYERBOT_MAX/MIN_RANDOM_BOTS` and tag more
  accounts (`playerbots_account_type.account_type=1`) — several hundred bots, no char creation.
- Real cost is LLM tick throughput: every bot ticks every 60–180s through a Semaphore(2) on one
  Ollama GPU. Doubling bots doubles ambient load → bots may chatter LESS often unless the tick
  interval lengthens, the semaphore rises, or a faster/second model is added.
- Do this AFTER R1/R4 so denser chatter is also better chatter. Decide target count + throughput
  plan (interval vs semaphore vs model) as part of the slice.

### Slice R6 — Bot↔bot conversation threading  (brain, was deferred slice 4)
- Let elected bots actually reply to each other's recent channel lines with continuity, not
  just emit independent one-liners. Cap depth to avoid runaway loops.
- Acceptance: a readable 2–4 turn exchange between bots appears in channels.

## Execution model (token-efficient hand-off)
Per slice: `superpowers:brainstorming` → `superpowers:writing-plans` → implement via
`superpowers:subagent-driven-development` (or a fresh, cheaper Claude session pointed at the
slice's spec). Brain-only slices (R2/R3/R4) need no image rebuild and can ship fast. C++ slices
(R1 payload, R5) batch into one rebuild. Recommended order: R1 → R2 → R4 → R3 → R5 → R6.
