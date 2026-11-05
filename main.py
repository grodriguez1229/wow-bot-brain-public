"""
wow-bot-brain v3 — real people living in WoW, 2005.
Bots have lives, goals, social dynamics, and can request game actions.
"""

import asyncio
import os
import random
import time

from fastapi import FastAPI

import re

from config import (LOGIN_DELAY_MIN_S, LOGIN_GEN_BUDGET_S, OLLAMA_MODEL, HEARD_CONVO_WINDOW_S, SIGNATURE_RATE, CHAT_MAX_CHARS,
                    TICK_MAX_CHARS, HEARD_MAX_CHARS, REPLY_RATE, SILENCE_RATE, VOICE_TRANSFORM)
from models import EventRequest, EventResponse, WhisperOut, ChatRequest, TickRequest, BotResponse, ReflectRequest, HeardRequest, HeardReply, HeardResponse
from consolidate import consolidate_scene
from self_memory import consolidate_self
from sim.transcript import Scene, Turn
from db import (init_db, get_db, get_memory, get_memory_sheet, save_message,
                get_relationship, describe_relationship, get_bot_names)
from irl_budget import irl_allowed, note_ambient_line
import election as election_mod
from election import (is_pass, cap_hearers, note_bot_spoke, note_replied,
                      is_duplicate_line, note_fleet_line)
import personality as personality_mod
from personality import IRL_IDENTITIES, get_or_create_personality, pick_mood, pick_tick_activity
from llm import call_ollama, parse_response
from postfilter import clean_line, is_narration, is_self_intro, strip_asterisk_actions
from prompts import (CHAT_PROMPT, CHAT_LIFE_RULE_OPEN, CHAT_LIFE_RULE_GAME, TICK_PROMPT, build_action_rules,
                     build_motivation_line, build_irl_section, build_examples_section,
                     build_chat_log_section, build_tick_user_message, build_moments_section,
                     build_pairs_section)
import chat_log
import events
import friendship
import login_whisper
import history as shared_history
import presence
from ad_templates import make_ad
from typing_transform import transform
from voice import (SHAPE_HINT, SHAPE_MAX_SENTENCES, SHAPE_NUM_PREDICT, is_example_copy, pick_shape,
                   sample_examples, sample_reply_pairs, sample_whisper_pairs, shape_budget)
from capabilities import capabilities
from knowledge import build_knowledge_section, find_violations
from memory_prompt import build_nearby_section, build_relationship_section, build_self_section, build_identity_section

app = FastAPI(title="wow-bot-brain", version="3.0.0")

FRESH_NUDGE = ("\n\nSay something clearly different from what everyone else is saying — "
               "your own wording and angle, not the usual phrasing.")


NARRATION_NUDGE = ("\n\nWrite it as yourself typing in chat, first person \u2014 no narrating, "
                   "no describing your character in third person, no *actions*.")

KNOWLEDGE_NUDGE = ("\n\nStick to what your character knows at their level: no raids, zones or "
                   "dungeons you haven't reached, and nothing from later expansions.")

SELF_INTRO_NUDGE = ("\n\nDon't introduce yourself or state your own level, race or class. "
                    "Just answer.")


