from sim.optimize.loop_cycle import should_stop
from sim.optimize.runlog import CycleRecord


def _rec(kept):
    return CycleRecord(cycle=0, edit_summary="", baseline_eval_mean=0,
                       candidate_eval_mean=0, heldout_delta=0, kept=kept)


def test_should_stop_after_k_no_wins():
    assert should_stop([_rec(False)] * 8, k=8)


def test_does_not_stop_if_a_recent_cycle_won():
    assert not should_stop([_rec(False)] * 7 + [_rec(True)], k=8)


def test_does_not_stop_before_k_cycles():
    assert not should_stop([_rec(False)] * 3, k=8)


def test_regen_eval_seeds_memory_fixture(monkeypatch, tmp_path):
    import sim.optimize.loop_cycle as lc
    calls = {}
    import sim.memory_fixture as mf
    monkeypatch.setattr(mf, "load_memory_fixture",
                        lambda path, db_path=None: calls.update(path=path, db_path=db_path))
    # Stop generation early: make run_scene unused by giving an empty pool
    manifest = tmp_path / "m.json"
    manifest.write_text('{"eval": []}')
    out = tmp_path / "out"
    lc.regen_eval(str(manifest), str(out), memory_fixture="eval/optimizer/memory_fixture.json",
                  brain_db_path="/tmp/wbb-exp.db")
    assert calls == {"path": "eval/optimizer/memory_fixture.json", "db_path": "/tmp/wbb-exp.db"}


def test_regen_eval_accepts_pool_and_reads_that_key(tmp_path, monkeypatch):
    import json
    from sim.optimize import loop_cycle

    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"eval": ["ambient-a-s1"], "heldout": ["ambient-a-s2"]}))

    seen = {}

    class FakeSpec:
        scene_id = "ambient-a"
        location = "Org"; channel = "SAY"; bots = ["Bo"]; player = None; turns = 2

    def fake_all_specs():
        return [FakeSpec()]

    def fake_run_scene(**kw):
        seen["sid"] = kw["scene_id"]
        class SC:
            def save(self, p): p.write_text("{}")
        return SC()

    monkeypatch.setattr("sim.scenes.all_specs", fake_all_specs)
    monkeypatch.setattr("sim.scene_runner.run_scene", fake_run_scene)
    monkeypatch.setattr("sim.brain_client.BrainClient", lambda base_url: object())

    loop_cycle.regen_eval(str(manifest), str(tmp_path / "out"), pool="heldout")
    assert seen["sid"] == "ambient-a-s2"
