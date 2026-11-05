import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "chatter_metrics", pathlib.Path(__file__).parent.parent / "eval" / "chatter_metrics.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

LOG = [
    '[tick] A -> GENERAL: "my gf says hi"',
    '[chat] noise',
    '[tick] B -> SAY: "murlocs everywhere in this camp"',
    "=== R3 DEPLOYED 2026-10-14T23:00 ===",
    '[tick] C -> GENERAL: "copy roger heading out"',
    '[tick] D -> SAY: (silent)',
    '[tick] E -> TRADE: "WTS linen bags 😂"',
]


def test_tick_messages_parses_and_skips_silent():
    assert cm.tick_messages(LOG) == ["my gf says hi", "murlocs everywhere in this camp",
                                     "copy roger heading out", "WTS linen bags 😂"]


def test_after_marker():
    assert cm.tick_messages(LOG, after="R3 DEPLOYED") == ["copy roger heading out", "WTS linen bags 😂"]


def test_metrics_values():
    m = cm.metrics(cm.tick_messages(LOG))
    assert m["n"] == 4
    assert m["irl"] == 0.25
    assert m["roger"] == 0.25
    assert m["emoji"] == 0.25
    assert m["over140"] == 0.0


def test_metrics_empty():
    assert cm.metrics([])["n"] == 0


def test_missing_marker_raises():
    import pytest
    with pytest.raises(ValueError, match="marker not found"):
        cm.tick_messages(LOG, after="NOT THERE")


def test_marker_only_in_tick_line_raises():
    import pytest
    lines = ['[tick] A -> SAY: "R3 DEPLOYED lol"', "plain line"]
    with pytest.raises(ValueError, match="marker not found"):
        cm.tick_messages(lines, after="R3 DEPLOYED")


def test_quoted_marker_in_tick_does_not_move_cut():
    lines = [
        '[tick] Z -> SAY: "R3 DEPLOYED lol"',
        "=== R3 DEPLOYED 2026-10-14T23:00 ===",
        '[tick] C -> GENERAL: "copy roger heading out"',
        '[tick] Y -> SAY: "quoting R3 DEPLOYED again"',
    ]
    assert cm.tick_messages(lines, after="R3 DEPLOYED") == [
        "copy roger heading out", "quoting R3 DEPLOYED again"]


def test_main_exits_on_missing_marker(tmp_path):
    import pytest
    before = tmp_path / "before.txt"
    after = tmp_path / "after.log"
    before.write_text('[tick] A -> SAY: "hi"\n')
    after.write_text('[tick] A -> SAY: "hi"\n')
    with pytest.raises(SystemExit) as exc:
        cm.main([str(before), str(after), "--after", "NOPE"])
    assert "marker not found" in str(exc.value)


R8_LOG = [
    '[tick] A -> GENERAL: "old format line here ok"',
    '[tick] B -> LFG [ad]: "lfm wc need tank"',
    '[tick] C -> GENERAL [reaction] (re A): "lol"',
    '[tick] D -> SAY [fragment]: "oom"',
    '[tick] E: (silent, breathe)',
    '[tick] F -> GUILD [question] (re Gus): "who is on?"',
]


def test_r8_tags_parse_alongside_old_format():
    recs = cm.tick_records(R8_LOG)
    assert [r["msg"] for r in recs] == ["old format line here ok", "lfm wc need tank", "lol",
                                        "oom", "who is on?"]
    assert recs[0]["shape"] is None and recs[0]["re"] is None
    assert recs[2]["shape"] == "reaction" and recs[2]["re"] == "A"
    assert recs[4]["channel"] == "GUILD" and recs[4]["re"] == "Gus"
    assert cm.tick_messages(R8_LOG) == [r["msg"] for r in recs]


def test_r8_metric_fields():
    recs = cm.tick_records(R8_LOG)
    m = cm.metrics([r["msg"] for r in recs], recs)
    assert m["le20"] == 0.8
    assert m["reply"] == 0.4
    assert m["reply_non_ad"] == 0.5
    assert m["shapes"]["untagged"] == 0.2 and m["shapes"]["ad"] == 0.2
    assert m["top_opener_share"] == 0.2
    assert "replies 40%" in cm._fmt("x", m)


def test_metrics_without_records_still_works():
    m = cm.metrics(["a b c", "a b d"])
    assert m["reply"] == 0.0 and m["shapes"] == {} and m["top_opener"] == "a b"


def test_main_prints_new_fields(tmp_path, capsys):
    before = tmp_path / "before.txt"
    after = tmp_path / "after.log"
    before.write_text('[tick] A -> SAY: "hi there"\n')
    after.write_text("=== R8 DEPLOYED x ===\n" + "\n".join(R8_LOG) + "\n")
    cm.main([str(before), str(after), "--after", "R8 DEPLOYED"])
    out = capsys.readouterr().out
    assert "After " in out and "replies 40%" in out and "<=20ch" in out