async def generate_deduped(gen, *, dedupe: bool, allow_silence: bool = False, decline=None,
                           max_len: int | None = None, bot_name: str = "", known_names=(),
                           silence_on_narration: bool = False, avoid=(), knowledge=None,
                           self_intro=None):
    """Generate one line via `gen("")`, post-filtered (emoji / mashed names / length).
    `decline` firing -> None. Third-person narration re-rolls once with NARRATION_NUDGE;
    if it persists: None when `silence_on_narration`, else asterisk actions are stripped.
    When `dedupe` is on and the line duplicates a recent fleet line, re-roll once with
    FRESH_NUDGE (only if that stays within 2 LLM calls); a still-duplicate line with
    `allow_silence` -> None. A near-copy of any `avoid` line (prompt examples, the line
    being replied to) counts as a duplicate too (R8). `knowledge(text)` returning violations
    (R2) re-rolls once with KNOWLEDGE_NUDGE; if they persist: None when
    `silence_on_narration`, else the line is kept. `self_intro(text)` True (R9) re-rolls
    once with SELF_INTRO_NUDGE; if it persists -> None on every lane. Records the emitted
    line in the fleet window."""
    calls = 0

    async def _gen(extra):
        nonlocal calls
        calls += 1
        r = await gen(extra)
        if r and r.get("message"):
            cleaned, flags = clean_line(r["message"], max_len=max_len, known_names=known_names)
            if flags:
                print(f"[filter] {bot_name or '?'} {','.join(flags)}")
            r["message"] = cleaned
        return r

    result = await _gen("")
    if decline is not None and decline(result):
        return None
    if result.get("message") and is_narration(result["message"], bot_name):
        print(f"[filter] {bot_name or '?'} narration")
        result = await _gen(NARRATION_NUDGE)
        if decline is not None and decline(result):
            return None
        if result.get("message") and is_narration(result["message"], bot_name):
            if silence_on_narration:
                return None
            result["message"] = strip_asterisk_actions(result["message"])
    if self_intro is not None and result.get("message") and self_intro(result["message"]):
        print(f"[filter] {bot_name or '?'} self_intro")
        result = await _gen(SELF_INTRO_NUDGE)
        if decline is not None and decline(result):
            return None
        if result.get("message") and self_intro(result["message"]):
            return None
    if knowledge is not None and result.get("message"):
        bad = knowledge(result["message"])
        if bad:
            print(f"[filter] {bot_name or '?'} knowledge {','.join(bad)}")
            result = await _gen(KNOWLEDGE_NUDGE)
            if decline is not None and decline(result):
                return None
            if silence_on_narration and result.get("message") and knowledge(result["message"]):
                return None

    def _dup(msg):
        return is_duplicate_line(msg) or is_example_copy(msg, avoid)

    if dedupe and result.get("message") and _dup(result["message"]):
        if calls < 2:
            result = await _gen(FRESH_NUDGE)
            if decline is not None and decline(result):
                return None
            if allow_silence and result.get("message") and _dup(result["message"]):
                return None
        elif allow_silence:
            return None
    # R9: a later re-roll (knowledge / fresh) can still come back as a self-intro.
    if self_intro is not None and result and result.get("message") and self_intro(result["message"]):
        print(f"[filter] {bot_name or '?'} self_intro (re-roll)")
        return None
    if dedupe and result and result.get("message"):
        note_fleet_line(result["message"])
    return result


def build_tick_state_line(activity: str | None, target: str | None, place: str) -> str:
    """One-line 'RIGHT NOW' anchor for the tick system prompt, from the bot's real state."""
    if activity == "in_combat":
        return f"RIGHT NOW: fighting{f' {target}' if target else ''} in {place}."
    if activity == "traveling":
        return f"RIGHT NOW: traveling through {place}."
    if activity == "resting":
        return f"RIGHT NOW: resting at an inn in {place}."
    if activity == "dead":
        return f"RIGHT NOW: dead in {place}, doing a corpse run."
    return ""


_NAMES_TTL_S = 300
_names_cache: dict = {"ts": float("-inf"), "names": frozenset()}


def known_bot_names() -> frozenset:
    """Bot names for the mashed-name post-filter; refreshed every few minutes."""
    now = time.monotonic()
    if now - _names_cache["ts"] > _NAMES_TTL_S:
        try:
            _names_cache.update(ts=now, names=frozenset(get_bot_names()))
        except Exception as e:
            print(f"[filter] known_bot_names refresh failed: {e}")
            _names_cache["ts"] = now
    return _names_cache["names"]

# Live self-reflection trigger: every Nth chat for a bot, distill its recent
# activity into an evolving self-view (fire-and-forget so the reply isn't blocked).
SELF_REFLECT_EVERY = 6
_chat_counts: dict[str, int] = {}
_self_tasks: set = set()


def _maybe_reflect_self(bot_name: str, who: str):
    if os.getenv("WBB_SELF_REFLECT", "1") != "1":
        return
    n = _chat_counts.get(bot_name, 0) + 1
    _chat_counts[bot_name] = n
    if n % SELF_REFLECT_EVERY != 0:
        return

    async def _run():
        try:
            applied = await asyncio.to_thread(consolidate_self, bot_name, who=who)
            if applied:
                print(f"[self] {bot_name} reflected: {applied}")
        except Exception as e:  # reflection is best-effort; never break chat
            print(f"[self] {bot_name} reflection failed: {e}")

    task = asyncio.create_task(_run())
    _self_tasks.add(task)
    task.add_done_callback(_self_tasks.discard)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    init_db()


