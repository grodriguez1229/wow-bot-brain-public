from sim.optimize.runlog import CycleRecord
from sim.optimize.evolution_loop import should_stop, load_state, save_state, COUNCIL_WHITELIST
from sim.optimize.guard import out_of_scope


def _rec(cycle, kept):
    return CycleRecord(cycle=cycle, edit_summary="x", baseline_eval_mean=3.0,
                       candidate_eval_mean=3.0, heldout_delta=0.0, kept=kept)


def test_should_stop_on_consecutive_reverts():
    recs = [_rec(1, False), _rec(2, False), _rec(3, False)]
    stop, reason = should_stop(recs, max_cycles=100, max_consecutive_reverts=3)
    assert stop and "revert" in reason.lower()


def test_should_not_stop_when_a_keep_breaks_the_streak():
    recs = [_rec(1, False), _rec(2, True), _rec(3, False)]
    stop, _ = should_stop(recs, max_cycles=100, max_consecutive_reverts=3)
    assert not stop


def test_should_stop_at_cycle_cap():
    recs = [_rec(i, True) for i in range(1, 6)]
    stop, reason = should_stop(recs, max_cycles=5, max_consecutive_reverts=8)
    assert stop and "cap" in reason.lower()


def test_state_round_trips(tmp_path):
    p = tmp_path / "state.json"
    save_state(p, {"cycle": 4, "baseline_mean": 3.1, "consecutive_reverts": 2})
    assert load_state(p)["cycle"] == 4
    assert load_state(tmp_path / "missing.json") == {}


def test_whitelist_is_council_only():
    assert COUNCIL_WHITELIST == {"council.py"}
    assert out_of_scope(["council.py"], COUNCIL_WHITELIST) == []
    assert out_of_scope(["council.py", "prompts.py"], COUNCIL_WHITELIST) == ["prompts.py"]
