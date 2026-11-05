"""R9 whisper A/B harness: 30 fixed prompts, one model per run, blinded side-by-side.

  run     --model TAG --out PATH.jsonl [--only reply|opener]
  compare A.jsonl B.jsonl --md OUT.md --seed N

`run` seeds a throwaway SQLite DB (the live memory.db is never opened) and forces the model
through llm.pick_model. `compare` hides which model wrote which column (key in OUT.key.json).
Run: venv/bin/python eval/whisper_ab.py ...
"""
import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whisper_prompts.json")
SHORT_LEN = 60


def load_cases(path: str = DEFAULT_PROMPTS) -> list[dict]:
    with open(path) as f:
        return json.load(f)


# --- run ------------------------------------------------------------------

def _seed_case(case: dict) -> None:
    """Reset every per-pair table for this bot, then load the case's world."""
    import db
    import friendship
    import history
    import personality

    bot, player = case["bot"], case["player"]
    now = time.time()
    conn = db.get_db()
    for table in ("messages", "relationships", "moments", "shared_events", "play_sessions"):
        conn.execute(f"DELETE FROM {table} WHERE bot_name = ?", (bot["bot_name"],))
    rel = case["relationship"]
    chat, play = float(rel["chat_points"]), float(rel["play_points"])
    fam = friendship.effective(chat, play)
    conn.execute(
        "INSERT INTO relationships (bot_name, player_name, familiarity, label, notes,"
        " chat_points, play_points, last_play_at, decayed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (bot["bot_name"], player, fam, friendship.label_for(fam), "", chat, play, now, now))
    conn.commit()
    conn.close()
    for role, content in case["history"]:
        db.save_message(bot["bot_name"], player, role, content)
    from knowledge import mentioned_places
    for i, text in enumerate(case["moments"]):
        history.add_moment(player, bot["bot_name"], text, source="fixture", source_id=i,
                           places=sorted(mentioned_places(text)))
    persona = dict(bot)
    persona.setdefault("gender", "male")
    persona.setdefault("in_group", 0)
    personality._personality_cache[bot["bot_name"]] = persona
    personality._level_checked[bot["bot_name"]] = time.monotonic()


def _allowed_text(case: dict) -> str:
    return " ".join(list(case["moments"]) + [c for _r, c in case["history"]])


def _persona_summary(case: dict) -> dict:
    b = case["bot"]
    return {k: b[k] for k in ("bot_name", "race", "class_name", "level", "faction")}


async def _run_reply(case: dict) -> str:
    import main
    from models import ChatRequest
    req = ChatRequest(bot_name=case["bot"]["bot_name"], player_name=case["player"],
                      message=case["message"],
                      channel="WHISPER" if case["lane"] == "whisper" else "SAY")
    if case["lane"] == "heard":
        result = await main.run_chat(req, lane="heard")
    else:
        result = await main.run_chat(req)
    return (result or {}).get("message", "") or ""


async def _run_opener(case: dict) -> str:
    import login_whisper
    plan = login_whisper.Plan(bot=case["bot"]["bot_name"], kind=case["opener_kind"], delay_s=0,
                              invite=({"type": "quest", "place": case["invite_zone"]}
                                      if case["opener_kind"] == "invite" else None),
                              long_absence_days=None)
    result = await login_whisper.generate_opener(
        plan, case["player"], player_zone=case["invite_zone"], rng=random.Random(0))
    return (result or {}).get("message", "") or ""


def run(model: str, out: str, only: str | None) -> int:
    import db
    import election
    import llm

    cases = [c for c in load_cases() if only in (None, c["kind"])]
    real_pick, real_path = llm.pick_model, db.DB_PATH
    tmp = tempfile.TemporaryDirectory()
    llm.pick_model = lambda _m, _lane: model
    db.DB_PATH = os.path.join(tmp.name, "whisper_ab.db")
    rows = []
    try:
        db.init_db()
        for case in cases:
            election.reset_state()
            _seed_case(case)
            t0 = time.monotonic()
            runner = _run_reply if case["kind"] == "reply" else _run_opener
            message = asyncio.run(runner(case))
            rows.append({"id": case["id"], "model": model, "kind": case["kind"],
                         "lane": case["lane"], "message": message, "len": len(message),
                         "latency_s": round(time.monotonic() - t0, 3),
                         "persona": _persona_summary(case), "allowed": _allowed_text(case)})
            print(f"[{case['id']}] {message!r}")
    finally:
        llm.pick_model, db.DB_PATH = real_pick, real_path
        import personality
        for c in cases:
            personality._personality_cache.pop(c["bot"]["bot_name"], None)
            personality._level_checked.pop(c["bot"]["bot_name"], None)
        tmp.cleanup()
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} rows -> {out}")
    return 0


