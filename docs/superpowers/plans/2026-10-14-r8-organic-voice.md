# R8 Organic Voice Implementation Plan

> **For agentic workers:** steps use checkbox (`- [ ]`) syntax. TDD: failing test, implement, pass, commit.

**Goal:** Make ambient bot chat read like 2005 vanilla chat: short, reactive, fragmentary,
varied in length, often replying to other lines; fewer lines overall.

**Spec:** `docs/superpowers/specs/2026-10-14-r8-organic-voice-design.md` (binding).

**Architecture:** Six new pure(ish) modules, wired into `main.py` `/tick` (full pipeline),
`/heard` (transform + chat-log recording) and `/chat` (light transform).

| module | role |
|---|---|
| `vanilla_guard.py` | banned post-vanilla term list + `find_banned(text)` (bank/template test guard) |
| `voice_examples.py` | authored example bank: `CHANNEL_EXAMPLES[ch] = [(text, shape, band)]`, `REPLY_PAIRS = [(prior, reply)]` |
| `voice.py` | shapes (`SHAPES` budgets), `pick_shape(channel, rng, reply=False)`, rotating `sample_examples(...)`, `sample_reply_pairs(...)`, `is_example_copy(...)` |
| `chat_log.py` | fleet-wide per-channel ring buffer of emitted/heard lines with scope keys, thread depth, reply counts; `record_line`, `reply_candidates`, `pick_reply_target`, `recent_context` |
| `ad_templates.py` | code-generated LFG/TRADE ads by level band, per-bot abbreviation style, per-item fleet recency |
| `typing_transform.py` | per-bot deterministic typing habits (seeded by name); `transform(text, bot, light=False, protect=())` |

## Finding: what `recent_lines` contain at runtime

`LlmBridge::PostTick` (mod-playerbots `src/Bot/LlmBridge.cpp`) sends only
`bot_name, location, subzone, activity, target, nearby_players, nearby_bots, bot_guild`.
`recent_lines` is never sent by the worldserver (only the sim harness sets it). So the
brain-side ring buffer (spec 3, fallback) is REQUIRED and is the primary source. `req.recent_lines`
is still honored (sim/eval) as an OVERHEARD section when not replying.

Channel scoping in-game (from `PlayerbotAI.cpp` / `Playerbots.cpp`): GENERAL is per zone,
TRADE/LFG are faction-wide-ish, GUILD per guild, SAY is 30yd proximity. Channels are
faction-separated. Scope keys:
- GENERAL: `(GENERAL, faction, zone)`; TRADE: `(TRADE, faction)`; LFG: `(LFG, faction)`
- GUILD: `(GUILD, guild_name)`; SAY: `(SAY, zone)` and the speaker must be in the
  ticking bot's `nearby_bots`/`nearby_players`.
- Lines heard from real players (/heard) carry faction `None` (unknown) and match any faction.

## Global constraints
- Worktree only; live checkout untouched. Python: `~/wow-bot-brain/venv/bin/python -m pytest -q`.
- Tests never touch memory.db / MySQL / Ollama (monkeypatch `call_ollama`, personality, sheets).
- R3 intact: IRL budget section + `note_ambient_line`, `clean_line` post-filter, narration
  re-roll, fleet dedup, <=2 LLM calls per line.
- Log format: `[tick] <bot> -> <CH>: "<msg>"` stays parseable; R8 extends it to
  `[tick] <bot> -> <CH> [<shape>] (re <speaker>): "<msg>"` (both tags optional).
  Silent: `[tick] <bot> -> <CH>: (silent)`; breathe-silence: `[tick] <bot>: (silent, breathe)`.
- Knobs in `config.py` with `WBB_` prefix.

## Tasks

### Task 1: config knobs
- [ ] Test `tests/test_r8_config.py`: defaults REPLY_RATE=0.5, SILENCE_RATE=0.25, REPLY_DEPTH_CAP=3,
  EXAMPLES_PER_PROMPT=10, CHAT_LOG_TTL_S=420, CHAT_LOG_MAXLEN=400, VOICE_TRANSFORM=True,
  SHAPE_BUDGETS reaction 25/question 50/fragment 70/ad 60/ramble 140; env override via reload.
- [ ] Implement in `config.py`.

### Task 2: `vanilla_guard.py`
- [ ] Test: `find_banned("flying to Outland")` -> hits; `find_banned("lf1m heals sm cath")` -> [];
  word-boundary (no false hit on "ironforge" for "dk" etc.).
- [ ] Implement: list of TBC/WotLK zones, races, classes, items/mechanics (ilvl, gearscore,
  LFD, queue, dailies, achievements, flying, Death Knight/DK, Draenei, Blood Elf, Outland,
  Northrend, Shattrath, Karazhan, Naxx is vanilla so NOT banned, etc.).