# The player asked who/what the bot is: stating name/level/class is then an answer.
_ASKS_ABOUT_BOT = re.compile(r"\b(lvl|level|class|name|who r u|who are you)\b", re.IGNORECASE)
# Token floor whenever the reply may end with an invite tag (R9 P4); the char budget
# still keeps the visible text short.
ACTION_TAG_TOKENS = 32
_STRANGER = {"familiarity": 0, "label": "stranger", "notes": ""}


def _whisper_moments(bot_name: str, player: str) -> list[str]:
    """Stored shared moments for the whisper prompt (R9); best-effort, never breaks chat."""
    try:
        return [m["text"] for m in shared_history.moments_for(player, bot_name)]
    except Exception as e:
        print(f"[chat] {bot_name} moments read failed: {e!r}")
        return []


async def run_chat(req: ChatRequest, may_decline: bool = False, *, lane: str = "default") -> dict | None:
    p = get_or_create_personality(req.bot_name)
    heard = lane == "heard"
    # Relationship bookkeeping never breaks a reply. Heard replies don't touch friendship
    # until one is actually sent (add_chat decays first), so a silent hearer adds no row.
    try:
        if not heard:
            friendship.apply_decay(req.bot_name, req.player_name)
        rel = get_relationship(req.bot_name, req.player_name)
    except Exception as e:
        print(f"[chat] {req.bot_name} relationship read failed: {e!r}")
        rel = dict(_STRANGER, bot_name=req.bot_name, player_name=req.player_name)
    history = get_memory(req.bot_name, req.player_name)

    identity = next((i for i in IRL_IDENTITIES if i["id"] == p["identity_id"]), None)
    irl = p.get("irl") or {}
    llm_lane = "heard" if heard else "chat"
    irl_ok = irl_allowed() if heard else True     # whispers keep the full persona, unbudgeted
    mood = pick_mood(identity, irl_ok=irl_ok) if identity else "chill"
    who = (irl.get("who_core") or p["who"]) if heard else p["who"]

    # Build context section
    context_lines = []
    context_lines.append(f"TALKING TO: {req.player_name} ({describe_relationship(rel)})")
    if req.channel:
        context_lines.append(f"CHANNEL: {req.channel}")
    if req.location:
        context_lines.append(f"LOCATION: {req.location}")
    if p.get("guild_name"):
        context_lines.append(f"YOUR GUILD: {p['guild_name']}")
    if req.bot_in_group:
        context_lines.append("YOU ARE IN A GROUP")
    context_section = "\n".join(context_lines)

    # Build memory section (pairwise history + persistent relationship notes)
    if history:
        mem_lines = [f"{'Them' if msg['role'] == 'user' else 'You'}: {msg['content']}" for msg in history[-6:]]
        memory_section = "Recent chat with them:\n" + "\n".join(mem_lines)
    else:
        memory_section = ""
    rel_section = build_relationship_section(rel)
    if rel_section:
        memory_section = (memory_section + "\n" + rel_section).strip()

    # R9: whispers see only the shared history that actually happened, plus the
    # player's own recent words; ambient (heard) replies don't.
    if heard:
        moments_section = ""
    else:
        said = [m["content"] for m in history if m["role"] == "user"][-3:]
        moments_section = build_moments_section(_whisper_moments(req.bot_name, req.player_name), said)

    # Action rules — let the bot send a REAL party invite to the person it's talking to.
    # A real player will group with a stranger who asks. The C++ bridge executes
    # [ACTION:invite <name>] (emote tags still parse, but were removed from the prompt on purpose in R9: they read as NPC narration).
    caps = capabilities(p.get("motivation", ""), can_guild_invite=p.get("can_guild_invite", False))
    if os.getenv("WBB_GUILD_ACTIONS") != "1":
        caps.discard("guild_invite")
    # Ambient channel reactions (heard election) must never fire REAL party/guild
    # invites — a bot overhearing you in /say or General shouldn't pull you into a
    # group. Real invites are offered only in direct whispers (the consented 1:1 path).
    if heard:
        caps.discard("party_invite")
        caps.discard("guild_invite")
    action_rules = build_action_rules(req.player_name, caps=caps)

    # R8-style shape for the reply (R9): it sets the token/sentence/char budget.
    shape = pick_shape(req.channel or "WHISPER", reply=True, whisper=not heard)
    if heard:
        pairs = sample_reply_pairs(4, level=p["level"], faction=p["faction"])
        examples_section = build_pairs_section("HOW PEOPLE ANSWER EACH OTHER (earlier):", pairs)
    else:
        pairs = sample_whisper_pairs(4)
        examples_section = build_pairs_section("HOW PEOPLE WHISPER BACK (earlier):", pairs)

    system = CHAT_PROMPT.format(
        name=req.bot_name,
        level=p["level"],
        race=p["race"],
        class_name=p["class_name"],
        faction=p["faction"],
        who=who,
        typing_style=p["typing_style"],
        mood=mood,
        current_goal=p["current_goal"],
        motivation_line=build_motivation_line(p.get("motivation", "")),
        self_section=build_self_section(get_memory_sheet(req.bot_name, "self")),
        identity_section=build_identity_section(get_memory_sheet(req.bot_name, "identity")),
        context_section=context_section,
        memory_section=memory_section,
        moments_section=moments_section,
        nearby_section=build_nearby_section(
            [rl.model_dump() for rl in (req.recent_lines or [])]
        ),
        examples_section=examples_section,
        action_rules=action_rules,
        life_rule=CHAT_LIFE_RULE_GAME if (heard and not irl_ok) else CHAT_LIFE_RULE_OPEN,
    )

    system += "\n\n" + build_knowledge_section(p["level"], p["faction"])

    if heard:
        system += "\n\n" + build_irl_section(irl, allowed=irl_ok,
                                             signature_on=random.random() < SIGNATURE_RATE)

    if may_decline:                                                   # NEW
        system += ("\n\nThis message wasn't addressed to you. Reply ONLY if your character "
                   "genuinely has something to add. If not, reply with exactly: PASS")  # NEW

    system += f"\n\nYOUR REPLY: {SHAPE_HINT[shape]}. Just the message."

    num_predict = SHAPE_NUM_PREDICT[shape]
    if caps & {"party_invite", "guild_invite"}:
        num_predict = max(num_predict, ACTION_TAG_TOKENS)   # P4: room for [ACTION:invite X]
    max_len = min(shape_budget(shape), HEARD_MAX_CHARS if heard else CHAT_MAX_CHARS)

    async def gen(extra):
        raw = await call_ollama(system + extra, [], req.message, num_predict=num_predict,
                                max_sentences=SHAPE_MAX_SENTENCES[shape], lane=llm_lane)
        return parse_response(raw, req.channel)

    asked_about_bot = bool(_ASKS_ABOUT_BOT.search(req.message or ""))
    intro = None if asked_about_bot else (lambda t: is_self_intro(
        t, bot_name=req.bot_name, race=p["race"], class_name=p["class_name"], level=p["level"]))

    # Fleet dedup applies to ambient overheard replies (heard lane), not direct whispers.
    result = await generate_deduped(
        gen, dedupe=heard,
        decline=(lambda r: is_pass(r["message"])) if may_decline else None,
        max_len=max_len, bot_name=req.bot_name,
        known_names=known_bot_names(), silence_on_narration=heard,
        avoid=[t for pr in pairs for t in pr] + [req.message],
        knowledge=lambda t: find_violations(t, p["level"], allowed_from=req.message),
        self_intro=intro)

    if result is None or (heard and not result.get("message")):
        print(f"[{'heard' if heard else 'chat'}] {req.bot_name} stayed silent")
        return None

    if VOICE_TRANSFORM and result.get("message"):
        # R8: per-bot typing habits; whispers get the light version (caps/punctuation only).
        result["message"] = transform(result["message"], req.bot_name, light=not heard,
                                      protect=set(known_bot_names()) | {req.player_name},
                                      max_len=max_len)

    if heard:
        note_ambient_line(result["message"], irl.get("irl_terms") or ())

    # Log
    rel_label = rel["label"]
    print(f"[chat:{llm_lane}] {req.player_name} -> {req.bot_name} (L{p['level']} {p['race']} "
          f"{p['class_name']}, {p['identity_id']}, mood={mood}, rel={rel_label}, shape={shape})")
    print(f"  IN:  \"{req.message}\"")
    print(f"  OUT: \"{result['message']}\"")
    if result["actions"]:
        print(f"  ACT: {result['actions']}")

    save_message(req.bot_name, req.player_name, "user", req.message)
    save_message(req.bot_name, req.player_name, "assistant", result["message"])
    try:
        friendship.add_chat(req.bot_name, req.player_name)
    except Exception as e:
        print(f"[chat] {req.bot_name} relationship update failed: {e!r}")
    _maybe_reflect_self(req.bot_name, p["who"])

    return result


