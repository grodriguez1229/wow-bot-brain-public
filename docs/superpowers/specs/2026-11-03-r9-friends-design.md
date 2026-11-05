# R9: friends who remember you (design)

Date: 2026-11-03. Status: draft for review.

## Intent

Gus wants the server's bots to become real relationships over time: short back-and-forths at
first, then an eventual "connection", especially inside a guild. The first visible proof of
that is:

> When Gus logs on, a bot he has been consistently running things with whispers him. The
> whisper is sometimes a callback to something they did, sometimes an invite, sometimes just
> checking in.

This slice builds that moment and the shared history it rests on. Slice #2 (R10: guild
members forming dungeon and raid groups on their own, with or without Gus) builds on the same
history and gets its own design afterwards. R9 should store history in a way R10 can read
(who ran what with whom), but R9 does not build any group-forming behaviour.

## Who and what exists today

- The player is Gus. His account is `GUS`, and his only character is **Abril** (level 10 Night
  Elf Rogue), Alliance. He hasn't played in a while. The design must work for his
  next session, not for a measured stream of traffic.
- `memory.db.relationships(bot_name, player_name, familiarity 0-100, label, notes)`.
  Familiarity only rises, by +1 per `/chat` exchange (`main.py:300`). Labels run
  stranger (<3), seen around (3+), acquaintance (10+), friend (25+), good friend (50+). There are 54 rows today;
  the top one is Astianon -> Abril at 15. Nothing records grouping, dungeons or questing
  together, and nothing decays.
- The C++ bridge (`mod-playerbots/src/Bot/LlmBridge.cpp`, `PlayerbotAI.cpp:505-600`):
  - A bot can whisper a named player, post to say/party/guild/channels, and act on `invite`
    (group invite) and `guildinvite`.
  - But a `/tick` response cannot whisper anyone: `PostTick` parses with `playerName = ""`,
    and the WHISPER branch requires a non-empty player name. So a bot cannot start a
    whisper today. It can only answer one.
  - `OnPlayerLogin` exists in `src/Script/Playerbots.cpp:98` but tells the brain nothing.
- Random bots rotate in and out of the world (about 150 online at a time out of a much larger
  pool). A given friend may not be online when Gus logs in.
- The whisper/heard reply lane was never reworked by R8. Its outputs run 150-200 characters,
  include self-introductions ("im mathalleas by the way level 60 night elf hunter") and
  invented places, and add unused emote narration. Friends talk through this lane, so R9 has to fix it
  or the friendship reads fake.

## Goals

1. **Shared history.** Record, per bot-player pair, the things that make a friendship:
   - grouped together, with duration;
   - ran a dungeon together (which one, and whether it was cleared or wiped where knowable);
   - levelled or quested in the same zone at the same time;
   - whisper and chat exchanges.

   Keep a short list of concrete, callback-able moments, e.g. "wiped on Mutanus in WC
   together, 2026-11-05".
2. **Friendship that is earned and fades.**
   - Familiarity is driven mostly by playing together. Grouping and runs count far more than
     chat.
   - It decays slowly when the two don't play together.
   - Strangers never initiate.
3. **Login whisper.** When Gus logs in, at most one or two bots who are his friends (and
   online) whisper him after a short, human-random delay. It is not instant and not every
   login. The message is one of:
   - a **callback** to a real shared moment;
   - an **invite**: the bot is doing something level-appropriate for Abril and sends a real
     group invite with the line;
   - a **check-in**, such as "yo", "how's the rogue coming", or "where u been" after a long
     absence.
4. **Real back-and-forth.** When Gus answers, the conversation continues as short real chat
   (R8-style lengths), and the bot carries what was said into next time.
5. **A voice that stays the same person** (the 4090 part). Try a bigger local model for the
   whisper/heard lane only. Keep `qwen3.5:9b` for background ticks. Gus picks the winner from
   side-by-side samples.

## Non-goals

- Bots forming groups or running dungeons on their own (that is R10).
- Bot-to-bot friendships (later, R6-adjacent).
- Making a specific friend bot log in when Gus does. If no friend is online, R9 does nothing.
- Fine-tuning a model. Revisit after R9 with the history and whisper samples it produces.
- Any change to profanity handling. Swearing stays; see CLAUDE.md.

## Anti-goals (failure even if it "works")

- A bot whispering on every login, several bots at once, or within a second of login.
  That reads as a script.
- Whispers that cite things that never happened (invented runs, places, or shared jokes).
- NPC voice: self-introductions, stating its own level/race/class, long paragraphs, emote
  narration.
- A stranger acting like a friend.
- An invite to something Abril can't do (wrong level, a raid at level 10) or to a group the
  bot isn't actually in or forming.

## Constraints

- All existing project rules apply (CLAUDE.md):
  - TDD.
  - Work in a worktree outside `~/wow-bot-brain`.
  - Never build on XPS; C++ goes through `scripts/deploy.sh`.
  - Ask before restarting the sidecar or worldserver.
  - Tests never touch the live `memory.db`, MySQL or Ollama.
  - No pushes.
