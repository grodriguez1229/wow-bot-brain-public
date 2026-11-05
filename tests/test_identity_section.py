from memory_prompt import build_identity_section


def test_empty_returns_blank():
    assert build_identity_section(None) == ""
    assert build_identity_section([]) == ""


def test_renders_facets_strongest_first():
    facets = [
        {"subject": "pugs", "content": "done with pugs after getting ninja-looted", "weight": 2},
        {"subject": "outlook", "content": "weirdly into late-night philosophy tangents", "weight": 4},
    ]
    out = build_identity_section(facets)
    assert out.startswith("WHO YOU'VE BECOME")
    # strongest (weight 4) listed before weaker (weight 2)
    assert out.index("philosophy") < out.index("ninja-looted")
    assert "- done with pugs" in out


def test_skips_blank_content():
    facets = [{"subject": "x", "content": "  ", "weight": 3}]
    assert build_identity_section(facets) == ""