### Task 3: example bank `voice_examples.py`
- [ ] Tests `tests/test_voice_examples.py`: every channel GENERAL/TRADE/LFG/GUILD/SAY has >=40
  lines; >=60 reply pairs; every shape tag valid; no banned term in any line/pair; no emoji;
  median length <=40; >=25% of lines <=20ch; no duplicate lines.
- [ ] Author the bank.

### Task 4: `voice.py` shape sampler + example sampler
- `SHAPE_WEIGHTS[channel]` (and `REPLY_SHAPE_WEIGHTS`), `pick_shape(channel, rng, reply=False) -> str`.
- `shape_budget(shape) -> int` (max_len), `shape_num_predict(shape) -> int`, `SHAPE_HINT[shape]`.
- `sample_examples(channel, shape, level, k, rng) -> list[str]`: ~60% of k match shape, rest other
  shapes, band-filtered; rotation state guarantees two consecutive calls for a channel never
  return the same set.
- `sample_reply_pairs(n, rng)`; `is_example_copy(text, examples)` (token Jaccard >= FLEET threshold,
  lines of <=3 tokens exempt).
- [ ] Tests: weights respected statistically (seeded), LFG/TRADE pick "ad" most often, reply
  never picks "ad", band filter, rotation, copy check.

### Task 5: `chat_log.py` ring buffer + threads
- `record_line(speaker, channel, text, *, faction, zone, guild, reply_to=None, now=None) -> int id`
- `scope_matches(entry, channel, faction, zone, guild)`
- `reply_candidates(bot, channel, *, faction, zone, guild, nearby=(), now=None) -> list[entry]`
  (other speakers, fresh within TTL, depth < cap, direct replies < 2, SAY needs speaker nearby)
- `pick_reply_target(cands, rng)`: weight questions x3, unanswered x2, newer higher.
- `recent_context(entry, n=4)`: last n lines in that scope up to and including target.
- `visible_channels(...)`; `reset_state()`.
- [ ] Tests for each, including depth cap 3 and faction isolation.

### Task 6: `ad_templates.py`
- `make_ad(channel, bot_name, level, class_name, faction, rng, now=None) -> str`
- LFG: dungeon by level band (+faction-appropriate), role needs, per-bot style (caps, abbreviations,
  pst variants). TRADE: WTS/WTB/service from a varied item pool by band, per-item fleet recency
  (an item used in the last N trade ads is skipped).
- [ ] Tests: vanilla-clean over 2,000 samples (guard), level-appropriate dungeons, item variety
  (no item >10% over 200 ads), deterministic per-bot style, length <= 60.

### Task 7: `typing_transform.py`
- `style_for(bot_name) -> dict` (seeded: caps mode, drop_punct, abbrev subset, typo_rate, lol rate).
- `transform(text, bot_name, *, light=False, protect=(), rng=None) -> str`. Never alters
  `[bracketed]` text, protected names, or tokens with digits. light: caps+punct only.
- [ ] Tests: deterministic style per name, styles differ across names, protection holds,
  light mode makes no typos/abbrev/lol, never empty, never exceeds len+6.

### Task 8: prompt rewrite (`prompts.py`)
- New TICK_PROMPT "chat log" framing with `{examples_section}` + `{nearby_section}` (chat log or
  overheard); keep persona/R1 state/self/identity/IRL placeholders and vanilla + AI rules.
- `build_examples_section(channel, examples)`, `build_chat_log_section(lines, target)`,
  `build_tick_user_message(channel, shape, situation, target=None)`.
- [ ] Update existing prompt tests that pin the old wording where needed; new tests for builders.

### Task 9: `/tick` pipeline (main.py)
Order: breathe-silence (SILENCE_RATE, no LLM) -> reply decision (candidates across visible channels,
REPLY_RATE, not in_combat/dead) -> else pick_tick_activity channel -> shape -> if ad: template ->
else LLM with shape budget (num_predict, max_len) + example-copy check folded into dedup re-roll ->
transform -> record in chat log (reply_to) -> R3 accounting -> log with tags.
- [ ] Tests (fake ollama): silence path makes 0 LLM calls; ad path makes 0 calls and emits a
  template; reply path prompt contains the target line, logs `(re X)`, increments depth;
  R3 tests still pass; transform applied; example copy re-rolls.

### Task 10: `/heard` + `/chat`
- heard: transform (full) + record incoming speaker line and replies in chat log.
- chat: light transform.
- [ ] Tests.

### Task 11: metrics
- TICK_RE accepts optional `[shape]` and `(re X)` tags; new fields `le20` share, `reply` share,
  `shapes` mix, `top_opener` share; `_fmt` prints them. Old-format lines still parse.
- [ ] Tests; run against `logs/r8-before-ticks.txt`.

### Task 12: dry-run (outside pytest, <=30 Ollama calls), notes doc, commit.
