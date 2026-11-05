# Persona-Surfacing + Topic Range — Design

**Date:** 2026-06-14
**Status:** Approved
**Scope:** brain-only (prompts.py + personality.py). No rebuild, no DB schema change.

## Problem

Live diagnosis: ~95% of bot chatter is transactional errand-announcements (LFG/WTS/"killing X for Y"). The rich IRL personas already stored in each bot's `who` field get crushed by the prompt framing: `CHAT_PROMPT` leads with `CHARACTER` + `IN-GAME GOAL` and mandates "5-15 words ideal," so asked "tell me about yourself," a retail-worker persona answers "tired dwarf grinding to 20." The person never surfaces; topics never leave the grind.

## Decisions (user-approved)

1. **Adaptive length** for CHAT — terse for terse exchanges, 2-4 sentences when personal/conversational. Ambient TICK stays short.
2. **Person bleeds through** — when asked something personal, answer as the human behind the keyboard (job/school/mood/IRL), the way a real 2005 player would in a whisper. Character is the costume; person is who they ARE.
3. **Fold in a model A/B** — qwen3.5:9b vs mistral-small:22b on the new prompts; user picks the live model after seeing quality + latency.

## Changes

### 1. Rewrite `CHAT_PROMPT` (prompts.py)
- Person-forward framing: lead with the IRL person, character is what they're playing.
- Replace hard "5-15 words ideal" with adaptive-length rule (short default; 2-4 sentences when personal/real conversation; never paragraphs/essays).
- Add persona-surface rule: personal questions → answer as the PERSON (job/school/mood/IRL life).
- Add topic-range seeds: real life, opinions on the game, other players, jokes, reactions, plans — not just LFG/WTS/grind. React and ask back.
- Keep ALL existing guards: no emoji, no post-vanilla, class/location coherence, anti-echo, never-reveal-AI, action_rules.

### 2. Lighten `TICK_PROMPT` topic range (prompts.py)
- Ambient stays short (one line), but add an IRL-bleed/banter lane so ticks aren't ~95% transactional.
- Widen toward IRL/reactions, NOT more dungeon goals (memory: diversifying goal strings backfired into more LFG spam).

### 3. `pick_tick_activity`: add a "banter/IRL" activity (personality.py)
- New activity emitting on SAY or GENERAL with non-errand content drawn from the bot's IRL life / a reaction / a random opinion. Modest weight so the ambient stream has non-errand content without flooding.

### 4. Model A/B
- Probe qwen3.5:9b vs mistral-small:22b on the NEW prompts across representative scenarios (personal "tell me about yourself", casual exchange, errand ask). Report quality + latency. User picks live model. Brain-only via model override.

## Testing

- Structural: assert CHAT_PROMPT contains the adaptive-length + persona-surface + topic-range directives; assert TICK_PROMPT retains one-line constraint + gains the banter lane; assert `pick_tick_activity` mix includes the banter activity.
- Behavioral: live /chat probes (before/after samples) + the model A/B.
- Keep existing suite green (105 tests).

## Out of scope

Density/visibility (#2), bot↔bot live interaction (#4), DB schema, C++ rebuild.
