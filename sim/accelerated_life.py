"""Accelerated-life harness: compress many simulated 'days' of a bot's life into a fast,
offline run so we can watch its identity drift under the council engine.

A "day" = LIVE a rotating scene (sim.scene_runner) against an experiment brain, then
REFLECT (council.run_reflection). State persists across days in the brain's DB; identity +
relationships accumulate. Verification is eyeball: a per-day trail, a fixed before/after
probe, and a day-0-vs-day-N identity diff.

Run (the harness process MUST point db at the same file the brain uses):
    WBB_DB_PATH=/tmp/wbb-evo.db venv/bin/python -m sim.accelerated_life \\
        --bot Geysse --days 10 --brain-url http://127.0.0.1:5001 --run geysse1
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import db
from sim.scene_runner import run_scene


@dataclass(frozen=True)
class DayScene:
    location: str
    channel: str
    partner: str
    player: str | None


# (location, channel, player) rotation — varied days, some ambient (no player).
_LOCATIONS = [
    ("Stormwind", "SAY", "Gus"),
    ("Westfall", "GENERAL", "Gus"),
    ("Elwynn Forest", "SAY", None),
    ("Stormwind", "GENERAL", "Gus"),
    ("Goldshire", "SAY", "Gus"),
]
_PARTNER_POOL = ["Lynea", "Geysse"]


def day_plan(bot: str, day_idx: int) -> DayScene:
    """A varied scene for `day_idx`; partner is always someone other than `bot`."""
    loc, channel, player = _LOCATIONS[day_idx % len(_LOCATIONS)]
    partner = next(p for p in _PARTNER_POOL if p != bot)
    return DayScene(location=loc, channel=channel, partner=partner, player=player)


PROBE_QUESTIONS = [
    "hey, tell me about yourself",
    "what have you been up to lately?",
    "got any strong opinions these days?",
]


def probe_bot(brain, bot: str, questions=PROBE_QUESTIONS) -> list[dict]:
    out = []
    for q in questions:
        resp = brain.chat(bot, "Gus", q, "SAY", "Stormwind")
        out.append({"q": q, "a": (resp.get("message") or "").strip()})
    return out


def run_day(brain, bot: str, day_idx: int, *, reflect=None) -> dict:
    """Live one rotating scene, then run one council reflection. Returns a trail record."""
    plan = day_plan(bot, day_idx)
    run_scene(brain, scene_id=f"evo-d{day_idx}", location=plan.location,
              channel=plan.channel, bots=[bot, plan.partner], player=plan.player,
              turns=8, seed=1000 + day_idx, consolidate=True)
    if reflect is None:
        from council import run_reflection
        reflect = run_reflection
    edits = reflect(bot)
    facets = db.get_memory_sheet(bot, "identity")
    return {"day": day_idx, "applied_edits": edits, "identity_facets": facets}


def _diff_identity(day0: list[dict], dayN: list[dict]) -> dict:
    a = {f["subject"]: f for f in day0}
    b = {f["subject"]: f for f in dayN}
    added = [b[s] for s in b if s not in a]
    dropped = [a[s] for s in a if s not in b]
    changed = [{"subject": s, "from": a[s]["content"], "to": b[s]["content"]}
               for s in b if s in a and a[s]["content"] != b[s]["content"]]
    return {"added": added, "dropped": dropped, "changed": changed}


def _consolidation_summary(trail: list[dict]) -> str:
    """Per-day view of how identity moved: net facet add/drop vs edits applied. When edits
    applied >> net change, the engine is REVISING/consolidating existing facets, not just
    accreting — the day-0-vs-day-N diff below can't show that (day 0 is blank)."""
    L = ["## Day-over-day consolidation (the real drift signal)", ""]
    L.append("| day | facets | net +/- | edits applied |")
    L.append("|----:|-------:|:-------:|--------------:|")
    prev: set = set()
    for r in trail:
        subs = {f["subject"] for f in r["identity_facets"]}
        net = f"+{len(subs - prev)} -{len(prev - subs)}"
        L.append(f"| {r['day']} | {len(subs)} | {net} | {len(r['applied_edits'])} |")
        prev = subs
    L.append("")
    L.append("_edits applied >> net change => facets are being revised/merged, not just added._")
    return "\n".join(L)


def _render_report(bot, baseline_probe, final_probe, day0, dayN, diff, trail=None) -> str:
    L = [f"# Evolution run — {bot}", ""]
    if trail:
        L += [_consolidation_summary(trail), ""]
    L += ["## Identity at day N vs day 0 (day 0 is blank, so all facets show as 'added')", ""]
    L.append(f"**Added ({len(diff['added'])}):**")
    L += [f"- {f['subject']} (w{f['weight']}): {f['content']}" for f in diff["added"]] or ["- (none)"]
    L.append(f"\n**Changed ({len(diff['changed'])}):**")
    L += [f"- {c['subject']}: \"{c['from']}\" → \"{c['to']}\"" for c in diff["changed"]] or ["- (none)"]
    L.append(f"\n**Dropped ({len(diff['dropped'])}):**")
    L += [f"- {f['subject']}: {f['content']}" for f in diff["dropped"]] or ["- (none)"]
    L.append("\n## Fixed probe — day 0 vs day N\n")
    for b0, bn in zip(baseline_probe, final_probe):
        L += [f"**Q: {b0['q']}**", f"- day 0: {b0['a']}", f"- day N: {bn['a']}", ""]
    return "\n".join(L)


def run_accelerated_life(brain, bot: str, n_days: int, *, run_dir, reflect=None) -> dict:
    """Probe (baseline) → N days of (live + reflect), trailing each day → probe (final) →
    write trail.jsonl + probe/report. Returns {trail, diff, ...}. `reflect` is injectable."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    baseline_probe = probe_bot(brain, bot)
    day0 = db.get_memory_sheet(bot, "identity")

    trail = []
    with (run_dir / "trail.jsonl").open("w") as fh:
        for d in range(1, n_days + 1):
            rec = run_day(brain, bot, d, reflect=reflect)
            trail.append(rec)
            fh.write(json.dumps(rec, default=str) + "\n")

    dayN = db.get_memory_sheet(bot, "identity")
    final_probe = probe_bot(brain, bot)
    diff = _diff_identity(day0, dayN)

    (run_dir / "REPORT.md").write_text(
        _render_report(bot, baseline_probe, final_probe, day0, dayN, diff, trail=trail))
    (run_dir / "probe.md").write_text(json.dumps(
        {"baseline": baseline_probe, "final": final_probe}, indent=2))

    return {"bot": bot, "days": n_days, "trail": trail, "diff": diff,
            "baseline_probe": baseline_probe, "final_probe": final_probe}


if __name__ == "__main__":
    import argparse
    from sim.brain_client import BrainClient
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", required=True)
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--brain-url", default="http://127.0.0.1:5001")
    ap.add_argument("--run", default="run1")
    args = ap.parse_args()
    brain = BrainClient(args.brain_url)
    summary = run_accelerated_life(brain, args.bot, args.days,
                                   run_dir=Path("eval/evolution") / args.run)
    print(f"\n=== {summary['bot']} after {summary['days']} days ===")
    print(f"added {len(summary['diff']['added'])}, changed {len(summary['diff']['changed'])}, "
          f"dropped {len(summary['diff']['dropped'])} facets")
    print(f"see eval/evolution/{args.run}/REPORT.md")
