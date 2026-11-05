# Slice 1: Heard-Chat Election — bots react to player messages beyond whispers

**Date:** 2026-07-14 · **Status:** approved design, pending implementation plan
**Repos touched:** `mod-playerbots` (C++ hook, small/stable) + `wow-bot-brain` (election + prompts, all policy)
**Out of scope (deferred slices):** bot↔bot conversation (slice 4), new actions beyond already-committed guildinvite (slice 2), persona diversity/anti-repetition (slice 3).

## Problem

Bots only answer whispers. `/say`, party, guild, and public channels (General/Trade/LFG) are
deaf: the LLM bridge has no input hook for them. Additionally the `guildinvite` action
(mod-playerbots `cc737b76`) is committed but not compiled into the running worldserver image.

## Goals / success criteria

1. A player message on say/party/guild/General/Trade/LFG can produce in-character bot replies
   through the existing LLM pipeline.
2. A bot named in the message **always** replies (prefix match, case-insensitive).
3. Bots engaged in the conversation (spoke in that channel recently, or have recent message
   history with the speaker) reply often; other relevant bots occasionally; everyone else stays
   silent. Max 2 responders per message (named bots exempt from cap).
4. No reply storms and no Ollama overload: per-bot per-channel cooldown (~30s), global cap of
   2 concurrent LLM calls, roster capped at ~30 hearers per event.
5. Whisper behavior unchanged. Worldserver never blocks on the brain (fire-and-forget).
6. Deploy ships the pending guildinvite handler and the RandomBotAccountCount=170 fix.

## Architecture (Approach A — hear in C++, elect in the brain)

```
player msg ──► OnPlayerCanUseChat overload (fires once per message, mod-playerbots)
                 │  assemble hearer roster, PostHeard(speaker, channel, msg, hearers)
                 ▼
             POST /heard  (one per message, worker thread, 75s timeout)
                 │
                 brain: election (tiers, caps, cooldowns) → chat prompt per elected bot
                 │        (candidate tier may answer "PASS" = stay silent)
                 ▼
             response body {"responses":[...]}  ──►  bridge queues each  ──►  PopResponse
             (bot speaks in-channel, LLM latency = natural typing delay)
```

### C++ side (mod-playerbots, module-only, no core edits)

**Amended after code reading:** the module's `OnPlayerCanUseChat` overloads in
`src/Script/Playerbots.cpp` already fire **once per player message** with the full hearer
set in reach (say/yell overload enumerates nearby bots; channel overload enumerates zone
bots; group and guild overloads enumerate members). So no debounce/aggregation map is
needed — each overload assembles the roster and calls `PostHeard` directly:

- Say/Yell + General/Trade/LFG overloads: **replace** the existing ad-hoc rolls
  (30% one-random-bot for say/yell, 20% for channels) with roster assembly + `PostHeard`.
- Group and Guild overloads: add roster assembly + `PostHeard` (previously no LLM hook).
- All gated on speaker being a **real player** (never a bot) and
  `AiPlayerbot.LlmHeardEnabled`. Roster sampled down to 30 if larger (named-in-message
  hearers always retained; brain re-checks names anyway).
- Config: `AiPlayerbot.LlmHeardEnabled` (default 1) + `AC_AI_PLAYERBOT_LLM_HEARD_ENABLED`
  env passthrough, so the feature can be killed without a rebuild.
- Reply path unchanged: elected replies arrive via the existing per-bot queue and
  `PopResponse` channel routing (already supports SAY/PARTY/GUILD/GENERAL/TRADE/LFG).

### Brain side (wow-bot-brain)

- New endpoint `POST /heard`: `{speaker, channel, message, location, hearers:[{bot_name,
  distance, same_party, same_guild}]}`. **Amended:** the bridge has no push channel — it
  parses the HTTP response body into its reply queue (like `/chat`). So `/heard` responds
  **synchronously** with all elected replies: `{"responses": [{bot_name, message, channel,
  emote, actions}, ...]}`; the bridge queues each. `PostHeard` uses a 75s HTTP timeout
  (up to 2 LLM calls behind the global semaphore).
- **Election tiers** (pure function, unit-testable, all constants in `config.py`):
  1. *Named*: hearer whose name prefix-matches a word in the message → guaranteed.
  2. *Engaged*: spoke in this channel within ~2 min (in-memory recent-speaker ring per
     channel), or has `messages` rows with the speaker in the last ~10 min → ~60% chance.
  3. *Candidate*: top 1–2 by score = familiarity (`relationships`) + keyword overlap with
     persona `who`/`current_goal` → low chance (~15%), prompt appended with "reply only if
     you have something to add; otherwise reply with nothing."
  4. Caps: ≤2 responders/message (named exempt); per-bot per-channel cooldown 30s;
     global `asyncio.Semaphore(2)` around Ollama calls (shared with /chat and /tick).
- Elected bots reuse the existing chat-prompt path (`CHAT_PROMPT` + memory/relationship
  sections) with channel context; empty parse result → log `[heard] <bot> stayed silent`,
  send nothing.
- Replies are queued for the bridge exactly like whisper replies (same `BotResponse` shape,
  `channel` set to the originating channel).

## Error handling

- Brain down → `PostHeard` fails silently at the bridge (same as `PostTick`); no retries.
- Malformed/oversized payloads → 422/413, logged, dropped.
- Ollama timeout on an elected bot → that bot stays silent; others unaffected.
- Duplicate player message within the same second → same hash bucket, one event.

## Testing

- **Brain (TDD):** unit tests per election tier, the cap/cooldown/semaphore behavior,
  stay-silent parsing, and a FastAPI TestClient test for `/heard` end-to-end with a stub LLM.
- **C++:** no module test harness; manual live checklist after deploy:
  whisper still works · `/say` near a bot gets an answer · naming a bot in Trade guarantees
  that bot answers · ≥3 bots present respects the 2-responder cap · party chat works ·
  guildinvite action fires (Esterini → Brotherhood of Twilight).

## Deployment

1. Implement + test brain side (restart uvicorn; no game impact).
2. Implement C++ side; **rebuild worldserver image** (`docker compose build ac-worldserver`,
   slow at CPARALLEL_JOBS=2), then `docker compose up -d ac-worldserver` — the recreate also
   applies the pending `RandomBotAccountCount=170` env fix.
3. Run the manual checklist; watch `brain.log` + `docker logs ac-worldserver | grep -i llmbridge`.

## Risks

- **Prompt quality for channel context** is unknown until live — mitigated by the
  kill-switch config and Python-side tunables (no rebuild needed for policy changes).
- **Rebuild is the long pole** (possibly hours); nothing else depends on it until step 2.
- The in-memory recent-speaker ring resets on brain restart — acceptable (worst case: one
  missed "engaged" tier window).
