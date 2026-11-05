# Bots That Act — "Alive Server" Design (2026-06-14, overnight)

North star: a WoW server that feels alive, where bots make sense and logging in feels
like the real game. This session: let bots take real player ACTIONS (esp. grouping),
fix the coherence "oddness", and make the world livelier. Standing user authorization
(BDD): permit engine bot-actions, raise bot counts, add/refine/remove personalities.
Local-only/private; reversible; verify against the live brain (:5000) + worldserver.

## Current state (verified by code scan)
- Brain emits `actions: [{type,target}]` in BotResponse; `parse_response` extracts
  `[ACTION:type target]` and `[EMOTE:..]`.
- C++ bridge (`mod-playerbots/src/Bot/LlmBridge.cpp`) parses the actions array.
- `PlayerbotAI.cpp` ALREADY executes: `emote` (HandleEmoteCommand) and `invite`
  (HandleGroupInviteOpcode → a real party invite to the named online player).
- The pipeline is end-to-end; it just rarely fires because the brain only unlocks
  `action_rules` at familiarity ≥ 5 and the model tends to *talk about* acting
  ("just grab me") instead of emitting `[ACTION:invite <name>]`.
- "Oddness" diagnosed from the live log: (a) promised actions not performed; (b) class
  confabulation (a Paladin "farming mana shields"); (c) location incoherence (claims to
  be in Deadmines while standing in Stormwind).

## Cost asymmetry (drives sequencing)
- Brain-only changes are HOT (restart uvicorn, verify in minutes).
- C++ changes need a worldserver IMAGE REBUILD (offloaded to Gus-Desktop per
  [[ac-build-offload]]); slow, and SSH to .99 is not currently authorized → treat the
  rebuild as the risky/last step; stage C++ if it can't be safely built tonight.

## Plan (sequenced for value-per-risk)

### Phase A — Brain-only: reliable invites + coherence (NO rebuild)
A1. Action emission: drop the familiarity≥5 gate; always offer the `invite` action.
    Teach the prompt: when you agree to group with the person you're talking to (they say
    "invite me", "lets group", "can I join"), emit `[ACTION:invite <their exact name>]`
    AND a short natural line. Use the real `player_name`. (emote already works.)
A2. Coherence guards in CHAT_PROMPT (and TICK):
    - "You are a {class_name}; only reference abilities YOUR class has." (kills the
      Paladin-mana-shield nonsense.)
    - "You are physically in {location} right now. Don't claim to be in a different
      zone/dungeon than where you are; if you're in a city you're not also in a dungeon."
A3. Tests: parse_response invite path; a prompt-builder for action rules; unit tests for
    the new action-rule text. Verify live: probe /chat "invite me" → brain emits
    [ACTION:invite Abril]; confirm worldserver receives it (log).

### Phase B — World liveliness: more bots (config only, NO rebuild)
B1. Raise random-bot count in playerbots.conf (Min/MaxRandomBots) to a livelier number
    (target ~80–150 depending on laptop headroom), watch CPU/RAM + the urand crash gotcha
    from [[ac-build-offload]]. Restart worldserver; confirm population + stability.

### Phase C — Personalities (brain-only, NO rebuild)
C1. Audit the 16 IRL_IDENTITIES for coherence; refine any that produce oddness; optionally
    add a few archetypes for variety. Keep de-clichéd. Fresh memory.db already in effect.

### Phase D — Engine: richer actions (C++; needs rebuild — attempt or stage)
D1. Add C++ handlers so the bot ACCEPTS the player's group invite (you invite a bot → it
    joins), plus `follow` and `leave`. Extend prompt action vocab to match.
D2. Build path: attempt the established Gus-Desktop offload only if authorized/reachable;
    otherwise build locally with care, or STAGE the diff + a clear rebuild note for the
    user. Never destabilize the running server.

## Verification & safety
- Each phase: restart the affected component, probe live, read brain + worldserver logs.
- Keep the worldserver UP and the brain UP throughout (the user may log in any time).
- Commit each phase locally (small steps); nothing to any remote; C++ edits not committed
  to the azerothcore repo (local working-tree only) per [[keep-customizations-private]].
- Morning report: what shipped, what's staged (esp. any pending rebuild), how to test.
