"""R9 whisper-lane metrics from brain.log: reply lanes and login whispers.

Usage (from repo root):
  venv/bin/python eval/whisper_metrics.py brain.log [--after "R9 DEPLOYED"] [--before-file F]
                                                   [--db memory.db]

Parsed lines (as printed by main.py):
  [chat] P -> Bot (L34 Dwarf Warrior, ...)        pre-R9 header, lane "chat"
  [chat:<lane>] P -> Bot (L34 ...)                R9 header, lane whisper|heard|...
    IN:  "..." / OUT: "..."                       OUT line carries the bot's message
  [whisper] Bot -> P [kind] (+Ns): "msg"          login whisper, lane "login"
`--after` keeps lines after the last non-chat line containing MARKER. Persona lookups open
memory.db read-only; an unknown persona falls back to a name-only self-intro check.
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sqlite3
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from knowledge import find_violations  # noqa: E402
from postfilter import is_self_intro  # noqa: E402

SHORT_LEN = 60
CHAT_RE = re.compile(r"^\[chat(?::(\w+))?\] (\S+) -> (\S+) \(L(\d+) ")
WHISPER_RE = re.compile(r'^\[whisper\] (\S+) -> (\S+) \[(\w+)\] \(\+\d+s\): "(.*)"$')
OUT_RE = re.compile(r'^\s+OUT: "(.*)"$')


def parse_chat_lines(lines, after: str | None = None) -> list[dict]:
    """Rows {source, lane, bot, player, level, kind, msg} for chat replies and login whispers."""
    lines = [l.rstrip("\n") for l in lines]
    if after:
        idx = max((i for i, l in enumerate(lines)
                   if after in l and not l.startswith(("[chat", "[whisper]", "  "))), default=None)
        if idx is None:
            raise ValueError(f"marker not found: {after!r}")
        lines = lines[idx + 1:]
    rows, pending = [], None
    for l in lines:
        m = CHAT_RE.match(l)
        if m:
            pending = {"source": "chat", "lane": m.group(1) or "chat", "player": m.group(2),
                       "bot": m.group(3), "level": int(m.group(4)), "kind": None}
            continue
        m = OUT_RE.match(l)
        if m and pending:
            rows.append({**pending, "msg": m.group(1)})
            pending = None
            continue
        m = WHISPER_RE.match(l)
        if m:
            pending = None
            rows.append({"source": "whisper", "lane": "login", "bot": m.group(1),
                         "player": m.group(2), "level": None, "kind": m.group(3),
                         "msg": m.group(4)})
    return rows


def load_personas(path: str) -> dict[str, dict]:
    """bot_name -> {race, class_name, level} from memory.db, opened read-only."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cur = conn.execute("SELECT bot_name, race, class_name, level FROM bot_personalities")
            return {n: {"race": r, "class_name": c, "level": lv} for n, r, c, lv in cur}
        finally:
            conn.close()
    except sqlite3.Error:
        return {}


def summarize(rows: list[dict], personas: dict[str, dict]) -> dict[str, dict]:
    """Per lane: count, median_len, short_share, self_intro_rate, violation_rate (+ kinds)."""
    by_lane: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by_lane[r["lane"]].append(r)
    out = {}
    for lane, rs in by_lane.items():
        lens = [len(r["msg"]) for r in rs]
        intro = viol = 0
        for r in rs:
            p = personas.get(r["bot"]) or {}
            level = r.get("level") or p.get("level") or 60     # unknown level: post-vanilla check only
            intro += bool(is_self_intro(r["msg"], bot_name=r["bot"], race=p.get("race", ""),
                                        class_name=p.get("class_name", ""),
                                        level=(p.get("level") or r.get("level") or 0)))
            viol += bool(find_violations(r["msg"], int(level)))
        n = len(rs)
        out[lane] = {"count": n, "median_len": statistics.median(lens),
                     "short_share": sum(x <= SHORT_LEN for x in lens) / n,
                     "self_intro_rate": intro / n, "violation_rate": viol / n}
        kinds = collections.Counter(r["kind"] for r in rs if r.get("kind"))
        if kinds:
            out[lane]["kinds"] = dict(kinds)
    return out


def _print(title: str, summary: dict[str, dict]) -> None:
    print(f"== {title}")
    if not summary:
        print("  (no rows)")
    for lane in sorted(summary):
        s = summary[lane]
        line = (f"  {lane:8s} n={s['count']:4d} median_len={s['median_len']:g} "
                f"<=60={s['short_share']:.0%} self_intro={s['self_intro_rate']:.1%} "
                f"violations={s['violation_rate']:.1%}")
        if "kinds" in s:
            line += " kinds=" + ",".join(f"{k}:{v}" for k, v in sorted(s["kinds"].items()))
        print(line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("log")
    ap.add_argument("--after", help="only count lines after the last line containing MARKER")
    ap.add_argument("--before-file", help="older log (or excerpt) to print as the 'before' block")
    ap.add_argument("--db", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                  "memory.db"))
    args = ap.parse_args(argv)
    personas = load_personas(args.db)
    if args.before_file:
        with open(args.before_file, errors="replace") as f:
            _print("before", summarize(parse_chat_lines(f), personas))
    with open(args.log, errors="replace") as f:
        rows = parse_chat_lines(f, after=args.after)
    _print("after" if args.after or args.before_file else "log", summarize(rows, personas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
