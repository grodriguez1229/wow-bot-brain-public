# R3 — IRL bleed + output post-filter (design)

**Status:** approved in brainstorming 2026-10-14 (sections 1–3 approved; user delegated
spec/plan review and asked for end-to-end execution). Brain-only, hot-reload, no restart.
Source evidence: `docs/superpowers/live-check-2026-10-14.md`, roadmap slice R3.

## Problem (measured)
- `IRL_IDENTITIES` has 16 archetypes; 216 bot rows hold exactly **16 distinct `who` strings**
  (~13 bots each). 17 bots literally carry "23yo Best Buy employee ... closing shift. Feet hurt".
- "copy roger": all 118 roger/copy tick lines come from the 12 `military_kid` bots — their
  `typing_style` quotes "'roger' or 'copy' sometimes" and the 9B model uses it nearly every line.
  Every archetype's style quotes catchphrases the model copies verbatim.
- gf/bf flip: `couples_player` says "boyfriend/girlfriend" — never fixed per bot.
- IRL is pushed from 3 places (archetype who/mood, a TICK_PROMPT rule, a weight-2 "IRL bleed"
  tick activity, plus the `resting` activity). Nothing measures or limits the fleet IRL ratio.
  Crude keyword grep: ~39% of 2,669 live tick lines.