@app.post("/chat", response_model=BotResponse)
async def chat(req: ChatRequest):
    result = await run_chat(req)
    if result is None:          # R9: a reply that can't avoid a self-intro stays unsent
        return BotResponse(message="", channel=req.channel or "WHISPER")
    return BotResponse(**result)


def _heard_familiarity(speaker: str, bot_name: str) -> int:
    return get_relationship(bot_name, speaker).get("familiarity", 0)


def _heard_persona_text(bot_name: str) -> str:
    p = get_or_create_personality(bot_name)
    irl = p.get("irl") or {}
    who = irl.get("who_core") or p.get("who", "")
    return f"{who} {p.get('current_goal', '')}"


def _heard_recent_convo(speaker: str, bot_name: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM messages WHERE bot_name = ? AND player_name = ? "
        "AND timestamp >= datetime('now', ?) LIMIT 1",
        (bot_name, speaker, f"-{HEARD_CONVO_WINDOW_S} seconds")).fetchone()
    conn.close()
    return row is not None


def _cached_persona(bot_name: str) -> dict:
    """Personality from the in-process cache only (no DB/MySQL); {} if not loaded yet."""
    return personality_mod._personality_cache.get(bot_name) or {}


@app.post("/heard", response_model=HeardResponse)
async def heard(req: HeardRequest):
    hearers = cap_hearers([h.model_dump() for h in req.hearers], req.message)
    # R8: the overheard line joins the chat log so ticking bots can reply to it later.
    guild = next((_cached_persona(h["bot_name"]).get("guild_name") for h in hearers
                  if h.get("same_guild")), None) if req.channel.upper() == "GUILD" else None
    heard_id = chat_log.record_line(req.speaker, req.channel, req.message, faction=None,
                                    zone=req.location, guild=guild)
    elected = election_mod.elect(
        hearers, req.message, req.speaker, req.channel,
        get_familiarity=lambda b: _heard_familiarity(req.speaker, b),
        get_persona_text=_heard_persona_text,
        recent_convo=lambda b: _heard_recent_convo(req.speaker, b),
    )
    if elected:
        print(f"[heard] {req.speaker} @{req.channel}: elected "
              f"{[(e['bot_name'], e['tier']) for e in elected]}")

    async def one(e):
        creq = ChatRequest(bot_name=e["bot_name"], player_name=req.speaker,
                           message=req.message, channel=req.channel, location=req.location)
        try:
            return e["bot_name"], await run_chat(creq, may_decline=(e["tier"] == "candidate"), lane="heard")
        except Exception as exc:
            print(f"[heard] {e['bot_name']} failed: {exc}")
            return e["bot_name"], None

    start = time.monotonic()
    results = await asyncio.gather(*(one(e) for e in elected))
    elapsed = time.monotonic() - start
    if elapsed > 60:
        print(f"[heard] SLOW: {elapsed:.1f}s for {len(elected)} bots ({req.channel})")
    responses = []
    for bot_name, r in results:
        if r is None:
            continue
        note_replied(bot_name, req.channel)
        note_bot_spoke(bot_name, req.channel)
        bp = _cached_persona(bot_name)
        chat_log.record_line(bot_name, req.channel, r["message"], faction=bp.get("faction"),
                             zone=req.location, guild=bp.get("guild_name"), reply_to=heard_id)
        responses.append(HeardReply(bot_name=bot_name, **r))
    return HeardResponse(responses=responses)


