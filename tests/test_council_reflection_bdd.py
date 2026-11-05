import json
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

import council

scenarios("features/council_reflection.feature")


@pytest.fixture
def context():
    return {}


@given(parsers.parse('a fresh memory db with bot "{bot}" who has said a few things'))
def _fresh(context, tmp_path, monkeypatch, bot):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    db.save_message(bot, "Gus", "user", "rough day?")
    db.save_message(bot, "Gus", "assistant", "ugh these pugs keep ninja looting")
    context["db"] = db
    context["bot"] = bot


@given(parsers.parse('bot "{bot}" already has identity facet "{subj}" content "{content}" weight {w:d}'))
def _seed_facet(context, bot, subj, content, w):
    context["db"].upsert_memory(bot, "identity", subj, content, weight=w)


@given(parsers.parse('bot "{bot}" has 16 weak identity facets at weight 1'))
def _seed_many(context, bot):
    for i in range(16):
        context["db"].upsert_memory(bot, "identity", f"w{i}", f"weak thing {i}", weight=1)


def _edits_from_spec(spec):
    # "subj:content:weight;subj:content:weight"
    out = []
    for part in spec.split(";"):
        s, c, w = part.split(":")
        out.append({"subject": s, "content": c, "weight": int(w)})
    return out


@when(parsers.parse('the council reflects with fakes that synthesize "{a}" and "{b}"'))
def _reflect_synth(context, a, b):
    edits = _edits_from_spec(f"{a};{b}")
    context["applied"] = council.run_reflection(
        context["bot"],
        propose=lambda *args, **kw: "[]",
        synthesize=lambda *args, **kw: json.dumps(edits),
        council=[council.Persona("X", "x")],
    )


@when(parsers.parse('the council reflects with a fake that proposes nudge "{subj}:{content}:{wd:d}" and falls back to merge'))
def _reflect_merge(context, subj, content, wd):
    nudge = [{"subject": subj, "content": content, "weight_delta": wd}]
    context["applied"] = council.run_reflection(
        context["bot"],
        propose=lambda *args, **kw: json.dumps(nudge),
        synthesize=lambda *args, **kw: "garbage-not-json",  # forces merge fallback
        council=[council.Persona("X", "x")],
    )


@then(parsers.parse('bot "{bot}" identity has facet "{subj}" with weight {w:d}'))
def _has_facet(context, bot, subj, w):
    rows = {r["subject"]: r for r in context["db"].get_memory_sheet(bot, "identity")}
    assert subj in rows, f"{subj} not in {list(rows)}"
    assert rows[subj]["weight"] == w


@then(parsers.parse('bot "{bot}" has at most {n:d} identity facets'))
def _at_most(context, bot, n):
    assert len(context["db"].get_memory_sheet(bot, "identity")) <= n
