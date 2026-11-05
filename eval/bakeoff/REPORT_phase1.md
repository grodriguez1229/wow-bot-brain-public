# Shared Memory Phase 1 — Bake-off (2026-06-14)

Seeded eval run of the merged Phase-1 shared-memory code on M*=qwen3.5:9b, real Alliance
identities (Geysse/Lynea), seeded relationship fixture, **overheard layer ACTIVE**,
consolidation OFF. 16 eval scenes, scored cold vs `prompts/judge.md`. Local-only/private.

## Headline
**Aggregate is flat: candidate 2.16 vs 2.163 baseline (eval_gain −0.00).** But the average
hides a real, directional split — shared memory clearly *works for conversations* and does
*nothing for ambient broadcast*, and the two effects cancel.

## What got better (the overheard layer is doing its job)
Player-present scenes improved markedly vs cycle 2 — genuine turn-taking, topic threads
that build, and emergent banter:
- `org-s11` (2.8): a real "wanna duo up?" / "maybe, but my feet are killin me" exchange.
- `org-s14` (2.8): an emergent **"beans"** riff — "brb chug some beans" → "beans are the
  fuel man" → "beans are life man." Bots building on each other, which never happened pre-Phase-1.
- `org-s15` (2.8): "just hit 17, anyone want to run Deadmines with me?" → "brb grabbing a
  bite" → "take your time" — actual coordination.
- `westfall-s11` (2.6): "my feet killin me" → "lmao mine too, chill at the inn?" → "inn it is."
The best player scenes went from ~3.0 ceiling (one-offs) in cycle 2 to a consistent 2.4–2.8 band.

## What did NOT improve (and regressed)
1. **No-player ambient scenes stayed ~1.5–2.0.** Worse: the overheard layer induced
   **verbatim echoing** — bots now SEE the last line and parrot it ("ugh tired of the rats
   already" repeated 3×; "ugh missed the whole Elwynn grind" ×3). The "don't repeat it"
   instruction is too weak. With no player and no goal pressure, awareness just amplifies
   the loop instead of breaking it.
2. **Clichés came back** ("man i wish i could play more", "ugh another murloc", "my feet
   are killin me"). Phase-B's de-clichéing was reverted when that experiment failed its
   gate, so the baked-in template clichés are live again — and the overheard echo amplifies them.
3. **Two new lore-gate failures** the clean qwen baseline didn't have:
   - `ambient-s11`: "glad to be back in **WotLK**" — post-vanilla expansion (anachronism).
   - `ambient-s13`: "🥺" — modern emoji breaks 2005 immersion.
4. **Format leak:** the model emits literal `[EMOTE:wave]` tags inside message text in several
   scenes (parse/prompt issue), and once referred to itself in third person.

## Gate (informational — Phase 1 is merged architecture, not a revertable config edit)
`eval_gain −0.003 ≤ 0.5` AND `new_lore_failures = 2` → both clauses fail. Recorded in
`phase1_sharedmem.json`. We do NOT revert the architecture; this measures it.

## Interpretation
Phase 1 **shifted the bottleneck** rather than raising the ceiling. Before: bots had no
awareness and broadcast classified ads. Now: bots are aware and *converse when there's a
conversation to join* (player present), but with no player they **echo** instead of advance,
and the underlying identities are clichéd. The memory plumbing is sound; the limiting
factors are now (a) anti-echo / novelty pressure, (b) clichéd identity templates, and
(c) ambient scenes lacking any goal/initiative structure.

## Concrete next levers (Phase 2 / next cycle)
1. **Anti-echo guard** — strengthen the prompt ("react, don't restate; add something new")
   and/or drop a turn when output is near-duplicate of an overheard line. Highest-value,
   directly targets the regression.
2. **Re-do the de-clichéing** now that memory is in — the cliché fix failed in cycle 2
   *without* memory; it may behave differently with conversational context, and it's the
   cleanest way to clear the lore/cliché problem (esp. the WotLK/emoji trips).
3. **Ambient goal/initiative structure** — no-player scenes need bots pursuing something
   (a stateful tick goal), not just hearing each other. This is the deeper Phase-2 work.
4. **Fix the `[EMOTE:...]` text leak** in parsing.

## State
`eval/bakeoff/phase1_sharedmem.json` + this report committed to local `master`. Brain
stopped; `ac-database` left up. Nothing pushed to any remote. Promotion/next-cycle choice
is the user's call.
