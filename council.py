"""The council engine: diverse-personality reflection that drives a bot's identity drift.

Repurposes the project's `summarize`-style seam from CRITIC to ENGINE. Three diverse
persona "lenses" PROPOSE nudges to the bot's identity; a SYNTHESIS step reconciles the
(deliberately conflicting) nudges into concrete identity edits, applied to the writable
`kind='identity'` layer. Pure parsing/merge + injectable model seams (propose/synthesize),
mirroring consolidate.py / self_memory.py. No Ollama in tests — they inject fakes. A Claude
backend can swap in later behind the same signatures.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

_MAX_IDENTITY = 16
_DEDUP_SIM = 0.6      # token-Jaccard >= this => near-twin facets, collapse to the strongest
_MAX_STRONG = 2       # at most this many facets may sit at weight >= _STRONG_W
_STRONG_W = 4
_WD_MIN, _WD_MAX = -3, 3      # weight_delta clamp (nudges)
_W_MIN, _W_MAX = 0, 5         # absolute facet weight clamp (edits); 0 == drop


def parse_nudges(raw: str) -> list[dict]:
    """One persona's output -> validated nudges [{subject, content, weight_delta}].
    Subject lowercased; weight_delta coerced+clamped; bad/empty entries dropped. Never raises."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject, content = item.get("subject"), item.get("content")
        if not subject or not content:
            continue
        try:
            wd = int(item.get("weight_delta", 1))
        except (TypeError, ValueError):
            wd = 1
        out.append({"subject": str(subject).strip().lower(),
                    "content": str(content).strip(),
                    "weight_delta": max(_WD_MIN, min(_WD_MAX, wd))})
    return out


