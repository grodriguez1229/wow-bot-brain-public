import council
from sim.evolution_judge import EvolutionScore
from sim.evolution_calibrate import calibration_report, noise_band, degraded_council, bucket_order_ok


def _score(run_id, score, gate=True):
    return EvolutionScore(run_id=run_id, dimensions={}, gate_passed=gate,
                          gate_violation=None if gate else "frame_break", score=score,
                          diagnosis="", weakest_dimension="growth")


# ── reused calibration checks work on EvolutionScore (duck-typed) ─────────────

def test_calibration_report_flags_good_below_bad_inversion():
    scores = {"g1": _score("g1", 2.0), "b1": _score("b1", 3.0)}
    buckets = {"g1": "good", "b1": "bad"}
    rep = calibration_report(scores, buckets, expected_violators=set())
    assert not rep.passed
    assert ("g1", "b1") in rep.inversions


def test_calibration_report_flags_uncaught_violator():
    scores = {"v1": _score("v1", 4.0, gate=True)}  # should have tripped the gate, didn't
    rep = calibration_report(scores, {"v1": "bad"}, expected_violators={"v1"})
    assert not rep.passed
    assert "v1" in rep.uncaught_violators


def test_calibration_report_passes_clean_set():
    scores = {"g1": _score("g1", 4.5), "b1": _score("b1", 1.5, gate=False)}
    rep = calibration_report(scores, {"g1": "good", "b1": "bad"}, expected_violators={"b1"})
    assert rep.passed


def test_noise_band_is_max_per_run_delta():
    a = {"r1": _score("r1", 3.0), "r2": _score("r2", 4.0)}
    b = {"r1": _score("r1", 3.4), "r2": _score("r2", 4.1)}
    assert abs(noise_band(a, b) - 0.4) < 1e-9


# ── bucket order (good > meh > bad means) ────────────────────────────────────

def test_bucket_order_ok_when_monotonic():
    scores = {"g": _score("g", 3.6), "m": _score("m", 2.8), "b": _score("b", 2.0, gate=False)}
    ok, violations = bucket_order_ok(scores, {"g": "good", "m": "meh", "b": "bad"})
    assert ok and violations == []


def test_bucket_order_catches_meh_above_good():
    # the exact inversion the first calibration exposed: a 'meh' outscored a 'good'
    scores = {"g": _score("g", 2.8), "m": _score("m", 3.8)}
    ok, violations = bucket_order_ok(scores, {"g": "good", "m": "meh"})
    assert not ok and ("good", "meh") in violations


# ── degraded council factory ─────────────────────────────────────────────────

def test_degraded_council_full_is_the_real_panel():
    assert degraded_council("full") == list(council.COUNCIL)


def test_degraded_council_single_lens_is_one_persona():
    assert len(degraded_council("single_lens")) == 1


def test_degraded_council_two_lens_and_arc_only():
    assert len(degraded_council("two_lens")) == 2
    assert len(degraded_council("arc_only")) == 1
    assert degraded_council("arc_only") != degraded_council("single_lens")


def test_degraded_council_planted_violator_adds_a_saboteur():
    full = degraded_council("full")
    pv = degraded_council("planted_violator")
    assert len(pv) == len(full) + 1
    assert any("flying mount" in p.lens.lower() or "death knight" in p.lens.lower() for p in pv)