_TOPIC_SEEDS = {
    "GENERAL": ["something about this zone", "a question you actually have", "a small complaint",
                "something that just happened to you", "your class or spec",
                "money or gear", "a dumb joke", "the quest you're on", "the server tonight"],
    "GUILD": ["guild banter", "your progress tonight", "asking guildies for a hand",
              "something that just happened to you", "a dumb joke"],
    "SAY": ["what's right in front of you", "the mob or quest you're on", "your health or mana",
            "the people around you"],
    "LFG": ["a group or dungeon for your level"],
    "TRADE": ["buying, selling or a crafting service"],
}


def build_tick_situation(activity: str | None, target: str | None, place: str, channel: str,
                         nearby_players=(), *, topic: bool = True, rng=None) -> str:
    """Short scene line for the tick user message (R8): where you are and what's going on."""
    rng = rng or random
    if activity == "in_combat":
        s = f"You're fighting{f' {target}' if target else ''} in {place}."
    elif activity == "dead":
        s = f"You just died in {place}."
    elif activity == "traveling":
        s = f"You're traveling through {place}."
    elif activity == "resting":
        s = f"You're at the inn in {place}."
    else:
        s = f"You're in {place}."
    if channel == "SAY" and nearby_players:
        s += f" {', '.join(list(nearby_players)[:3])} standing near you."
    if topic and activity not in ("in_combat", "dead"):
        s += f" Maybe: {rng.choice(_TOPIC_SEEDS.get(channel, _TOPIC_SEEDS['GENERAL']))}."
    return s


