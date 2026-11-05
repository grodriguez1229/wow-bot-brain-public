# Self-Improving Pipeline for wow-bot-brain — Design

**Date:** 2026-06-10
**Status:** Design approved; step 1 (Foundation) starting.
**Project:** `~/wow-bot-brain` (AzerothCore AI world-simulation "brain")

## Goal

A multi-day, mostly-unattended loop that continuously tunes the bot world-simulation
toward **more believable emergent social life** — bots that pursue intentions across
turns, respond to each other, form relationships, and follow through on actions —
while never degrading the world the user actually plays in.

The local Ollama model (`qwen3.5:9b`) runs the cheap, continuous **bot actors**;
**Claude (via local Claude Code)** acts as the periodic **judge + optimizer**.

## Key discovered constraints (ground truth, 2026-06-10)

These reshaped the design and must not be re-litigated by guesswork:

1. **Bots do not talk to each other in the live game.** Both chat hooks in
   `mod-playerbots/src/Script/Playerbots.cpp` (`OnPlayerCanUseChat`, lines ~288 and
   ~346) gate on `!GetPlayerbotAI(player)` — a bot only ever responds to a *real
   human*. `/chat` fires only on human speech (~30% chance a nearby bot answers
   SAY/YELL; ~20% for Trade/LFG/General). `/tick` fires autonomous one-liners on a
   timer; `nearby_bots` is passed but is only *names*, never another bot's words.
   So "emergent social life" cannot emerge unattended in the live game today.
2. **The percentage gates + proximity + "pick one random responder" logic live in
   C++, not the brain.** The brain (FastAPI `:5000`) answers every request; it knows
   nothing about the gates. The C++ `LlmBridge` is merely a *client* of the brain.
3. **`personalities/*.yaml` (Sylvara/Razak/Brumdar) are DEAD CODE.** Nothing in the
   running app reads them. The live personality system is the 16 `IRL_IDENTITIES` in
   `personality.py` ("real people playing WoW in 2005"). The yaml files also
   contradict that design (lore-RP fantasy chars). The loop must NOT target them.
4. **`IRL_IDENTITIES` content is copied into the `bot_personalities` DB row at
   creation.** Editing the identity list does not retroactively change existing bots;
   only a fresh DB makes identity/prompt changes take effect.
5. **Not a git repo yet** — versioning/rollback requires `git init` first.
6. **Billing:** Claude Code is covered by the Pro plan; the Anthropic **API is
   pay-per-token** (reserved for the HA voice assistant). **Cloud** scheduled routines
   cannot reach the LAN/local files. => the judge must be **local Claude Code**.

## Decisions

- **Primary eval target:** emergent social life (not just per-line quality).
- **Loop substrate:** an **offline Python scene simulator** — a sibling client of the
  brain that drives `/chat` + `/tick` bot-to-bot directly, bypassing the C++ gates.
  Fast, reproducible, cheap, fully within the brain's edit scope.
- **Isolation:** two brain instances — **production** (`:5000`, frozen good config,
  prod DB, what the user plays against) and **experiment** (candidate config,
  throwaway DB, what the loop tunes). They share only Ollama (one GPU). The loop
  throttles/yields to live traffic.
