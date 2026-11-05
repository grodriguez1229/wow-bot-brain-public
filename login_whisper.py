"""Login whispers from friend bots (R9).

plan_login decides who (at most LOGIN_WHISPER_MAX friend bots, usually none or one), what
kind (callback / invite / checkin) and when (a human delay). generate_opener writes the
line, grounded only in stored shared history; anything it can't ground twice falls back to
an authored opener, so it never invents a shared past.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

import db
import friendship
import history
import personality
import presence
from config import (FRIENDS_ENABLED, INVITE_LEVEL_SPREAD, KIND_WEIGHTS, LOGIN_DELAY_MAX_S,
                    LOGIN_DELAY_MIN_S, LOGIN_WHISPER_COOLDOWN_S, LOGIN_WHISPER_MAX,
                    LOGIN_WHISPER_RATE, LONG_ABSENCE_DAYS, RUN_OFFER_MIN_GAP, RUN_OFFER_RATE,
                    SECOND_WHISPER_RATE, VOICE_TRANSFORM, WHISPER_MAX_CHARS)
from knowledge import (canonical_place, dungeons_for_level, find_violations, mentioned_places,
                       ungrounded_mentions, zones_for_level)
from llm import call_ollama, parse_response
from postfilter import clean_line, is_narration, is_self_intro
from prompts import (WHISPER_OPENER_PROMPT, build_moments_section, build_opener_examples_section,
                     build_opener_kind_instruction, build_opener_user_message)
from typing_transform import transform
from voice import is_example_copy
from voice_examples import OPENER_EXAMPLES, OPENER_FALLBACKS, OPENER_LONG_ABSENCE_EXAMPLES

BUSY = ("in_combat", "dead")
DAY_S = 86400
OPENER_EXAMPLES_SHOWN = 6
LONG_ABSENCE_FALLBACK = "where u been"

RETRY_NUDGE = {
    "empty": "",
    "narration": "\n\nType it as yourself, first person. No narrating, no *actions*.",
    "self_intro": "\n\nThey know you. Don't introduce yourself or state your own level, race or class.",
    "knowledge": "\n\nOnly mention places written above.",
    "ungrounded": "\n\nOnly mention places written above. Never make up something you did together.",
    "copy": "\n\nUse your own words, not one of the example lines.",
}


@dataclass
class Plan:
    bot: str
    kind: str                     # callback | invite | checkin
    delay_s: int
    invite: dict | None           # {"type": "quest"|"run", "place": str}
    long_absence_days: int | None


# ── planning ────────────────────────────────────────────────────────────────

def invite_option(bot_p: dict, bot_state: dict | None, player_level: int, player_faction: str,
                  rng) -> dict | None:
    """Something the player can join right now: questing in a zone at the player's level, or
    a dungeon run when the bot is far enough above them. Never a raid (raids aren't in the
    dungeon table)."""
    if not bot_state or bot_state.get("activity") in BUSY:
        return None
    bot_level = int(bot_p.get("level") or 1)
    zone = canonical_place(bot_state.get("zone") or "")
    if (abs(bot_level - player_level) <= INVITE_LEVEL_SPREAD and zone
            and zone in zones_for_level(player_level, player_faction)):
        return {"type": "quest", "place": zone}
    if bot_level - player_level >= RUN_OFFER_MIN_GAP and rng.random() < RUN_OFFER_RATE:
        dungeons = dungeons_for_level(player_level, player_faction)
        if dungeons:
            return {"type": "run", "place": rng.choice(dungeons)}
    return None


def _pair_bots(player: str) -> list[str]:
    """Bots that already have a relationships row with `player` (never creates rows)."""
    conn = db.get_db()
    try:
        rows = conn.execute("SELECT bot_name FROM relationships WHERE player_name = ?"
                            " ORDER BY bot_name", (player,)).fetchall()
    finally:
        conn.close()
    return [r["bot_name"] for r in rows]


def _candidates(player: str, faction: str, now: float) -> list[tuple[str, dict, dict, int]]:
    out = []
    for bot in _pair_bots(player):
        if not presence.is_online(bot, now=now):
            continue
        st = presence.state(bot)
        if not st or st.get("activity") in BUSY:
            continue
        try:
            p = personality.get_or_create_personality(bot)
        except Exception as e:
            print(f"[friends] {bot} persona read failed: {e!r}")
            continue
        if p.get("faction") != faction:
            continue
        if history.count_events(player, bot, "login_whisper",
                                since=now - LOGIN_WHISPER_COOLDOWN_S) > 0:
            continue
        if not friendship.is_whisper_eligible(bot, player, now=now):
            continue
        fam = db.get_relationship(bot, player).get("familiarity") or 0
        out.append((bot, p, st, fam))
    return out


def _long_absence_days(player: str, now: float) -> int | None:
    seen = history.player_seen(player)
    last = (seen or {}).get("last_logout")
    if last is None or now - last < LONG_ABSENCE_DAYS * DAY_S:
        return None
    return int((now - last) // DAY_S)


def _pick_kind(player: str, bot: str, p: dict, st: dict, level: int, faction: str,
               rng) -> tuple[str, dict | None]:
    invite = invite_option(p, st, level, faction, rng)
    kinds = ["checkin"]
    if history.moments_for(player, bot, limit=1):
        kinds.append("callback")
    if invite:
        kinds.append("invite")
    weights = [KIND_WEIGHTS.get(k, 0) for k in kinds]
    if not any(weights):
        return "checkin", None
    kind = rng.choices(kinds, weights=weights, k=1)[0]
    return kind, (invite if kind == "invite" else None)


def plan_login(player: str, *, level: int, faction: str, rng=None, now=None) -> list[Plan]:
    """Which friend bots whisper `player` after this login, and how. Usually [] or one."""
    if not FRIENDS_ENABLED:
        return []
    if LOGIN_WHISPER_MAX <= 0:
        print(f"[friends] login {player}: -> none (max={LOGIN_WHISPER_MAX})")
        return []
    rng = rng or random
    now = time.time() if now is None else now
    cands = _candidates(player, faction, now)
    names = [c[0] for c in cands]
    if not cands:
        print(f"[friends] login {player}: eligible=[] -> none (no eligible friend)")
        return []
    roll = rng.random()
    if roll >= LOGIN_WHISPER_RATE:
        print(f"[friends] login {player}: eligible={names} roll={roll:.2f} -> none (rate)")
        return []
    picked = [_weighted_pick(cands, rng)]
    rest = [c for c in cands if c[0] != picked[0][0]]
    if rest and LOGIN_WHISPER_MAX >= 2 and rng.random() < SECOND_WHISPER_RATE:
        picked.append(_weighted_pick(rest, rng))
    absence = _long_absence_days(player, now)
    plans: list[Plan] = []
    for i, (bot, p, st, _fam) in enumerate(picked[:LOGIN_WHISPER_MAX]):
        kind, invite = _pick_kind(player, bot, p, st, level, faction, rng)
        delay = (rng.randint(LOGIN_DELAY_MIN_S, LOGIN_DELAY_MAX_S) if i == 0
                 else plans[0].delay_s + rng.randint(30, 90))
        plans.append(Plan(bot=bot, kind=kind, delay_s=delay, invite=invite,
                          long_absence_days=absence))
    desc = ", ".join(f"{pl.bot}:{pl.kind}@{pl.delay_s}s" for pl in plans)
    print(f"[friends] login {player}: eligible={names} roll={roll:.2f} -> [{desc}]")
    return plans


def _weighted_pick(cands, rng):
    return rng.choices(cands, weights=[max(1, c[3]) for c in cands], k=1)[0]


# ── opener ──────────────────────────────────────────────────────────────────

def _long_absent(plan: Plan) -> bool:
    return bool(plan.long_absence_days and plan.long_absence_days >= LONG_ABSENCE_DAYS)


def _fallback(plan: Plan, rng) -> str:
    pool = list(OPENER_FALLBACKS.get(plan.kind) or OPENER_FALLBACKS["checkin"])
    if not _long_absent(plan):
        pool = [x for x in pool if x != LONG_ABSENCE_FALLBACK] or ["hey"]
    return rng.choice(pool)


def _said(bot: str, player: str) -> list[str]:
    return [m["content"] for m in db.get_memory(bot, player) if m["role"] == "user"][-3:]


async def generate_opener(plan: Plan, player: str, *, player_zone: str | None,
                          rng=None) -> dict:
    """A short opener for `plan`, grounded only in stored shared history, the player's own
    recent words, their zone and the invite place. Always returns a message: the model's
    line, or an authored fallback after two failed attempts."""
    rng = rng or random
    p = personality.get_or_create_personality(plan.bot)
    level = int(p.get("level") or 1)
    moments = history.moments_for(player, plan.bot)
    said = _said(plan.bot, player)
    place = (plan.invite or {}).get("place") if plan.kind == "invite" else None
    allowed_text = " ".join([m["text"] for m in moments] + [pl for m in moments for pl in m["places"]]
                            + said + [player_zone or "", place or ""])
    pool = list(OPENER_EXAMPLES.get(plan.kind, OPENER_EXAMPLES["checkin"]))
    if plan.kind == "checkin" and _long_absent(plan):
        pool += OPENER_LONG_ABSENCE_EXAMPLES
    examples = rng.sample(pool, min(OPENER_EXAMPLES_SHOWN, len(pool)))
    identity = next((i for i in personality.IRL_IDENTITIES if i["id"] == p.get("identity_id")), None)
    mood = personality.pick_mood(identity) if identity else "chill"
    system = WHISPER_OPENER_PROMPT.format(
        who=(p.get("irl") or {}).get("who_core") or p.get("who", ""),
        typing_style=p.get("typing_style", ""), mood=mood, name=plan.bot, level=level,
        race=p.get("race", ""), class_name=p.get("class_name", ""), faction=p.get("faction", ""),
        player=player,
        moments_section=build_moments_section([m["text"] for m in moments], said),
        examples_section=build_opener_examples_section(examples),
        kind_instruction=build_opener_kind_instruction(plan.kind, plan.invite,
                                                       plan.long_absence_days))
    user = build_opener_user_message(player)

    def problem(text: str) -> str | None:
        if not text:
            return "empty"
        if is_narration(text, plan.bot):
            return "narration"
        if is_self_intro(text, bot_name=plan.bot, race=p.get("race", ""),
                         class_name=p.get("class_name", ""), level=level):
            return "self_intro"
        if find_violations(text, level, allowed_from=allowed_text):
            return "knowledge"
        if ungrounded_mentions(text, allowed_text):
            return "ungrounded"
        if is_example_copy(text, examples):
            return "copy"
        return None

    message, nudge = "", ""
    for _attempt in range(2):
        raw = await call_ollama(system + nudge, [], user, num_predict=24, max_sentences=2,
                                lane="chat")
        text, _flags = clean_line(parse_response(raw or "", "WHISPER")["message"],
                                  max_len=WHISPER_MAX_CHARS)
        why = problem(text)
        if why is None:
            message = text
            break
        print(f"[friends] opener {plan.bot} -> {player} [{plan.kind}] rejected ({why}): {text!r}")
        nudge = RETRY_NUDGE[why]

    fallback = not message
    if fallback:
        message = _fallback(plan, rng)           # authored, already typed like chat
    elif VOICE_TRANSFORM:
        message = transform(message, plan.bot, light=True, protect={player},
                            max_len=WHISPER_MAX_CHARS)
    cited_places = mentioned_places(message)
    moment_ids = [m["id"] for m in moments if cited_places & set(m["places"])]
    if plan.kind == "callback" and not fallback and not moment_ids and moments:
        # no place named: credit the newest moment shown, so citing rotates it
        moment_ids = [max(moments, key=lambda m: (m["ts"], m["id"]))["id"]]
    print(f"[friends] opener {plan.bot} -> {player} [{plan.kind}]"
          f"{' fallback' if fallback else ''}: {message!r}")
    return {"message": message,
            "actions": [{"type": "invite", "target": player}] if plan.kind == "invite" else [],
            "moment_ids": moment_ids, "fallback": fallback}
