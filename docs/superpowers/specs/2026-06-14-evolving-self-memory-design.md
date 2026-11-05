# Evolving Self-Memory — Design

**Date:** 2026-06-14
**Status:** Approved-in-advance (user: "make sure the bot begins to remember its personality over time" + "I approve stuff")
**Scope:** brain-only. No rebuild. Builds on shared-memory Phase 1 (`bot_memory` table, `self` kind, consolidate `summarize` seam).

## Goal

A bot should accumulate and EVOLVE a sense of itself over time — its interests, mood, what it's been up to, how it sees its own character — and have that self-view surface in conversation. Today every prompt is rebuilt from the static `who`/`identity`; the bot never changes. After this, a bot that's been grinding and venting about work will start to *carry* that, and it shifts as play continues.

## Architecture

Reuse Phase-1 plumbing — the `self` memory kind was reserved for exactly this.

### Storage (`bot_memory`, kind=`self`)
- Up to **4** self-notes per bot, each `(subject, content)`. PK `(bot, 'self', subject)` so a recurring theme (e.g. `mood`) overwrites instead of duplicating; stale themes fade via prune-to-newest-4.
- New db helpers: `prune_memory(bot, kind, keep)` (delete all but newest `keep` by updated_at) and `get_recent_messages(bot, limit)` (the bot's last N messages across all players — the reflection input).

### Reflection write-path (`self_memory.py`, mirrors consolidate.py)
- `parse_self_notes(raw) -> list[{subject, note}]` — pure, defensive (drops bad entries, caps at 4).
- `local_summarize_self(transcript, name, who, current_notes) -> raw json` — default backend; asks the local model, AS the bot, for its UPDATED self-view as JSON `[{subject, note}]`, given its identity, current self-notes, and recent chat. Low temp (0.4). Injectable seam (tests mock it; richer/critique backend swaps in later).
- `consolidate_self(bot, *, summarize=None, ...)` — pulls recent messages, runs summarize, upserts each note under kind `self`, prunes to 4. Returns applied notes. Evolution = the model rewrites its self-view each pass from (old self-view + recent behavior).

### Injection (`memory_prompt.build_self_section`)
- `build_self_section(self_notes) -> str` → `"HOW YOU SEE YOURSELF LATELY: <note>; <note>; ..."`. Empty list → `""` (prompts unchanged when a bot has no self-memory yet).
- New `{self_section}` placeholder in CHAT_PROMPT and TICK_PROMPT; main.py fills both from `get_memory_sheet(bot, 'self')`.

### Live trigger
- Count-based, in `/chat`: an in-memory per-bot counter; every **6th** chat for a bot, fire-and-forget a reflection (`asyncio.create_task` → `asyncio.to_thread(consolidate_self, ...)`) so the chat response is never blocked.
- Gated by env `WBB_SELF_REFLECT` (default ON; set `0` to disable the extra model load).
- `/reflect_self` endpoint (bot_name) for manual/testing and a future scheduler.

## Why count-based live trigger (not scenes)
Phase-1 consolidation runs on finished offline Scenes via `/reflect`. The LIVE game has no scene boundaries — just a stream of /chat and /tick. A per-bot interaction counter is the simplest robust trigger that rides existing traffic with no external scheduler. Counter resets on brain restart (fine — it's a heuristic, not state).

## Testing
- `parse_self_notes`: valid / non-list / missing fields / cap-at-4 / bad json → [].
- `consolidate_self` (fake summarize): persists notes under `self`, prunes to 4, evolves (re-run overwrites same subject).
- `prune_memory`: keeps newest N. `get_recent_messages`: returns bot's last N across players, chronological.
- `build_self_section`: empty → "", notes → formatted; `{self_section}` present in both prompts.
- Full suite stays green.

## Out of scope
Cross-bot self-comparison, the fan-out personality-critique agents (separate feature, same seam), DB-persisted counters, C++ changes.
