# Session report — Bot Evolution Slice 1 (council engine + accelerated-life)

**When:** overnight 2026-06-15 (early AM). Built while you slept, per standing autonomy.
**Branch:** `evolution-council` (off `master`). **Nothing merged to master. Nothing touched live.**
**Tests:** 157 passing. **Live prod brain (`:5000`) untouched and still up the whole time.**

## What you asked for

Bots that **genuinely evolve beyond their base personality** — and you liked the idea of a
**council of judges with different personalities**. We brainstormed it down to: the council
is the **ENGINE** of growth (not just a critic), evolution is developed **offline** in an
accelerated "compress many days into minutes" harness, and the game world stays vanilla-
locked while **the person behind the keyboard can talk about anything** (modern history,
real life, etc.).

This was scoped as **slice 1 of 4** (full plan in the spec). Slice 1 = a thin end-to-end
vertical slice: *watch one bot visibly become a different but believable person, fast.*

## What I built (all TDD/BDD)

- **Writable identity layer** — a new `kind='identity'` in `bot_memory`: a growing set of
  facets `{subject, content, weight}` that *augments* the frozen template and feeds a new
  `WHO YOU'VE BECOME` prompt section. Pruned by conviction (weight), cap 16.
- **`council.py` — the engine.** Three diverse persona "lenses" (**Edge** = sharper
  opinions, **Heart** = relationships, **Arc** = life-arc continuity) each PROPOSE nudges;
  a SYNTHESIS step reconciles the deliberately-conflicting nudges into identity edits.
  Pure parsers + injectable model seams (Ollama by default; a **Claude backend can drop in
  later** behind the same signatures — the fan-out critique agents your notes anticipated).
- **`sim/accelerated_life.py` — the harness.** A "day" = live a rotating scene (your sim
  substrate) + one council reflection. Runs N days offline in minutes; identity +
  relationships accumulate in a throwaway `/tmp` DB.
- **Prompt reframing (experiment brain only):** relaxed "real person in 2005" → game-
  locked / person-open, per your call.

Docs: spec `docs/superpowers/specs/2026-06-15-evolution-council-accelerated-life-design.md`,
plan `docs/superpowers/plans/2026-06-15-evolution-council-accelerated-life.md`.

## What actually happened — two 10-day runs (Geysse, L19 Dwarf Rogue)

**It works.** Geysse visibly became a different, believable person both times:
- **Run 1** (`eval/evolution/geysse1/REPORT.md`): a burned-out night-shift worker — bonded
  with **Lynea**, developed a "done with mining for gold" opinion, a "happy to be here even
  though I'm always behind" arc. Relationship + opinion + life-arc all surfaced; the
  vanilla game-gate held (Deadmines, Wailing Caverns, iron ore — all period-correct).
- **Run 2** (`eval/evolution/geysse2/REPORT.md`): a zen solitary grinder — "saving every
  copper for the next skill cap, pacing the windmills listening to the wind." Distinct,
  coherent, evolved.

**Honest findings (and a correction to my own first read):**
1. **It consolidates — it is NOT additive-only.** My first glance said "changed=0,
   dropped=0," but that was a *metric artifact*: the day-0-vs-day-N diff is always
   all-"added" because day 0 identity is blank. The **day-over-day trail** (now shown as a
   table in each REPORT.md) tells the truth: each day applies 4–9 edits but net facet count
   barely moves and sometimes drops — i.e. the engine **revises/merges existing facets and
   occasionally sheds them**. Facet count self-stabilizes ~9–13, under the cap.
2. **Run 1 over-fixated** on one motif ("bread and cheese") and inflated weights
   (8 of 11 facets pegged at max weight 5). I made one disciplined fix — told the synthesis
   to consolidate duplicates, shed stale facets, keep the identity diverse, and reserve
   weight 5 for a few core traits.
3. **The fix helped where it could:** run 2 had **1** max-weight facet instead of 8, a
   healthy 2–4 spread, and a less compulsive probe. **Kept that change.**
4. **Residual wrinkles** (for the next cycle, not fixed): cross-subject duplication
   (e.g. `dogs`/`mutts`, `copper`/`saving_copper` — same idea, two keys); and a minor
   `[GUS:deadmines invite]` action-tag leaked into one probe (a `parse_response` gap).

**Caveat on the A/B:** a fresh DB re-rolls the base persona, so run 1 (weekend_warrior) vs
run 2 (quiet_grinder) isn't a clean *content* comparison — but the *structural* metrics
(weight spread, facet count, consolidation) are comparable, and that's where the win is.

## Reproduce / re-run

```bash
cd ~/wow-bot-brain && git checkout evolution-council
# game DB must be up (it is): docker start ac-database
rm -f /tmp/wbb-evo.db
WBB_DB_PATH=/tmp/wbb-evo.db WBB_SELF_REFLECT=0 WBB_GUILD_ACTIONS=1 \
  setsid nohup venv/bin/uvicorn main:app --host 127.0.0.1 --port 5001 >/tmp/wbb-evo-brain.log 2>&1 &
WBB_DB_PATH=/tmp/wbb-evo.db venv/bin/python -m sim.accelerated_life \
  --bot Geysse --days 10 --brain-url http://127.0.0.1:5001 --run myrun
cat eval/evolution/myrun/REPORT.md
# stop the experiment brain by PID (NEVER pkill uvicorn — that would kill prod :5000):
kill $(ss -ltnp | grep ':5001' | grep -oP 'pid=\K[0-9]+' | head -1)
```

## Your call / where this goes next

Slice 1 is done and verified; **promotion to the live game is your decision** (it's not
merged). Natural next steps, roughly the remaining sub-projects we scoped:
- **Sub-project 3 — evolution judging + guardrails:** turn the council into a *critic* too,
  so we can *measure* "is this drift good / did it go off the rails" instead of eyeballing.
  This is the right tool to settle the duplication/fixation tuning properly (avoids the
  eyeball-calibration trap). **I'd do this next.**
- **Sub-project 2 — richer substrate:** activate `event` memory + recency so life-arc /
  relationships have more fuel.
- **Then live promotion (sub-project 4):** wire the council into the `:5000` brain with a
  scheduled reflection; adopt the game-locked/person-open prompt reframe live.

Want me to (a) start sub-project 3 (the judge/guardrails), (b) tune the duplication issue
now with a quick measured loop, or (c) promote slice 1 to live and watch real bots drift?
