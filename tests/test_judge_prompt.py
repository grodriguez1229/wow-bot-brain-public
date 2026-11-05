from pathlib import Path

from sim.judge import DIMENSIONS


def test_rubric_prompt_covers_schema():
    text = Path("prompts/judge.md").read_text()
    for dim in DIMENSIONS:
        assert dim in text, f"rubric prompt missing dimension {dim}"
    for token in ["gate_passed", "gate_violation", "diagnosis", "1-5", "JSON"]:
        assert token in text, f"rubric prompt missing {token}"