def _emit_tick(bot_name: str, channel: str, shape: str, msg: str, *, target: dict | None,
               faction, zone, guild, irl_terms=()) -> None:
    """Record + log + R3 accounting for an emitted tick line. Log format (R8):
    [tick] <bot> -> <CH> [<shape>] (re <speaker>): "<msg>"   (both tags parse as optional)."""
    chat_log.record_line(bot_name, channel, msg, faction=faction, zone=zone, guild=guild,
                         reply_to=target["id"] if target else None)
    re_tag = f" (re {target['speaker']})" if target else ""
    print(f'[tick] {bot_name} -> {channel} [{shape}]{re_tag}: "{msg}"')
    note_bot_spoke(bot_name, channel)
    note_ambient_line(msg, irl_terms)


@app.post("/tick", response_model=BotResponse)
async def tick(req: TickRequest):
    try:
        presence.note_tick(req.bot_name, zone=req.location, subzone=req.subzone,
                           activity=req.activity, nearby_players=req.nearby_players or [])
    except Exception as e:      # presence is bookkeeping; never silence the bot over it
        print(f"[presence] error {req.bot_name}: {e!r}")
    # R8: let channels breathe. A share of ticks says nothing, before any LLM work.
    if random.random() < SILENCE_RATE:
        print(f"[tick] {req.bot_name}: (silent, breathe)")
        return BotResponse(message="", channel="SAY")

    p = get_or_create_personality(req.bot_name)
    identity = next((i for i in IRL_IDENTITIES if i["id"] == p["identity_id"]), None)
    irl = p.get("irl") or {}
    irl_ok = irl_allowed()
    mood = pick_mood(identity, irl_ok=irl_ok) if identity else "chill"

    location_str = req.location or "somewhere"
    guild = p.get("guild_name") or req.bot_guild or ""
    faction = p.get("faction")
    nearby_players = req.nearby_players or []
    nearby_bots = req.nearby_bots or []
    place = req.subzone or location_str

    # R8 reply-first: answer a recent line this bot could see (not mid-fight / dead).
    target = None
    if REPLY_RATE > 0 and req.activity not in ("in_combat", "dead"):
        cands = chat_log.reply_candidates(req.bot_name, faction=faction, zone=req.location,
                                          guild=guild, nearby=nearby_bots + nearby_players)
        if cands and random.random() < REPLY_RATE:
            target = chat_log.pick_reply_target(cands)

    if target:
        channel = target["channel"]
        shape = pick_shape(channel, reply=True)
    else:
        activity = pick_tick_activity(p["level"], p["class_name"], location_str, bool(guild),
                                      bias_say=bool(nearby_players), motivation=p.get("motivation", ""),
                                      activity=req.activity, target=req.target, subzone=req.subzone,
                                      irl_ok=irl_ok)
        channel = activity["channel"]
        shape = pick_shape(channel)

    irl_terms = irl.get("irl_terms") or ()
    if shape == "ad":
        ad = make_ad(channel, req.bot_name, p["level"], p["class_name"], faction)
        if ad:
            note_fleet_line(ad)
            _emit_tick(req.bot_name, channel, shape, ad, target=None, faction=faction,
                       zone=req.location, guild=guild, irl_terms=irl_terms)
            return BotResponse(message=ad, channel=channel)
        shape = "question"            # nothing fits this level -> a short LLM question

    examples = sample_examples(channel, shape, level=p["level"], faction=faction)
    pairs = sample_reply_pairs(3, level=p["level"], faction=faction) if target else None
    if target:
        nearby_section = build_chat_log_section(
            channel, [(e["speaker"], e["text"]) for e in chat_log.recent_context(target)])
    else:
        nearby_section = build_nearby_section([rl.model_dump() for rl in (req.recent_lines or [])])

    system = TICK_PROMPT.format(
        name=req.bot_name,
        level=p["level"],
        race=p["race"],
        class_name=p["class_name"],
        faction=p["faction"],
        who=irl.get("who_core") or p["who"],
        typing_style=p["typing_style"],
        mood=mood,
        current_goal=p["current_goal"],
        motivation_line=build_motivation_line(p.get("motivation", "")),
        state_line=build_tick_state_line(req.activity, req.target, place),
        self_section=build_self_section(get_memory_sheet(req.bot_name, "self")),
        identity_section=build_identity_section(get_memory_sheet(req.bot_name, "identity")),
        irl_section=build_irl_section(irl, allowed=irl_ok, signature_on=random.random() < SIGNATURE_RATE),
        examples_section=build_examples_section(channel, examples, pairs),
        nearby_section=nearby_section,
    ) + "\n" + build_knowledge_section(p["level"], faction)
    situation = build_tick_situation(req.activity, req.target, place, channel, nearby_players,
                                     topic=target is None)
    user_msg = build_tick_user_message(channel, SHAPE_HINT[shape], situation,
                                       reply_to=(target["speaker"], target["text"]) if target else None)

    async def gen(extra):
        raw = await call_ollama(system + extra, [], user_msg,
                                num_predict=SHAPE_NUM_PREDICT[shape],
                                max_sentences=SHAPE_MAX_SENTENCES[shape])
        return parse_response(raw, channel)

    names = known_bot_names()
    avoid = examples + [t for pr in (pairs or []) for t in pr] + ([target["text"]] if target else [])
    result = await generate_deduped(gen, dedupe=True, max_len=min(shape_budget(shape), TICK_MAX_CHARS),
                                    bot_name=req.bot_name, known_names=names,
                                    silence_on_narration=True, avoid=avoid,
                                    knowledge=lambda t: find_violations(
                                        t, p["level"], allowed_from=target["text"] if target else ""))
    if not result or not result.get("message"):
        print(f"[tick] {req.bot_name} -> {channel}: (silent)")
        return BotResponse(message="", channel=channel)   # C++ bridge skips empty ticks
    msg = result["message"]
    if VOICE_TRANSFORM:
        protect = set(names) | ({target["speaker"]} if target else set())
        msg = transform(msg, req.bot_name, protect=protect, max_len=TICK_MAX_CHARS)
    result["message"] = msg
    result["channel"] = channel
    _emit_tick(req.bot_name, channel, shape, msg, target=target, faction=faction,
               zone=req.location, guild=guild, irl_terms=irl_terms)
    return BotResponse(**result)


