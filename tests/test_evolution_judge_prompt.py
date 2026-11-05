from pathlib import Path

RUBRIC = Path(__file__).resolve().parent.parent / "prompts" / "evolution_judge.md"


def test_rubric_names_all_five_dimensions():
    text = RUBRIC.read_text()
    for dim in ["growth", "believability", "continuity", "diversity", "rootedness"]:
        assert dim in text, f"missing dimension {dim}"


def test_rubric_names_all_four_guardrails():
    text = RUBRIC.read_text()
    for gate in ["frame_break", "template_betrayal", "identity_collapse", "fixation"]:
        assert gate in text, f"missing guardrail {gate}"


def test_rubric_demands_single_json_and_no_overall_score():
    text = RUBRIC.read_text().lower()
    assert "json" in text
    # the harness derives the overall score; the judge must not compute it
    assert "do not compute" in text or "don't compute" in text
