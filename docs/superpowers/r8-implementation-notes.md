# R8 organic voice: implementation notes (2026-10-14)

Branch `r8-organic-voice`, based on master `3e0df31` (R3). Not deployed. Spec:
`specs/2026-10-14-r8-organic-voice-design.md`. Plan: `plans/2026-10-14-r8-organic-voice.md`.
Tests: 433 passing (baseline 359). No tests touch memory.db, MySQL or Ollama.

## What changed

| file | change |
|---|---|
| `voice_examples.py` (new) | Authored example bank. 48-88 lines per channel (GENERAL, TRADE, LFG, GUILD, SAY) and 67 reply pairs. All lines are original and vanilla-only. Lines are tagged by shape, and optionally by faction and level band (e.g. `H@13-18\|LFG RFC`). |
| `vanilla_guard.py` (new) | Banned post-vanilla terms: TBC/WotLK zones and instances, races, DK, ilvl, gearscore, queue, LFD, dailies, heroics, flying, gems, guild bank, arena brackets, materials. `find_banned()` uses word boundaries ("uldaman" passes, "ulduar" does not; "dkp" passes, "dk" does not). |
| `voice.py` (new) | Shape sampler: per-channel weights plus reply weights. Shape budgets: char cap, `num_predict`, `max_sentences`, a hint. Rotating example sampler: about 60% of examples match the chosen shape, filtered by band and faction, and never the same set twice in a row for a channel. `is_example_copy`. Optional real-chat corpus loader (off by default). |
| `chat_log.py` (new) | Fleet-wide ring buffer of channel lines with scope keys, reply threads (root, depth, reply counts), candidate selection and target picking. |
| `ad_templates.py` (new) | Code-built LFG/TRADE ads with no LLM call. 26 vanilla dungeons/raids by level band and faction. 75 items by band with plausible prices. Class services (rogue lockboxes, mage portals at 40+). Per-bot ad style (caps, preferred abbreviation, pst variant), seeded by name. Fleet recency: last 12 items and last 6 dungeons. |
| `typing_transform.py` (new) | Per-bot typing habits, seeded by name: caps mode, rates for dropped trailing punctuation and apostrophes, an abbreviation subset (u, ur, ty, np, lf, pls, prob, idk, ppl, rn, cuz, tho, gonna, any1, lvl, ...), a typo rate (0 for 40% of bots), a lol/emoticon habit and a caps-outburst habit. Item links, protected names and tokens with digits are never touched. |
| `prompts.py` | `TICK_PROMPT` rewritten in a "chat log" framing. New `{examples_section}` holds the examples as log lines. The style-description rules were cut down. Persona, R1 state line, self/identity, the R3 IRL section and the vanilla/AI rules are kept. Added `build_examples_section`, `build_chat_log_section`, `build_tick_user_message`, `channel_label`. |
| `main.py` `/tick` | New pipeline, described below. `generate_deduped` gained `avoid=`: a near-copy of a shown example, a pair line or the target line counts as a duplicate and gets one FRESH re-roll, within the existing 2-call cap. |
| `main.py` `/heard` | The incoming player line goes into the chat log (faction unknown, zone = location, guild resolved from a cached same-guild hearer). Each heard reply is recorded as a reply to it, so ticking bots can join the thread. |
| `main.py` `run_chat` | Typing transform runs after the post-filter: full on the heard lane, light (caps, punctuation, apostrophes only) on whispers. |
| `postfilter.py` | A word-boundary truncation now drops trailing function words ("...then ill" becomes "..."). Sentence-end truncation is unchanged. |
| `config.py` | R8 knobs (listed below). |
| `eval/chatter_metrics.py` | Parses the optional `[shape]` and `(re X)` tags. Adds `tick_records()` and the new fields `le20`, `reply`, `reply_non_ad`, `shapes`, `top_opener`/`top_opener_share`. The old format still parses: on `logs/r8-before-ticks.txt` it reports median 67ch, <=20ch 0%, replies 0%, shapes all `untagged`. |