- **Live toggle:** the live world normally points at production; a one-step toggle can
  point it at the candidate config to watch progress, then back. (User: "both, at
  different times.")
- **Edit scope (per cycle):** data + prompts + **whitelisted logic** — `IRL_IDENTITIES`
  content, prompt templates (`prompts.py`), goal/activity text, `llm.py` knobs
  (temperature, num_predict, truncation), **and** the sim **orchestration policy**
  (turn-taking, response odds, thread depth, action follow-through), since that is
  where emergent dynamics live. Anything outside the whitelist is rejected before
  apply. NOT C++ (that is a separate one-time manual edit). NOT the dead yaml files.
- **Judge + optimizer:** local Claude Code on a timer (persistent `/loop` session or a
  local cron invoking `claude -p` headless). Not the API, not a cloud routine.
- **Actor model:** keep local Ollama. `qwen3.5:9b` for now; treat model choice as an
  explicit **eval axis** to be measured (quick eyeball end of step 2; formal scored
  comparison in step 3), accounting for the speed↔quality tradeoff.

## Architecture & data flow

```
 LIVE GAME (when user logs in)
   worldserver ──toggle──► production brain (:5000) ── frozen good config + prod DB ┐
                                                                                     ├─► Ollama
 TUNING LOOP                                                                         │   (1 GPU,
   sim harness ──► experiment brain ── candidate config + throwaway DB ─────────────┘   qwen3.5:9b)
        │                 │
        │            /chat /tick driven bot-to-bot in Python
        ▼
   scene transcripts ──► local Claude Code judge+optimizer
                              ├─ score scenes (rubric)
                              ├─ propose + apply one bounded edit (whitelist)
                              ├─ smoke test + held-out eval + git commit/revert
                              └─ trigger next sim batch
```

## Components

### B. Offline scene simulator
Stages **scenes** (e.g. "3 bots + 1 synthetic player, Westfall, LFG context, 12
turns"). Picks who speaks, feeds each speaker's output as the next bot's `/chat`
input, runs `/tick` for ambient chatter, records an **ordered scene-level transcript**
(speaker, channel, text, `[ACTION:]`). Runs against a **throwaway DB seeded fresh each
run** (see constraint 4). The **orchestration policy** is an explicit Python artifact
and one of the loop's editable levers.

### C. Eval signal — judge rubric
Claude scores each scene 1–5 per dimension with a one-line justification:
- **Believable intentions** — goals pursued across turns
- **Turn-taking realism** — responds to what was just said; no monologue/talking-past
- **Relational continuity** — exchanges build; shared history referenced
- **Initiative & follow-through** — `[ACTION:]` well-motivated and reciprocated
- **In-character + level/lore consistency** — *gate*: a violation (anachronism,
  AI-reveal, wrong-level knowledge) caps the scene score
- **Voice distinctness** — identities stay recognizably different
Output = weighted scene score (for gating) **plus** a diagnosis + one concrete edit
proposal (the optimizer role).

### D. Optimize step
Each cycle the optimizer proposes **one** whitelisted change, applies it to the
**experiment** config, and re-runs the sim. Whitelist enforced by config; out-of-scope
edits rejected before apply.

### E. Anti-degradation
1. **git** — every cycle is one commit; rollback = `git revert`.
2. **Promotion gate** — a candidate is kept only if it (a) passes a **smoke test**
   (N scenes crash-free), (b) beats current best on a **held-out scene set** it could
   not see during optimization (anti-overfit), and (c) clears the lore/level gate.
   Fail → auto-revert.
3. **Golden anchor set** — fixed human-blessed scenes re-scored every cycle; if the
   judge's scores on these drift, that signals judge drift / reward-hacking → loop
   pauses for human review.
4. **Live world never auto-changes** — promotion to the production brain is a separate,
   explicit, human-approved step. The loop only promotes within the experiment lane.

### F. Orchestration, cadence & billing
- **Sim harness:** plain local background process (Python + Ollama; no Claude). Runs
  continuously.
- **Judge + optimizer:** local Claude Code on a timer (`/loop` session or local cron
  `claude -p`). Local = file/git/LAN access; Claude Code = Pro-covered.
- **Cadence:** sim runs continuously; judge wakes ~every 30–60 min for one optimize
  cycle. Tunable.

## Build order (each its own spec → plan → build)

1. **Foundation:** `git init` + `.gitignore` + baseline commit; experiment/prod brain
   split; isolated DBs; config-snapshot mechanism; live-world toggle.
2. **Scene simulator** + transcript format (offline, no Claude yet). *End: quick
   multi-model eyeball.*
3. **Judge rubric + scoring** (Claude Code reads transcripts → scores); validate
   against the user's taste on hand-made scenes. *Formal actor-model comparison here.*
4. **Optimize + gates** (edit → smoke test → held-out eval → git).
5. **Orchestration / cadence** for unattended multi-day operation.
6. *(Optional, decoupled, later)* one-time C++ edit to enable bot↔bot chat **in the
   live game**, once a sim-tuned config is worth watching live.

## Out of scope

- Security/ops hardening of the brain (plaintext creds, local-only exposure) — this is
  an experimental sim, explicitly not an ops/security concern.
- Editing the dead `personalities/*.yaml` files.
- Anthropic API usage for the loop (reserved for the HA voice assistant).
