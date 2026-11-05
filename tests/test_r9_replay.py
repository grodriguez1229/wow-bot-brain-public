"""R9 Task 11: replay harness. Real /event + planner + opener pipeline, fake LLM, fresh DB per trial."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))

import r9_replay  # noqa: E402

SCEN = pathlib.Path(r9_replay.__file__).parent / "r9_scenarios"


def _load(name):
    return json.loads((SCEN / f"{name}.json").read_text())


def _whispers(results):
    return [w for r in results for w in r["whispers"]]


def test_three_wc_runs_friend_whispers():
    res = r9_replay.run_scenario(_load("three_wc_runs"), llm=r9_replay.fake_llm(), trials=10, seed=1)
    assert len(res) == 10
    for r in res:
        assert 1 <= len(r["whispers"]) <= 2
        assert r["passed"], r["failures"]
        for w in r["whispers"]:
            assert w["whisper_to"] == "Abril"
            assert 20 <= w["delay_s"] <= 120
            assert len(w["message"]) <= 60
            assert w["self_intro"] is False
            assert w["ungrounded"] == []
            assert w["kind"] in ("callback", "invite", "checkin")
    # the opener really was built from stored history, not a canned unconditional line
    assert any("wailing caverns" in w["message"].lower() for w in _whispers(res))


def test_pair_cooldown_does_not_bleed_between_trials():
    res = r9_replay.run_scenario(_load("three_wc_runs"), llm=r9_replay.fake_llm(), trials=5, seed=3)
    assert all(r["whispers"] for r in res)


def test_stranger_and_chat_only_silent():
    for name in ("stranger", "chat_only"):
        res = r9_replay.run_scenario(_load(name), llm=r9_replay.fake_llm(), trials=20, seed=2)
        assert _whispers(res) == [], name
        assert all(r["passed"] for r in res)


def test_invite_only_when_joinable():
    fits = r9_replay.run_scenario(_load("invite_fits"), llm=r9_replay.fake_llm(), trials=10, seed=1)
    inv = [w for w in _whispers(fits) if w["kind"] == "invite"]
    assert inv, "invite_fits never produced an invite in 10 seeded trials"
    assert all(w["invite_action"] for w in inv)
    assert all(not w["invite_action"] for w in _whispers(fits) if w["kind"] != "invite")
    unfit = r9_replay.run_scenario(_load("invite_unfit"), llm=r9_replay.fake_llm(), trials=20, seed=1)
    assert _whispers(unfit), "unfit scenario should still whisper (callback/checkin)"
    assert not [w for w in _whispers(unfit) if w["kind"] == "invite" or w["invite_action"]]


def test_cross_faction_silent():
    res = r9_replay.run_scenario(_load("cross_faction"), llm=r9_replay.fake_llm(), trials=20, seed=2)
    assert _whispers(res) == []


def test_checks_run_on_produced_messages():
    def bad(system, hist, user, **kw):
        return "im Astianon a level 12 night elf hunter in Stormwind City"
    res = r9_replay.run_scenario(_load("three_wc_runs"), llm=r9_replay.fake_llm(bad), trials=3, seed=1)
    # the pipeline rejects bad lines and falls back to authored openers; the report
    # must still validate what was produced
    for r in res:
        for w in r["whispers"]:
            assert w["self_intro"] is False and w["ungrounded"] == []
            assert len(w["message"]) <= 60


def test_report_flags_failures():
    spec = dict(_load("stranger"))
    spec["expect"] = {"whisper": True}
    res = r9_replay.run_scenario(spec, llm=r9_replay.fake_llm(), trials=2, seed=1)
    assert not any(r["passed"] for r in res)


def test_cli_exit_code(capsys):
    assert r9_replay.main_cli([str(SCEN / "stranger.json"), "--trials", "2", "--seed", "1"]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "stranger" in out
