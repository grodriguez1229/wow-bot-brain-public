from llm import build_llm_options


def test_options_carry_num_predict_and_temperature():
    opts = build_llm_options(50)
    assert opts["num_predict"] == 50
    assert opts["temperature"] == 0.9  # preserved from the pre-slice behavior


def test_options_include_antirepetition_knobs():
    opts = build_llm_options(160)
    assert opts["repeat_penalty"] >= 1.1          # punishes recycled phrasing
    assert 0.0 < opts["min_p"] < 1.0              # tail cutoff for coherence
    assert 0.0 < opts["top_p"] <= 1.0
    assert opts["repeat_last_n"] >= 64            # window the penalty looks back over