- Vanilla 1.12 guardrails for anything authored. The R2 knowledge filter applies to whispers
  too.
- GPU: the 4090 is shared with the WoW client (about 12 of 24 GB in use with the 9B model
  and the client both loaded). The bigger whisper-lane model must fit alongside the client,
  so it should need about 10 GB or less.
- Whispers to Gus are rare by nature. Measurement can't rely on live volume; it needs a
  replay/dry-run harness plus a live check when Gus plays.

## Decided

- R9 = login whisper + shared history + earned/decaying friendship + whisper-lane voice fix +
  bigger-model A/B for that lane. Guild-run groups are R10.
- **Friendship is earned from scratch, but chat counts a little** (Gus, 2026-11-03).
  - Existing familiarity rows stay as they are and count as chat-earned.
  - Chat alone can lift a pair to `acquaintance` at most, roughly 10-12 points. Builder's call:
    a per-pair cap on chat-earned points.
  - Reaching `friend` and becoming able to send a login whisper requires shared play, as above.
  - Expect no login whispers in Gus's first session or two. That is intended.
- All three whisper kinds (callback, invite, check-in) are in scope. Gus said "we can adjust
  if things feel creepy later", so the frequency and threshold defaults ship as tunable knobs,
  not final values.

## Left to the builder (with my default calls, marked as such)

- **Where events come from.**
  - My call: add a small C++ event hook in LlmBridge (a new `/event` POST) for player login,
    group join/leave, instance enter, boss kill and level-up. Fire it only when a real
    (non-bot) player is involved.
  - Polling MySQL `group_member` / `character_instance` is the fallback. It is weaker: no
    boss kills or wipes, and both tables were empty in a spot check.
- **How a bot starts a whisper.**
  - My call: extend the `/tick` (or new `/event`) response with an optional `whisper_to`
    field that the C++ parser honours. Then the brain can queue a whisper for a friend bot
    and deliver it on that bot's next update.
  - The exact mechanism is the builder's choice, as long as the delay feels human
    (roughly 20-120 s after login).
- **Familiarity weights, decay rate, thresholds.**
  - My call: a whisper needs label `friend` (25+).
  - It needs at least two shared runs or one long group session.
  - A login whisper fires on about 50% of eligible logins, with at most 2 whisperers.
  - Decay is about 1 point per real-world day without shared play.
  - All of these are `WBB_*` knobs.
- **The bigger model.**
  - My call: A/B one 14B-class model at Q4 against `qwen3.5:9b` on a fixed set of 30 whisper
    prompts, with output judged side by side by Gus.
  - Ollama model tags are the builder's to pick.
- **Whisper-lane voice fix.** Apply R8's shape/length/example approach to `/chat` and
  `/heard`. Drop the unused emote-narration actions or keep them out of the prompt. Specifics
  are left to the builder.

## Builder-check rulings (my calls)

- **Any human player, not just Gus.**
  - History, the login hook and `whisper_to` work for any non-bot player.
  - Bots are identified by `RNDBOT%` accounts or the playerbots manager.
  - Gus/Abril is just the only one today.
- **The A/B doesn't block shipping.**
  - R9 ships on `qwen3.5:9b`, with a per-lane model knob (`WBB_OLLAMA_HEARD_MODEL` already
    exists; add a whisper/chat equivalent if needed) defaulting to the 9B.
  - Pulling the candidate model onto GusDesktop's Ollama for the A/B is fine. It's Gus's
    machine, and he asked to use the 4090.
- **Chat can be cited, but only from stored text.**
  - Moments from conversations may be cited, but only if they come from the stored transcript
    (`messages`) or from a moment the brain extracted and checked against it.
  - The model's free-form summaries are never cited directly.
- **Invites.**
  - A bot is invite-eligible when it is not already in a full group, and either:
    - it is within 5 levels of the player and in or near a zone that fits the player's level; or
    - it is a friend at least 10 levels higher offering a run ("want a run thru deadmines?").
      This kind of invite fires rarely.
  - Never raids for players under 55.
  - The brain judges this from the level, zone and activity it already gets on `/tick`. No new
    C++ state report.

## Success

- In a replay harness with synthetic history (e.g. 3 shared WC runs with Abril):
  - a friend bot produces a login whisper that cites only real history, is ≤60 characters
    in most cases, and has no self-introduction;
  - a stranger produces nothing;
  - an invite fires only when the bot is actually doing something Abril can join.
- Live, the first sessions Gus plays: he gets a whisper only after earning it, and he judges
  the back-and-forth as "a person". Gus has the final say.
- No regression in the R8/R2 tick metrics (`eval/chatter_metrics.py`,
  `eval/knowledge_audit.py`).
- A results doc with before/after whisper-lane samples (length, self-intro rate, invented
  places) and the model A/B verdict.