### /tick pipeline (in order)
1. **Breathe silence.** With probability `SILENCE_RATE` the tick returns empty before any DB or LLM work. It logs `[tick] X: (silent, breathe)`, which the metric ignores.
2. **Reply-first.** Skipped when `in_combat` or `dead`. The bot collects reply candidates from the chat log across the channels it can see. If there are any, then with probability `REPLY_RATE` it picks one. Questions weigh x3 and unanswered lines x2, and newer lines weigh more. The channel is the target's channel and the shape comes from `REPLY_SHAPE_WEIGHTS`.
3. Otherwise `pick_tick_activity` picks the channel (unchanged R1 logic) and `pick_shape` picks the shape.
4. **Ad shape** (LFG/TRADE): uses a template with no LLM call. If nothing fits the level (an LFG bot below about 11), it falls back to a short LLM question.
5. **LLM path.** The prompt gets 10 rotated examples (plus 3 reply pairs when replying). When replying, the live chat log goes in as the last 4 lines of the target's scope. The user message reads "<situation> [X just said: ...] Type your next/reply message in <channel>: <shape hint>. Just the message." `num_predict`, `max_sentences` and the post-filter `max_len` come from the shape. Narration re-roll and fleet dedup (R3) stay, with the example-copy check folded into dedup.
6. Typing transform, capped at `TICK_MAX_CHARS`.
7. The line is recorded in the chat log (with `reply_to`), `note_bot_spoke`, `note_ambient_line` (R3 IRL budget), and logged as
   `[tick] <bot> -> <CH> [<shape>] (re <speaker>): "<msg>"`.

## Finding: `recent_lines` are never sent by the worldserver
`LlmBridge::PostTick` (mod-playerbots `src/Bot/LlmBridge.cpp`) posts only bot_name,
location, subzone, activity, target, nearby_players, nearby_bots and bot_guild. Only the sim harness fills
`recent_lines`. So the brain-side ring buffer (spec §3 fallback) is the primary reply source.
`req.recent_lines` still renders as the OVERHEARD section on non-reply ticks (sim/eval).

