from pathlib import Path

from sim.optimize.guard import ALLOWED_PATHS


def test_optimizer_prompt_names_whitelist_and_rules():
    text = Path("prompts/optimizer.md").read_text()
    for p in ALLOWED_PATHS:
        assert p in text, f"optimizer prompt missing whitelisted file {p}"
    for token in ["ONE", "weakest", "diagnose", "do NOT", "orchestration"]:
        assert token in text, f"optimizer prompt missing {token}"
