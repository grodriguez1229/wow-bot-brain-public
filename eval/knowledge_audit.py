"""R2 acceptance audit: emitted tick lines that name content above the bot's level, or
post-vanilla terms. Bot levels come from memory.db (bot_personalities).

  venv/bin/python eval/knowledge_audit.py brain.log [--after "R2 DEPLOYED"] [--last 200]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DB_PATH  # noqa: E402
from knowledge import find_violations  # noqa: E402

_TICK = re.compile(r'^\[tick\] (\S+) -> (\S+)(?: \[[^\]]*\])?(?: \(re [^)]*\))?: "(.*)"$')


def tick_lines(lines, after: str | None = None) -> list[tuple[str, str]]:
    """(bot, message) for each emitted tick line, after the marker line if given."""
    if after is not None:
        idx = next((i for i, ln in enumerate(lines) if after in ln), None)
        lines = lines[idx + 1:] if idx is not None else []
    out = []
    for ln in lines:
        m = _TICK.match(ln.rstrip("\n"))
        if m and m.group(3):
            out.append((m.group(1), m.group(3)))
    return out


def audit(ticks, levels: dict[str, int]) -> tuple[int, list[tuple[str, int, str, list[str]]]]:
    """(lines checked, violating lines). Bots with no known level are skipped."""
    checked, bad = 0, []
    for bot, msg in ticks:
        lvl = levels.get(bot)
        if lvl is None:
            continue
        checked += 1
        v = find_violations(msg, lvl)
        if v:
            bad.append((bot, lvl, msg, v))
    return checked, bad


def load_levels(db_path=DB_PATH) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        return dict(conn.execute("SELECT bot_name, level FROM bot_personalities").fetchall())
    finally:
        conn.close()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--after", default=None, help="marker line; audit only lines after it")
    ap.add_argument("--last", type=int, default=None, help="only the last N tick lines")
    ap.add_argument("--db", default=str(DB_PATH))
    a = ap.parse_args(argv)
    with open(a.log, errors="replace") as f:
        ticks = tick_lines(f.readlines(), a.after)
    if a.last:
        ticks = ticks[-a.last:]
    checked, bad = audit(ticks, load_levels(a.db))
    rate = len(bad) / checked if checked else 0.0
    print(f"checked {checked} tick lines, {len(bad)} violations ({rate:.1%})")
    for bot, lvl, msg, v in bad:
        print(f"  L{lvl:<2} {bot}: {msg!r}  -> {', '.join(v)}")


if __name__ == "__main__":
    main()