## Rulings (with cost if wrong)
1. **Visibility scopes:** GENERAL = same zone + faction; TRADE/LFG = same faction, any zone; GUILD = same guild; SAY = same zone with the speaker in nearby_bots/players (C++ uses 40yd). In 3.3.5, Trade is city-only, so a bot in Westfall may "reply" to a Trade line it couldn't see. *Cost:* occasional off-screen replies in Trade, harmless to read. GENERAL per zone is the strict choice; if bots are spread thin, the reply share will come in low (knob: `CHAT_LOG_TTL_S`).
2. **Real-player lines from /heard have faction None** (the request carries no faction) and match either faction. *Cost:* a Horde bot may answer an Alliance player's General line. Since the player is usually Gus, this mostly reads as "bots notice me".
3. **Reply caps:** depth cap 3 per root (spec), plus at most 2 direct replies per line and one reply per bot per line (my additions, to stop pile-ons). *Cost:* slightly fewer replies.
4. **No replies while in_combat/dead.** Those ticks keep the grounded R1 fight/corpse-run line.
5. **Silence comes first**, before the reply decision and the personality load, so silent ticks are almost free. Silent ticks return channel SAY with an empty message, which the C++ bridge already skips.
6. **Ads are template-only.** Ad lines bypass the LLM, the post-filter and the transform, because templates carry their own per-bot style. They still feed the fleet dedup window, the chat log and the IRL budget (never IRL).
7. **Example-copy check exempts lines of 3 tokens or fewer** ("lol", "inv pls" are everyone's words). Longer lines re-roll at Jaccard >= `FLEET_DEDUP_THRESHOLD` (0.6) against shown examples, pair lines and the target line (anti-parroting).
8. **Transform scope:** full on tick + heard, light on whispers (caps, trailing punctuation, apostrophes). Item links, all known bot names, the target/speaker name and tokens with digits are protected. Zone names get lowercased in "lower" style, which is realistic. *Cost:* whisper replies lose some capitalisation.
9. **Log format** gains a `[shape]` tag (not in the spec) so the metric can report the shape mix. Both tags are optional in the regex.
10. **Truncation trims dangling function words** in `postfilter._truncate`. This also affects R3 heard/tick truncation, and only makes it cleaner.
11. **Shape weights tuned toward the controller's corpus calibration** (median 18ch, 54% <=20ch): GENERAL reaction 25 / question 25 / fragment 42 / ramble 8; GUILD and SAY are reaction-heavier; TRADE 70% ads, LFG 82% ads; replies reaction 55 / fragment 32 / question 10 / ramble 3. Transform: 55% of bots all-lowercase, drop-trailing-punct rate 0.5-1.0.
12. **Corpus loader** (`WBB_VOICE_CORPUS_PATH`, empty = off). It keeps only era `unknown`/`vanilla` lines from public channels (GENERAL/OTHER/SAY/PARTY/YELL/GUILD/TRADE/LFG; never SYSTEM, WHISPER or RAID). It drops lines with banned terms, profanity, gold-seller spam, "48k"-style numbers and item links (unknown era). On the current transcript that leaves 171 lines (GENERAL 54, SAY 45, GUILD 51, TRADE 21), mostly reactions. Nothing from the corpus is committed. A few odd lines survive ("0 players found."), so leave it off unless you want the extra register.
13. The prompt no longer appends "Other players nearby: X" for nearby bots. Nearby real players are still named in the SAY situation line.

## Knobs (`config.py`, `WBB_` env, read at import, so changes need a process restart)
| knob | default | effect |
|---|---|---|
| `WBB_SILENCE_RATE` | 0.25 | share of ticks that say nothing (0 = off) |
| `WBB_REPLY_RATE` | 0.5 | chance to reply when a candidate exists (0 = off) |
| `WBB_REPLY_DEPTH_CAP` | 3 | max chain depth per root line |
| `WBB_EXAMPLES_PER_PROMPT` | 10 | examples shown per prompt |
| `WBB_CHAT_LOG_TTL_S` | 420 | how long a line stays reply-able |
| `WBB_CHAT_LOG_MAXLEN` | 400 | ring buffer size |
| `WBB_VOICE_TRANSFORM` | 1 | per-bot typing habits on/off |
| `WBB_VOICE_CORPUS_PATH` | "" | optional extra examples (jsonl), off |
| `SHAPE_BUDGETS` (code) | reaction 25 / question 50 / fragment 70 / ad 60 / ramble 140 | post-filter cap per shape |
| shape weights (code, `voice.py`) | see ruling 11 | |

## Dry-run (30 Ollama calls total, outside pytest)
Script: scratchpad `dryrun.py`. It sends synthetic ticks for 12 fake bots (6 Horde, 6 Alliance, levels 12-60, `compose_identity` people) through the real `/tick` with live Ollama, faking DB/personality, under a hard call cap. Silent and ad ticks cost nothing, so about 66 ticks used 30 calls (roughly 0.45 calls per tick, against about 1.0+ before). Prompt iteration: the first pass used "a few words" hints and fragments ran to 70+ chars and got truncated mid-word. Switching to "at most 6/7 words" and the dangling-word trim fixed most of that.

15 sample outputs (first two runs, then the final run after tuning):
```
L33 [tick] Liora -> SAY [reaction]: "stupid gnolls lol"
L44 [tick] Elowen -> SAY [fragment]: "aggro lost him? i was behind rock..."
L33 [tick] Liora -> SAY [question] (re Elowen): "did we hit 'im yet though lol"
L37 [tick] Zulja -> SAY [reaction]: "Mana low"
L31 [tick] Krasha -> GENERAL [question] (re Zulja): "Does it count as more dps?"
L37 [tick] Zulja -> TRADE [ad]: "wtb [Small Silk Pack] paying 1.6g ea"
L23 [tick] Gorak -> GENERAL [question]: "still sleeping well after night shift?"
L14 [tick] Hoofer -> GENERAL [fragment] (re Gorak): "naah barely sleepin atm need xp more than coffee kinda tiired though"
L52 [tick] Mortis -> SAY [fragment]: "watching out for goblins again lol"
L14 [tick] Hoofer -> SAY [reaction]: "too many snakes today"
L44 [tick] Elowen -> SAY [fragment]: "greenberries cheap today"
L12 [tick] Grimbo -> GENERAL [fragment]: "this zone sucks my ears bleedin"
L44 [tick] Elowen -> SAY [reaction]: "low health"
L18 [tick] Brannick -> TRADE [fragment]: "Buying steel ingots afk soon tho"
L14 [tick] Hoofer -> SAY [ramble]: "this rapter keeps dodging my swipe while i try so hard its literally annoying man im gonna go drink some water real quick sorry"
```
Template ads (no LLM), sampled offline: `lfm kraul dps`, `rfc need 4 more PST`, `LFG wailing caverns can heals`, `LFM mara tank w me`, `lf3m sfk`, `lfm brd need heals and dps`, `wts [Dreamfoil] x20 2s ea`, `WTB [Mountain Silversage] x10`, `selling [Rugged Leather] stacks PST`, `lw lf work pst`.

Bad outputs also seen (all model-side, not from the bank or templates):
- "Gotcha near stranglethorn if u head that way lmao" (a vague reply to a boat question)
- "haha nah im heading north for westfall dailies..." ("dailies" is an R2 knowledge leak)
- "...grinding grommash hold for like two hours trying to hit that boss..." (nonsense lore)
- "Slow as fuck" (model profanity)
- "...grinding barrens w/ zulja..." (the bot names its own character)
- "Who sell repair kis nears by plz" (the model plus the typo layer is too much)

## Known gaps / concerns
- **Runtime knowledge leaks (R2) remain**, and are out of scope by spec. `vanilla_guard.find_banned` could cheaply serve as one more re-roll trigger in `generate_deduped`. It's a one-line change, but "flying"/"queue" have false-positive risk in free text, so I left it for R2.
- **Reply share depends on per-zone density.** GENERAL is zone-scoped and bots may be spread thin. If the reply share comes in under 25%, raise `WBB_CHAT_LOG_TTL_S` (e.g. 900) or `WBB_REPLY_RATE` (0.7).
- **Rambles still truncate at 140** mid-thought sometimes. They are about 5-8% of LLM lines.
- **The heard lane prompt is unchanged** (no examples or shapes). Heard replies get the transform only, so they will stay longer than tick lines.
- **Profanity** from the model is not filtered (the pre-R8 behaviour, same as before).
- **Rotation is per channel**, not per (channel, shape). Consecutive sets differ, but they can overlap heavily.
- **All R8 state is in-process.** Thread state and recency reset on reload, and the chat log refills within minutes.
- **The dry run is small (30 calls),** so the shape-mix and length targets are unverified at fleet scale. The real measurement is the deploy.
- **Knob changes need a restart**, because env is read at import and `--reload` only watches files. Rollback is a git revert (see below).

## Deploy + measurement
1. Fast-forward master (master `3e0df31` is an ancestor of this branch, 12 commits ahead):
   `git -C ~/wow-bot-brain merge --ff-only r8-organic-voice`
   uvicorn `--reload` picks it up. Wait for "Application startup complete" in brain.log.
   No DB migration and no new dependencies.
2. Marker: `echo "=== R8 DEPLOYED $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> ~/wow-bot-brain/brain.log`
3. Health: `curl -s localhost:5000/health`, and `grep -c Traceback brain.log` before and after.
   Quick look: `grep -A0 "R8 DEPLOYED" -n brain.log`, then `tail -f brain.log | grep "^\[tick\]"`.
4. Wait for 1,500 or more tagged tick lines. Expect about 45-55 emitted lines/min with 25% silence, so roughly 30-35 min.
5. Metrics:
   `cd ~/wow-bot-brain && venv/bin/python eval/chatter_metrics.py logs/r8-before-ticks.txt brain.log --after "R8 DEPLOYED"`
   Targets: median <=40ch (aim ~20), <=20ch >=25%, replies >=25% (the `reply` field; `reply_non_ad` excludes template ads), top 3-gram and top opener <=3%, IRL <20%, emoji 0, >140ch 0, roger/copy <2%.
6. LLM calls per tick (no direct counter). After the marker, count ticks by kind:
   `sed -n '/R8 DEPLOYED/,$p' brain.log | grep -c "(silent, breathe)"` (0 calls),
   `... | grep -c '^\[tick\] .* \[ad\]'` (0 calls),
   `... | grep -c '^\[tick\] .* \[\(reaction\|question\|fragment\|ramble\)\]'` (1 call, 2 with a re-roll),
   `... | grep -c '^\[filter\]'` (re-roll pressure). Before R8 every tick was 1-2 calls.
7. Blind read: take 20 random lines from the before snapshot and 20 from after the marker, strip the tags and shuffle. The tags must be stripped:
   `sed 's/^\[tick\] \S* -> \S*\( \[[a-z]*\]\)\?\( (re \S*)\)\?: //'`
8. Rollback: `git revert --no-edit 3e0df31..<R8 head>` on master (hot-reloads). Or set `WBB_SILENCE_RATE=0 WBB_REPLY_RATE=0 WBB_VOICE_TRANSFORM=0` and restart, which leaves only the new prompt, shapes and ads active.