- Output defects (finding #4): 200+ char run-ons, emoji runs, mashed-name tokens, third-person
  narration.

## Goals / acceptance
1. Fleet IRL share of ambient (tick + heard) lines ≈ 15% (target, configurable); must be < 20%
   in a post-deploy sample measured by the shared classifier.
2. Each bot has a deterministic, persistent IRL identity (same partner gender/name, same job);
   ≥95% of composed `who` strings are distinct across 200 bot names (individual slot phrases
   may repeat; the combination does not).
3. No single catchphrase ("roger"/"copy") in > 2% of fleet tick lines.
4. Post-filter: 0 emoji, 0 tick lines > 140 chars, narration lines suppressed.
5. Whispers (`/chat` default lane) keep the full persona and are not budgeted or length-capped.
6. Existing tests stay green; no restart, no C++ change.

## Non-goals
Topic variety / trade templates (R4), knowledge guard (R2), rewriting reflected memories
that mention old backstories (they drift/prune naturally), cross-process budget persistence.

## Design

### 1. `irl_identity.py` — slot composition (pure)
`compose_identity(bot_name, archetype_id=None) -> dict`, RNG = `random.Random(int(sha256(bot_name)))`.
- Archetype: the 16 existing ids (life stage, mood pool, descriptive typing style). If
  `archetype_id` is given (existing bots) it is kept; else drawn from the seeded RNG.
- Slots (archetype-specific pools): occupation detail (workplace/school + schedule), household
  (constrained: highschool/newbie/shy kid → lives with parents, no partner; stayathome_parent →
  1–3 kids with fixed ages + spouse; couples_player → partner with fixed gender + name; others
  draw alone/roommates/partner), two life details (pet+name, hobby, drink/food, music, region),
  optional signature phrase (~60% of bots) with an `irl` tag.
- Returns `{archetype, who_core, irl_facts: [str], irl_terms: [str], signature: str|None,
  signature_irl: bool, typing_style}`. `who_core` = age + life stage only (no specific
  workplace/partner/pet). `irl_facts` = the specific details. `irl_terms` = lowercase
  distinctive tokens (pet name, workplace, partner name) for the classifier.
- `IRL_IDENTITIES` stays as the archetype table, with every quoted catchphrase in
  `typing_style` rewritten as description (no example words in quotes).
- Persisted `who` = `who_core + " " + " ".join(irl_facts)` (full persona for whispers,
  consolidation, `get_who`).

### 2. Storage / migration (`db.py`, `personality.py`)
- New column `bot_personalities.irl_json TEXT DEFAULT ''` (same try/ALTER pattern).
- `get_or_create_personality`: new bot → compose, store `irl_json`, `who`, `typing_style`.
  Existing row with empty `irl_json` → compose with its `identity_id`, write back `irl_json`,
  `who`, `typing_style` (lazy, idempotent). Returned dict gains `irl` (parsed dict).
  Memories/relationships untouched.
- Pinned eval casts (`sim/memory_fixture.seed_cast`) write `irl_json='{"pinned": true}'` so
  their frozen `who` is never rewritten; a pinned/irl-less row falls back to `who` as
  `who_core` with no facts.

### 3. `irl_budget.py` — fleet budget + classifier
- Process-wide `deque(maxlen=IRL_WINDOW)` of bools; `irl_allowed()` → share < `IRL_TARGET`
  (empty window → allowed); `note_ambient_line(text, extra_terms=())`; `reset_state()`;
  `share()`.
- `is_irl_line(text, extra_terms=())`: word-boundary regex over real-life phrases (job/shift/
  boss/customers/school/homework/exam/paper due, gf/bf/wife/husband/partner/kids/mom/dad,
  pets, beer/coffee/pizza/dinner/bed/sleep, irl/afk-for-real-life cues, etc.), excluding
  ambiguous game senses (bare "class", bare "work"); plus `extra_terms` matched as words.
- Config: `IRL_TARGET=0.15`, `IRL_WINDOW=200`, `SIGNATURE_RATE=0.1` (env-overridable).

### 4. Prompt gating (`prompts.py`, `personality.py`, `main.py`)
- TICK_PROMPT gains `{irl_section}`; the old "real-life aside" rule text is removed from the
  static RULES (keeps "not just LFG/WTS/quests") and moves into `irl_section`.
- `build_irl_section(irl, allowed, signature_on)`:
  - allowed → "YOUR LIFE (mention only if it fits, briefly): <facts>" + the real-life-aside
    permission rule.
  - denied → "This line stays in the game world — don't mention your real life."
  - signature_on (and not (signature_irl and denied)) → "If it fits naturally, you might use
    your phrase: '<sig>'".
- `pick_tick_activity(..., irl_ok=True)`: when False, drop the banter activity and use a
  non-IRL `resting` variant. Default True preserves current behavior.
- Mood: denied → shared in-game pool (`IN_GAME_MOODS`), allowed → archetype pool.
- `/tick`: `allowed = irl_allowed()`; `who=who_core`; signature on with `SIGNATURE_RATE`.
- `/heard` (run_chat lane="heard"): same gating; `who = who_core (+ facts if allowed)`;
  denied appends the in-game rule to the system prompt.
- `/chat` default lane: `who` = full persisted persona, archetype mood, no budget.
- After emission, tick + heard lines call `note_ambient_line(msg, irl_terms)`.

### 5. `postfilter.py` (pure) + pipeline
- `clean_line(text, *, max_len=None, known_names=(), bot_name="") -> (text, flags)`:
  strip emoji (pictographs, dingbats, symbols, VS16, ZWJ) → drop mashed tokens (contains a
  known bot name as substring and ≥3 letters longer than it, or ≥14 letters and not in a
  long-word allowlist) → if `max_len` and too long, cut at last `.!?` ≤ max_len else last
  word boundary, strip trailing `,;:-`. Whitespace normalized.
- `is_narration(text, bot_name)`: `*...*` action, or bot's own name adjacent to a
  third-person verb (`\w+s` / `\w+es`, e.g. "sighs Pazuwo", "Pazuwo sighs").
  `strip_asterisk_actions(text)` for whispers.
- `generate_deduped(gen, *, dedupe, allow_silence=False, decline=None, max_len=None,
  bot_name="", known_names=(), silence_on_narration=False)`:
  gen → decline → clean → narration? (re-roll once with NARRATION_NUDGE, clean; still
  narration → None if `silence_on_narration` else strip asterisks) → dedup (re-roll only if
  fewer than 2 calls used so far; existing allow_silence semantics) → record fleet line.
  Max 2 LLM calls per line. Prints `[filter] <bot> <flags>` when anything fired.
- Ticks: `max_len=140`, `silence_on_narration=True`; None → `BotResponse(message="")`
  (C++ `LlmBridge.cpp:364` skips empty tick messages), no `note_bot_spoke`.
- Heard: `max_len=200`, silence on narration. Chat: no cap, no silence.
- `known_names`: cached set of `bot_personalities.bot_name` (refresh on new bot creation).

### 6. Metrics — `eval/chatter_metrics.py` (tracked; `logs/` is gitignored)
Parses `[tick]` lines (same regex as `logs/rep_metrics.py`), optional `--after "<marker>"`
to only count lines after a marker line in the log. Reports n, IRL share (`is_irl_line`),
roger/copy share, top 3-gram share, median length, share > 140 chars, share with emoji,
plus the existing max-similarity buckets and top openers.

## Rollout
Implement in a git worktree on branch `r3-irl-bleed`; full suite green there; snapshot
before-ticks to `logs/r3-before-ticks.txt`; fast-forward `master` (hot-reload); append a
`=== R3 DEPLOYED <ts> ===` marker to `brain.log`; after ~30 min run metrics before vs after.
Rollback: `git revert` the merged commits on master (hot-reloads back).
No push.

## Testing
Unit (pytest, temp DB): composition determinism + archetype constraints + partner stability
+ no quoted catchphrases in styles; migration idempotent; budget window edges; classifier
positives/negatives; gating (activity menu, irl_section allowed/denied/signature);
postfilter per rule; pipeline with fake gen (narration re-roll, silence, 2-call cap, dedup
interaction); `/tick` silence returns empty message.