# --- compare --------------------------------------------------------------

def _load_rows(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")


def side_by_side(rows_a: list[dict], rows_b: list[dict], rng: random.Random) -> tuple[str, dict]:
    """Markdown table with columns X/Y; which model is X is a coin flip per row."""
    by_a = {r["id"]: r for r in rows_a}
    by_b = {r["id"]: r for r in rows_b}
    tag_a = rows_a[0]["model"] if rows_a else "A"
    tag_b = rows_b[0]["model"] if rows_b else "B"
    lines = ["| id | X | Y |", "|---|---|---|"]
    key = {}
    for cid in [r["id"] for r in rows_a] + [i for i in by_b if i not in by_a]:
        a, b = by_a.get(cid), by_b.get(cid)
        pair = [(tag_a, a), (tag_b, b)]
        if rng.random() < 0.5:
            pair.reverse()
        key[cid] = {"X": pair[0][0], "Y": pair[1][0]}
        x = _cell(pair[0][1]["message"]) if pair[0][1] else "(none)"
        y = _cell(pair[1][1]["message"]) if pair[1][1] else "(none)"
        lines.append(f"| {cid} | {x} | {y} |")
    return "\n".join(lines) + "\n", key


def metrics(rows: list[dict]) -> dict:
    """Per-model summary. Self-intro / ungrounded need helpers that may not exist yet."""
    out = {"n": len(rows)}
    lens = [r["len"] for r in rows]
    out["median_len"] = statistics.median(lens) if lens else "n/a"
    out["short_share"] = (sum(n <= SHORT_LEN for n in lens) / len(lens)) if lens else "n/a"
    try:
        from postfilter import is_self_intro
    except ImportError:
        is_self_intro = None
    if is_self_intro and rows:
        hits = 0
        for r in rows:
            p = r["persona"]
            hits += bool(is_self_intro(r["message"], bot_name=p["bot_name"], race=p["race"],
                                       class_name=p["class_name"], level=p["level"]))
        out["self_intro_rate"] = hits / len(rows)
    else:
        out["self_intro_rate"] = "n/a"
    try:
        from knowledge import ungrounded_mentions
    except ImportError:
        ungrounded_mentions = None
    if ungrounded_mentions and rows:
        out["ungrounded_rate"] = sum(
            bool(ungrounded_mentions(r["message"], r.get("allowed", ""))) for r in rows) / len(rows)
    else:
        out["ungrounded_rate"] = "n/a"
    return out


def _fmt(v) -> str:
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def compare(path_a: str, path_b: str, md_path: str, seed: int) -> int:
    rows_a, rows_b = _load_rows(path_a), _load_rows(path_b)
    table, key = side_by_side(rows_a, rows_b, random.Random(seed))
    foot = ["", "## Metrics (unblinded)", "",
            "| model | n | median len | share <= 60 | self-intro rate | ungrounded-place rate |",
            "|---|---|---|---|---|---|"]
    for tag, rows in ((rows_a[0]["model"] if rows_a else "A", rows_a),
                      (rows_b[0]["model"] if rows_b else "B", rows_b)):
        m = metrics(rows)
        foot.append(f"| {tag} | {m['n']} | {_fmt(m['median_len'])} | {_fmt(m['short_share'])} |"
                    f" {_fmt(m['self_intro_rate'])} | {_fmt(m['ungrounded_rate'])} |")
    with open(md_path, "w") as f:
        f.write(table + "\n".join(foot) + "\n")
    key_path = (md_path[:-3] if md_path.endswith(".md") else md_path) + ".key.json"
    with open(key_path, "w") as f:
        json.dump(key, f, indent=1)
    print(f"wrote {md_path} and {key_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--only", choices=["reply", "opener"])
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--md", required=True)
    c.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    if args.cmd == "run":
        return run(args.model, args.out, args.only)
    return compare(args.a, args.b, args.md, args.seed)


if __name__ == "__main__":
    sys.exit(main())
