"""R9 replay / dry-run harness: synthetic event histories through the real /event pipeline.

Each scenario is a JSON timeline (events and bot ticks at simulated seconds). A trial replays it
into a fresh temp DB with fresh presence/cooldown state, then forces the login roll through
(LOGIN_WHISPER_RATE=1) and reports what login whispers would happen, with quality checks.

  venv/bin/python eval/r9_replay.py eval/r9_scenarios/*.json [--trials N] [--seed S]
  venv/bin/python eval/r9_replay.py SCENARIO... --real-llm --model qwen3.5:9b   # operator only

Default LLM is a canned fake (no network). Exit code 1 on any FAIL.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import inspect
import json
import random
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import events  # noqa: E402
import friendship  # noqa: E402
import history  # noqa: E402
import llm as llm_mod  # noqa: E402
import login_whisper  # noqa: E402
import main  # noqa: E402
import personality  # noqa: E402
import presence  # noqa: E402
from config import WHISPER_MAX_CHARS  # noqa: E402
from knowledge import RAIDS, canonical_place, ungrounded_mentions  # noqa: E402
from postfilter import is_self_intro  # noqa: E402

T0 = 1_760_000_000          # simulated clock origin; steps use "at" seconds from here
DEFAULT_PERSONA = {"gender": "male", "who": "a college kid who games too much",
                   "typing_style": "lowercase, fast", "identity_id": "none",
                   "current_goal": "level up",
                   "irl": {"who_core": "a college kid who games too much"}}


def fake_llm(inner=None):
    """Canned WHISPER line that names the first stored moment's place (so it is grounded).
    `inner(system, hist, user, **kw)` may replace the line (sync or async)."""
    async def _fake(system, hist, user, **kw):
        if inner is not None:
            out = inner(system, hist, user, **kw)
            return await out if inspect.isawaitable(out) else out
        conn = db.get_db()
        try:
            row = conn.execute("SELECT places FROM moments ORDER BY ts, id LIMIT 1").fetchone()
        finally:
            conn.close()
        places = json.loads(row["places"]) if row and row["places"] else []
        return f"{places[0]} again?" if places else "yo"
    return _fake


@contextlib.contextmanager
def _clock(start: float):
    cur = {"t": start}
    real = time.time
    time.time = lambda: cur["t"]
    try:
        yield cur
    finally:
        time.time = real


def _seed_persona(spec: dict, saved: dict) -> None:
    name = spec["bot_name"]
    saved.setdefault(name, (personality._personality_cache.get(name),
                            personality._level_checked.get(name)))
    personality._personality_cache[name] = {**DEFAULT_PERSONA, **spec}
    personality._level_checked[name] = time.monotonic()


def _restore_personas(saved: dict) -> None:
    for name, (p, lc) in saved.items():
        for cache, v in ((personality._personality_cache, p), (personality._level_checked, lc)):
            if v is None:
                cache.pop(name, None)
            else:
                cache[name] = v


def _all_moment_text(player: str, bot: str) -> str:
    ms = history.moments_for(player, bot, limit=1000)
    return " ".join([m["text"] for m in ms] + [p for m in ms for p in m["places"]])


def _run_trial(spec: dict, llm, seed: int, client, plans_seen: list) -> dict:
    player = spec["player"]
    pname = player["name"]
    bots = {b["bot_name"]: b for b in spec.get("bots", [])}
    steps = sorted(spec["steps"], key=lambda s: s["at"])
    login_step = max((s for s in steps if s.get("event", {}).get("type") == "login"),
                     key=lambda s: s["at"])
    last = steps[-1]
    assert last is login_step, "scenario must end with the login under test"
    for rel in spec.get("relationships", []):
        friendship.add_chat(rel["bot"], pname, rel["chat_points"], now=T0)
    whispers: list[dict] = []
    with _clock(T0) as clk:
        for st in steps:
            clk["t"] = T0 + st["at"]
            if "tick" in st:
                r = client.post("/tick", json=st["tick"])
                assert r.status_code == 200, r.text
                continue
            ev = {"player": pname, "level": player["level"], "faction": player["faction"],
                  "group": [], **st["event"]}
            if st is last:
                random.seed(seed)
            r = client.post("/event", json=ev)
            assert r.status_code == 200, r.text
            if st is last:
                whispers = r.json()["whispers"]
                login_ev = ev
    kinds = {p.bot: p for p in plans_seen}
    out = []
    for w in whispers:
        bot = w["bot_name"]
        plan = kinds.get(bot)
        persona = personality._personality_cache.get(bot, {})
        invite_place = (plan.invite or {}).get("place") if plan and plan.invite else None
        with _clock(T0 + last["at"]):
            allowed = " ".join([_all_moment_text(pname, bot), login_ev.get("zone") or "",
                                invite_place or "",
                                " ".join(m["content"] for m in db.get_memory(bot, pname)
                                         if m["role"] == "user")])
        out.append({
            "bot_name": bot, "whisper_to": w["whisper_to"], "message": w["message"],
            "kind": plan.kind if plan else "?", "length": len(w["message"]),
            "delay_s": w["delay_s"],
            "self_intro": is_self_intro(w["message"], bot_name=bot, race=persona.get("race", ""),
                                        class_name=persona.get("class_name", ""),
                                        level=int(persona.get("level") or 1)),
            "ungrounded": ungrounded_mentions(w["message"], allowed),
            "invite_action": any(a.get("type") == "invite" for a in (w.get("actions") or [])),
            "invite_place": invite_place})
    return {"whispers": out, "bots": list(bots)}


def _judge(spec: dict, trial: dict) -> list[str]:
    expect, ws = spec.get("expect", {}), trial["whispers"]
    fails = []
    if expect.get("whisper") is True and not ws:
        fails.append("expected a whisper, got none")
    if expect.get("whisper") is False and ws:
        fails.append(f"expected silence, got {len(ws)} whisper(s)")
    if len(ws) > 2:
        fails.append(f"{len(ws)} whispers (max 2)")
    for w in ws:
        tag = f"{w['bot_name']} [{w['kind']}]"
        if w["whisper_to"] != spec["player"]["name"]:
            fails.append(f"{tag} wrong whisper_to {w['whisper_to']}")
        if not 20 <= w["delay_s"] <= 120:
            fails.append(f"{tag} delay {w['delay_s']}s out of 20..120")
        if w["length"] > WHISPER_MAX_CHARS:
            fails.append(f"{tag} length {w['length']} > {WHISPER_MAX_CHARS}")
        if w["self_intro"]:
            fails.append(f"{tag} self-intro")
        if w["ungrounded"]:
            fails.append(f"{tag} ungrounded {w['ungrounded']}")
        if w["kind"] == "invite" and not w["invite_action"]:
            fails.append(f"{tag} invite kind without invite action")
        if w["kind"] != "invite" and w["invite_action"]:
            fails.append(f"{tag} invite action on non-invite kind")
        if "kinds" in expect and w["kind"] not in expect["kinds"]:
            fails.append(f"{tag} kind not in {expect['kinds']}")
        if expect.get("invite") is False and (w["invite_action"] or w["kind"] == "invite"):
            fails.append(f"{tag} invite not expected")
        place = w.get("invite_place")
        if place and spec["player"]["level"] < 55 and place in {r[0] for r in RAIDS}:
            fails.append(f"{tag} raid invite for L{spec['player']['level']}")
    return fails


def run_scenario(spec: dict, *, llm, trials: int, seed: int) -> list[dict]:
    """Replay `spec` `trials` times (fresh temp DB and in-process state each), return one result
    dict per trial: {trial, whispers, passed, failures}."""
    from fastapi.testclient import TestClient
    results = []
    saved_attrs = [(login_whisper, a, getattr(login_whisper, a)) for a in
                   ("FRIENDS_ENABLED", "LOGIN_WHISPER_RATE", "call_ollama", "plan_login")]
    saved_main, saved_db = main.call_ollama, db.DB_PATH
    saved_personas: dict = {}
    real_plan = login_whisper.plan_login
    try:
        login_whisper.FRIENDS_ENABLED = True
        login_whisper.LOGIN_WHISPER_RATE = 1.0
        login_whisper.call_ollama = llm
        async def tick_fake(system, hist, user, **kw):
            return "SAY: hey"
        main.call_ollama = tick_fake
        for i in range(trials):
            plans: list = []
            def spy(*a, **kw):
                ps = real_plan(*a, **kw)
                plans.extend(ps)
                return ps
            login_whisper.plan_login = spy
            with tempfile.TemporaryDirectory() as tmp:
                db.DB_PATH = str(Path(tmp) / "replay.db")
                db.init_db()
                presence.reset_state()
                events.reset_state()
                for b in spec.get("bots", []):
                    _seed_persona(b, saved_personas)
                try:
                    trial = _run_trial(spec, llm, seed + i, TestClient(main.app), plans)
                finally:
                    presence.reset_state()
                    events.reset_state()
            trial["trial"] = i
            trial["failures"] = _judge(spec, trial)
            trial["passed"] = not trial["failures"]
            results.append(trial)
    finally:
        _restore_personas(saved_personas)
        main.call_ollama, db.DB_PATH = saved_main, saved_db
        for mod, a, v in saved_attrs:
            setattr(mod, a, v)
    return results


def scenario_failures(spec: dict, results: list[dict]) -> list[str]:
    """Per-trial failures plus the scenario-level 'invite can happen' check."""
    fails = [f"trial {r['trial']}: {f}" for r in results for f in r["failures"]]
    if spec.get("expect", {}).get("invite") is True and results and not any(
            w["invite_action"] for r in results for w in r["whispers"]):
        fails.append("expected at least one invite across trials, got none")
    return fails


def _real_llm(model: str | None):
    async def call(system, hist, user, **kw):
        kw["model"] = model
        return await llm_mod.call_ollama(system, hist, user, **kw)
    return call


def main_cli(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("scenarios", nargs="+")
    ap.add_argument("--real-llm", action="store_true", help="call real Ollama (operator only)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    llm = _real_llm(args.model) if args.real_llm else fake_llm()
    bad = 0
    for path in args.scenarios:
        spec = json.loads(Path(path).read_text())
        results = run_scenario(spec, llm=llm, trials=args.trials, seed=args.seed)
        fails = scenario_failures(spec, results)
        nw = sum(len(r["whispers"]) for r in results)
        print(f"== {spec['name']}: {nw} whisper(s) in {len(results)} trial(s) "
              f"-> {'FAIL' if fails else 'PASS'}")
        for r in results:
            for w in r["whispers"]:
                print(f"  t{r['trial']} {w['bot_name']}->{w['whisper_to']} [{w['kind']}] "
                      f"+{w['delay_s']}s len={w['length']} self_intro={w['self_intro']} "
                      f"ungrounded={w['ungrounded']} invite={w['invite_action']}: {w['message']!r}")
        for f in fails:
            print(f"  FAIL {f}")
        bad += bool(fails)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main_cli())
