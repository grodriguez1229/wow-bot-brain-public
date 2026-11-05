"""Before/after chatter metrics over brain.log-style [tick] lines (R3).

Usage (from repo root):
  venv/bin/python eval/chatter_metrics.py BEFORE.txt AFTER.log [--after MARKER] [--last 1500]
`--after` only counts AFTER-file lines following the last line containing MARKER."""
from __future__ import annotations

import argparse
import collections
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from irl_budget import is_irl_line  # noqa: E402
from postfilter import has_emoji  # noqa: E402

# R8 adds optional "[shape]" and "(re Speaker)" tags; pre-R8 lines have neither.
TICK_RE = re.compile(r'^\[tick\] (\S+) -> (\S+)(?: \[(\w+)\])?(?: \(re (\S+)\))?: "(.*)"$')
_ROGER = re.compile(r"\b(?:roger|copy)\b", re.IGNORECASE)


def _toks(s: str) -> list[str]:
    return re.findall(r"[a-z']+", s.lower())


def tick_messages(lines, after: str | None = None) -> list[str]:
    return [r["msg"] for r in tick_records(lines, after=after)]


def tick_records(lines, after: str | None = None) -> list[dict]:
    """Parsed [tick] lines: bot, channel, shape (None pre-R8), re (reply target or None), msg."""
    lines = list(lines)
    if after:
        # Only non-tick lines may serve as the cut marker, so a chat line
        # quoting the marker inside a [tick] line cannot move the cut.
        idx = max((i for i, l in enumerate(lines)
                   if after in l and not l.lstrip().startswith("[tick]")), default=None)
        if idx is None:
            raise ValueError(f"marker not found: {after!r}")
        lines = lines[idx + 1:]
    out = []
    for l in lines:
        m = TICK_RE.match(l.strip())
        if m:
            bot, ch, shape, re_, msg = m.groups()
            out.append({"bot": bot, "channel": ch, "shape": shape, "re": re_, "msg": msg})
    return out


def metrics(msgs: list[str], records: list[dict] | None = None) -> dict:
    n = len(msgs)
    if not n:
        return {"n": 0}
    sims = []
    sets = [set(_toks(m)) for m in msgs]
    for i, t in enumerate(sets):
        best = 0.0
        for u in sets[max(0, i - 100):i]:
            if t and u:
                best = max(best, len(t & u) / len(t | u))
        sims.append(best)
    tri = collections.Counter()
    for m in msgs:
        w = _toks(m)
        tri.update({" ".join(w[i:i + 3]) for i in range(len(w) - 2)})
    top_tri, top_cnt = tri.most_common(1)[0] if tri else ("", 0)
    openers = collections.Counter(" ".join(_toks(m)[:2]) for m in msgs)
    top_op, top_op_cnt = openers.most_common(1)[0] if openers else ("", 0)
    recs = records or []
    shapes = collections.Counter(r["shape"] or "untagged" for r in recs)
    non_ad = [r for r in recs if r["shape"] != "ad"]
    return {
        "n": n,
        "irl": sum(is_irl_line(m) for m in msgs) / n,
        "roger": sum(bool(_ROGER.search(m)) for m in msgs) / n,
        "top_trigram": top_tri, "top_trigram_share": top_cnt / n,
        "median_len": statistics.median(len(m) for m in msgs),
        "over140": sum(len(m) > 140 for m in msgs) / n,
        "emoji": sum(has_emoji(m) for m in msgs) / n,
        "sim30": sum(s >= .3 for s in sims) / n, "sim40": sum(s >= .4 for s in sims) / n,
        "sim50": sum(s >= .5 for s in sims) / n,
        "openers": [(k, round(v / n, 3)) for k, v in openers.most_common(4)],
        "top_opener": top_op, "top_opener_share": top_op_cnt / n,
        "le20": sum(len(m) <= 20 for m in msgs) / n,
        "reply": (sum(bool(r["re"]) for r in recs) / len(recs)) if recs else 0.0,
        "reply_non_ad": (sum(bool(r["re"]) for r in non_ad) / len(non_ad)) if non_ad else 0.0,
        "shapes": {k: round(v / len(recs), 3) for k, v in shapes.most_common()} if recs else {},
    }


def _fmt(label: str, m: dict) -> str:
    if not m.get("n"):
        return f"{label}: n=0"
    return (f"{label}: n={m['n']} IRL {m['irl']:.0%}  roger/copy {m['roger']:.1%}  "
            f"emoji {m['emoji']:.1%}  >140ch {m['over140']:.1%}  median {m['median_len']:.0f}ch  "
            f"top3gram '{m['top_trigram']}' {m['top_trigram_share']:.1%}  "
            f"maxsim>=.3 {m['sim30']:.0%} >=.4 {m['sim40']:.0%} >=.5 {m['sim50']:.0%}  "
            f"openers {m['openers']}\n"
            f"        <=20ch {m['le20']:.0%}  replies {m['reply']:.0%} (non-ad {m['reply_non_ad']:.0%})  "
            f"top opener '{m['top_opener']}' {m['top_opener_share']:.1%}  shapes {m['shapes']}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after_file")
    ap.add_argument("--after", default=None, help="marker line in AFTER file")
    ap.add_argument("--last", type=int, default=1500)
    a = ap.parse_args(argv)
    with open(a.before, errors="ignore") as f:
        before = tick_records(f)[-a.last:]
    with open(a.after_file, errors="ignore") as f:
        try:
            after = tick_records(f, after=a.after)[-a.last:]
        except ValueError as e:
            sys.exit(f"error: {e}")
    print(_fmt("Before", metrics([r["msg"] for r in before], before)))
    print(_fmt("After ", metrics([r["msg"] for r in after], after)))


if __name__ == "__main__":
    main()