@app.post("/event", response_model=EventResponse)
async def event(req: EventRequest):
    """R9: world events from the worldserver. Never 500s on bad game input."""
    if req.type == "ping":
        return EventResponse()
    try:
        events.ingest(req.model_dump())
        print(f"[event] {req.type} {req.player} L{req.level} {req.zone} "
              f"inst={req.instance} group={','.join(req.group)}")
    except Exception as e:
        print(f"[event] {req.type} {req.player} ingest failed: {e!r}")
    if req.type != "login":
        return EventResponse()
    try:
        return EventResponse(whispers=await _login_whispers(req))
    except Exception as e:
        print(f"[r9] login error {req.player}: {e!r}")
        return EventResponse()


async def _login_whispers(req: EventRequest) -> list[WhisperOut]:
    """Plan, write and record login whispers. Each planned whisper is recorded now (history
    event + reply thread), so a relog before delivery hits the per-pair cooldown."""
    started = time.monotonic()
    plans = login_whisper.plan_login(req.player, level=req.level or 1,
                                     faction=req.faction or "")
    if not plans:
        return []
    for pl in plans:
        shared_history.add_event(req.player, pl.bot, "login_whisper", detail=pl.kind)

    def fallback_opener(pl):
        return {"message": login_whisper._fallback(pl, random), "moment_ids": [], "actions": []}

    async def one(pl):
        try:
            return await login_whisper.generate_opener(pl, req.player, player_zone=req.zone)
        except Exception as e:
            print(f"[r9] login error opener {pl.bot} -> {req.player}: {e!r}; using fallback")
            return fallback_opener(pl)

    # C++ waits ~75 s for /event: bound generation, and never drop a recorded plan.
    tasks = [asyncio.ensure_future(one(pl)) for pl in plans]
    await asyncio.wait(tasks, timeout=LOGIN_GEN_BUDGET_S)
    openers = []
    for pl, t in zip(plans, tasks):
        if t.done() and not t.cancelled():
            openers.append(t.result())
        else:
            t.cancel()
            print(f"[r9] login opener {pl.bot} -> {req.player} over budget; using fallback")
            openers.append(fallback_opener(pl))
    elapsed = time.monotonic() - started
    out: list[WhisperOut] = []
    for pl, op in zip(plans, openers):
        if not op or not op.get("message"):
            continue
        delay = int(max(LOGIN_DELAY_MIN_S, pl.delay_s - elapsed))
        save_message(pl.bot, req.player, "assistant", op["message"])
        if op.get("moment_ids"):
            shared_history.mark_cited(op["moment_ids"])
        print(f'[whisper] {pl.bot} -> {req.player} [{pl.kind}] (+{delay}s): "{op["message"]}"')
        out.append(WhisperOut(bot_name=pl.bot, whisper_to=req.player, message=op["message"],
                              actions=op.get("actions") or [], delay_s=delay))
    return out


