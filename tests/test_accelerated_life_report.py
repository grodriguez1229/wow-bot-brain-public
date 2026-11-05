from sim.accelerated_life import _consolidation_summary


def test_consolidation_summary_shows_revision_signal():
    trail = [
        {"day": 1, "identity_facets": [{"subject": "a"}, {"subject": "b"}],
         "applied_edits": [1, 2, 3]},
        {"day": 2, "identity_facets": [{"subject": "a"}, {"subject": "c"}],
         "applied_edits": [1, 2, 3, 4]},  # b dropped, c added -> net +1 -1, but 4 edits
    ]
    out = _consolidation_summary(trail)
    assert "| 1 | 2 | +2 -0 | 3 |" in out
    assert "| 2 | 2 | +1 -1 | 4 |" in out
    assert "revised/merged" in out
