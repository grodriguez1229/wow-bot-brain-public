import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "eval"))

import whisper_ab  # noqa: E402
from vanilla_guard import find_banned  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "eval", "whisper_prompts.json")


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _strings(v)


def test_prompt_fixture_shape():
    cases = whisper_ab.load_cases(FIXTURE)
    assert len(cases) == 30
    assert len({c["id"] for c in cases}) == 30
    kinds = [c["kind"] for c in cases]
    assert kinds.count("reply") == 20 and kinds.count("opener") == 10
    for c in cases:
        for s in _strings(c):
            assert find_banned(s) == [], (c["id"], s)
    openers = [c["opener_kind"] for c in cases if c["kind"] == "opener"]
    assert (openers.count("callback"), openers.count("invite"), openers.count("checkin")) == (4, 3, 3)
    replies = [c for c in cases if c["kind"] == "reply"]
    assert sum(c["lane"] == "whisper" for c in replies) == 14
    assert sum(c["lane"] == "heard" for c in replies) == 6
    msgs = {c["message"] for c in replies}
    for m in ("hey", "where u at", "what lvl r u", "wanna run wc?", "how was work",
              "lol remember that wipe", "tell me about yourself", "u around tonight?"):
        assert m in msgs


def _rows(model, n=3):
    return [{"id": f"c{i}", "model": model, "kind": "reply", "lane": "whisper",
             "message": f"{model} says {i}", "len": 10 + i, "latency_s": 0.1} for i in range(n)]


def test_side_by_side_blinds_and_keys():
    a, b = _rows("A"), _rows("B")
    md, key = whisper_ab.side_by_side(a, b, random.Random(7))
    data_rows = [ln for ln in md.splitlines() if ln.startswith("| c")]
    assert len(data_rows) == 3
    assert set(key) == {"c0", "c1", "c2"}
    for v in key.values():
        assert set(v) == {"X", "Y"} and {v["X"], v["Y"]} == {"A", "B"}
    for ln in data_rows:               # model tags never leak into the table
        assert "A says" not in ln.split("|")[2] or key[ln.split("|")[1].strip()]["X"] == "A"
    md2, key2 = whisper_ab.side_by_side(a, b, random.Random(7))
    assert (md, key) == (md2, key2)


def test_run_with_fake_llm(tmp_path, monkeypatch):
    import config
    import main

    async def fake(*a, **k):
        return "lol ya"

    monkeypatch.setattr(main, "call_ollama", fake)
    live = str(config.DB_PATH)
    before = os.stat(live).st_mtime_ns if os.path.exists(live) else None
    out = tmp_path / "out.jsonl"
    whisper_ab.main(["run", "--model", "fake:1", "--only", "reply", "--out", str(out)])
    rows = [json.loads(ln) for ln in out.read_text().splitlines()]
    assert len(rows) == 20
    for r in rows:
        assert r["model"] == "fake:1" and r["kind"] == "reply" and r["message"]
        assert {"id", "lane", "len", "latency_s", "persona", "allowed"} <= set(r)
    after = os.stat(live).st_mtime_ns if os.path.exists(live) else None
    assert before == after


def test_compare_writes_table_key_and_metrics(tmp_path):
    pa, pb = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    for p, model in ((pa, "A"), (pb, "B")):
        rows = _rows(model)
        for r in rows:
            r["persona"] = {"bot_name": "Thaldrun", "race": "Dwarf", "class_name": "Warrior",
                            "level": 34, "faction": "Alliance"}
            r["allowed"] = ""
        p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    md = tmp_path / "out.md"
    whisper_ab.main(["compare", str(pa), str(pb), "--md", str(md), "--seed", "3"])
    text = md.read_text()
    assert "median len" in text and "| A |" in text and "| B |" in text
    assert set(json.loads((tmp_path / "out.key.json").read_text())) == {"c0", "c1", "c2"}


def test_run_openers_with_fake_llm(tmp_path, monkeypatch):
    import login_whisper
    import main

    async def fake(*a, **k):
        return "lol ya"

    monkeypatch.setattr(main, "call_ollama", fake)
    monkeypatch.setattr(login_whisper, "call_ollama", fake)
    out = tmp_path / "op.jsonl"
    whisper_ab.main(["run", "--model", "fake:1", "--only", "opener", "--out", str(out)])
    rows = [json.loads(ln) for ln in out.read_text().splitlines()]
    assert len(rows) == 10
    assert all(r["kind"] == "opener" and r["message"] for r in rows)