@app.get("/personalities")
def list_personalities():
    conn = get_db()
    rows = conn.execute(
        "SELECT bot_name, race, class_name, level, identity_id, current_goal, guild_name FROM bot_personalities ORDER BY bot_name"
    ).fetchall()
    conn.close()
    return {"bots": [dict(r) for r in rows]}


@app.get("/personality/{bot_name}")
def get_personality(bot_name: str):
    return get_or_create_personality(bot_name)


@app.get("/relationships/{bot_name}")
def get_relationships(bot_name: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM relationships WHERE bot_name = ? ORDER BY familiarity DESC",
        (bot_name,)
    ).fetchall()
    conn.close()
    return {"relationships": [dict(r) for r in rows]}


@app.post("/reflect")
def reflect(req: ReflectRequest):
    s = req.scene
    scene = Scene(
        scene_id=s.scene_id, location=s.location, channel=s.channel,
        participants=s.participants,
        turns=[Turn(idx=t.idx, speaker=t.speaker, channel=t.channel,
                    text=t.text, actions=t.actions) for t in s.turns],
    )
    applied = consolidate_scene(scene, bots=req.bots)
    return {"applied": len(applied), "updates": applied}


@app.post("/reflect_self/{bot_name}")
def reflect_self(bot_name: str):
    """Force one self-reflection pass for a bot (manual / future scheduler)."""
    p = get_or_create_personality(bot_name)
    applied = consolidate_self(bot_name, who=p.get("who", ""))
    return {"bot": bot_name, "applied": applied,
            "self": get_memory_sheet(bot_name, "self")}


@app.get("/health")
def health():
    return {"status": "ok", "model": OLLAMA_MODEL, "version": "3.0.0"}