def parse_edits(raw: str) -> list[dict]:
    """Synthesis output -> validated edits [{subject, content, weight}]. weight clamped
    [0,5]; weight 0 = DROP (content optional). Positive weight requires content. Never raises."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject")
        if not subject:
            continue
        try:
            w = int(item.get("weight", 1))
        except (TypeError, ValueError):
            w = 1
        w = max(_W_MIN, min(_W_MAX, w))
        content = (item.get("content") or "").strip()
        if not content and w > 0:
            continue
        out.append({"subject": str(subject).strip().lower(), "content": content, "weight": w})
    return out


def merge_nudges(current: list[dict], nudges: list[dict]) -> list[dict]:
    """Deterministic fallback synthesis (no LLM). Same-subject nudges sum weight_delta; last
    non-empty content wins. new_weight = clamp(old_weight + summed_delta, 0, 5). Returns edits.
    Used when the synthesis model returns nothing parseable, so a cycle never silently no-ops."""
    cur = {str(f["subject"]).strip().lower():
           {"content": (f.get("content") or "").strip(), "weight": int(f.get("weight", 1) or 1)}
           for f in current}
    agg: dict[str, dict] = {}
    for n in nudges:
        a = agg.setdefault(n["subject"], {"delta": 0, "content": ""})
        a["delta"] += n["weight_delta"]
        if n["content"]:
            a["content"] = n["content"]
    edits = []
    for s, a in agg.items():
        old_w = cur.get(s, {}).get("weight", 0)
        new_w = max(_W_MIN, min(_W_MAX, old_w + a["delta"]))
        content = a["content"] or cur.get(s, {}).get("content", "")
        if new_w > 0 and not content:
            continue
        edits.append({"subject": s, "content": content, "weight": new_w})
    return edits


import httpx

import db
from config import OLLAMA_URL, OLLAMA_MODEL


@dataclass(frozen=True)
class Persona:
    name: str
    lens: str   # the system-prompt that gives this council member its distinct taste


COUNCIL: list[Persona] = [
    Persona("Edge",
            "You are The Edge, on a council that shapes who a WoW player is becoming. "
            "Push them toward SHARPER, more SPECIFIC opinions, tastes, grudges, and "
            "in-jokes — the little stances that make a person not generic. Don't make "
            "them mean; make them particular."),
    Persona("Heart",
            "You are The Heart, on a council that shapes who a WoW player is becoming. "
            "Push their RELATIONSHIPS forward — who they bond with, clash with, drift "
            "from — and how those people change them. Root changes in who they spend "
            "time with."),
    Persona("Arc",
            "You are The Arc, on a council that shapes who a WoW player is becoming. Your "
            "job is NARRATIVE CONTINUITY — a believable through-line over time (burnout, a "
            "comeback, getting hooked on something, a mood that trends) that stays "
            "consistent with who they've been becoming."),
]


def build_life_digest(bot_name: str, *, recent_limit: int = 20) -> str:
    """The 'recent life' the council reads: recent chat across everyone + relationship notes."""
    msgs = db.get_recent_messages(bot_name, limit=recent_limit)
    convo = "\n".join(
        f"{'You' if m['role'] == 'assistant' else m['player_name']}: {m['content']}"
        for m in msgs) or "(quiet stretch — not much said)"
    rels = db.get_memory_sheet(bot_name, "relationship")
    rel_txt = "; ".join(f"{r['subject']}: {r['content']}" for r in rels) or "(no one in particular yet)"
    return f"RECENT CHAT:\n{convo}\n\nPEOPLE YOU KNOW: {rel_txt}"


def _format_identity(facets: list[dict]) -> str:
    if not facets:
        return "(blank slate — they haven't grown into anyone specific yet)"
    return "; ".join(f"{f['subject']} (w{f.get('weight', 1)}): {f['content']}" for f in facets)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _similar(a: str, b: str, threshold: float) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


def consolidate_facets(facets: list[dict], *, sim_threshold: float = _DEDUP_SIM,
                       max_strong: int = _MAX_STRONG, strong_w: int = _STRONG_W) -> list[dict]:
    """Deterministic identity hygiene, applied after synthesis: (1) MERGE near-duplicate facets
    (token-Jaccard >= sim_threshold) keeping the highest-weight one; (2) enforce the WEIGHT
    CEILING — at most max_strong facets may sit at weight >= strong_w, the rest demoted to
    strong_w - 1. Pure, order-stable on ties. This is the lever the LLM prose rules ignored in
    cycle 1 (cafe_crust/cafeteria_crust both survived at w5), which drove recycled output."""
    ordered = sorted(enumerate(facets), key=lambda iv: (-int(iv[1].get("weight", 1)), iv[0]))
    kept: list[dict] = []
    for _, f in ordered:
        if any(_similar(f.get("content") or "", k.get("content") or "", sim_threshold) for k in kept):
            continue  # near-twin of an already-kept (higher-or-equal weight) facet
        kept.append(dict(f))
    strong = [f for f in kept if int(f.get("weight", 1)) >= strong_w]
    for f in strong[max_strong:]:  # kept is weight-desc, so these are the weakest 'strong' ones
        f["weight"] = strong_w - 1
    return kept


def apply_edits(bot_name: str, edits: list[dict]) -> list[dict]:
    """Apply edits to the writable identity layer, prune to the strongest _MAX_IDENTITY, then
    run deterministic consolidation (drop near-twins + enforce the weight ceiling).
    weight 0 deletes the facet. Returns the edits applied."""
    for e in edits:
        if e["weight"] <= 0:
            db.delete_memory(bot_name, "identity", e["subject"])
        else:
            db.upsert_memory(bot_name, "identity", e["subject"], e["content"], e["weight"])
    db.prune_memory_by_weight(bot_name, "identity", keep=_MAX_IDENTITY)
    current = db.get_memory_sheet(bot_name, "identity")
    consolidated = consolidate_facets(current)
    kept_subjects = {f["subject"] for f in consolidated}
    for f in current:
        if f["subject"] not in kept_subjects:
            db.delete_memory(bot_name, "identity", f["subject"])
    for f in consolidated:
        db.upsert_memory(bot_name, "identity", f["subject"], f["content"], int(f["weight"]))
    return edits


def local_propose(persona: Persona, digest: str, current_identity: str, who: str) -> str:
    """Default backend: one Ollama call per persona. Never called in tests."""
    system = (
        f"{persona.lens}\n\nThe person at their core: {who}\n"
        f"Who they've been becoming: {current_identity}\n\n"
        "Propose 1-3 nudges to who they are, as ONLY a JSON list, each "
        '{"subject": one-or-two-word key, "content": a short first-person line, '
        '"weight_delta": -3..3}. Positive = lean into it; negative = it\'s fading. Ground '
        "every nudge in the recent life below. No prose, JSON only.")
    resp = httpx.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL, "think": False, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": digest}],
        "options": {"num_predict": 220, "temperature": 0.7},
    }, timeout=60.0)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def local_synthesize(current_identity: str, all_nudges: list[dict], who: str) -> str:
    """Default backend: one Ollama call reconciling the council's competing nudges. Never
    called in tests."""
    system = (
        "You reconcile a council's competing suggestions about who a WoW player is becoming "
        "into a final, coherent identity update. They disagree on purpose — keep what's "
        "true, let real tensions stand as part of the person, drop what no longer fits.\n"
        "A real person is BROAD and CHANGES, they don't just pile on the same idea. So:\n"
        "- MERGE near-duplicates: if several facets circle the same theme, collapse them "
        "into ONE. Never output two facets that say basically the same thing.\n"
        "- Prefer REVISING an existing facet (reuse its exact subject key) over inventing a "
        "new subject. Only add a new subject for a genuinely new part of them.\n"
        "- SHED: use weight 0 to DROP a facet that's gone stale or that a fresher facet "
        "now covers. The person should lose things too, not only accumulate.\n"
        "- Keep the whole identity DIVERSE — don't let one motif (a food, a phrase, a "
        "grievance) dominate. If it's taking over, dial it down or drop it.\n"
        "- Weights: reserve 4-5 for a FEW truly core traits; most facets sit at 2-3.\n"
        "Output ONLY a JSON list of facets to set, each {\"subject\": key, \"content\": "
        "short first-person line, \"weight\": 0..5}. Keep it human and specific, not a "
        f"committee average.\n\nAt their core: {who}\nCurrent identity: {current_identity}")
    user = "COUNCIL SUGGESTIONS:\n" + json.dumps(all_nudges, indent=2)
    resp = httpx.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL, "think": False, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "options": {"num_predict": 320, "temperature": 0.5},
    }, timeout=90.0)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def run_reflection(bot_name: str, *, who: str = "", propose=None, synthesize=None,
                   recent_limit: int = 20, council: list[Persona] | None = None) -> list[dict]:
    """One council reflection cycle for one bot. propose/synthesize resolve at CALL time so
    tests inject fakes. Returns the applied identity edits.

    propose(persona, digest, current_identity_str, who) -> raw JSON str (nudges)
    synthesize(current_identity_str, all_nudges, who)    -> raw JSON str (edits)
    """
    if propose is None:
        propose = local_propose
    if synthesize is None:
        synthesize = local_synthesize
    if council is None:
        council = COUNCIL
    if not who:
        who = db.get_who(bot_name)

    facets = db.get_memory_sheet(bot_name, "identity")
    digest = build_life_digest(bot_name, recent_limit=recent_limit)
    cur_str = _format_identity(facets)

    all_nudges: list[dict] = []
    for persona in council:
        all_nudges.extend(parse_nudges(propose(persona, digest, cur_str, who)))

    edits = parse_edits(synthesize(cur_str, all_nudges, who))
    if not edits:
        edits = merge_nudges(facets, all_nudges)
    return apply_edits(bot_name, edits)
