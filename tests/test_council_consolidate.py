"""Cycle-2 deterministic identity consolidation: kill near-twin facets and the
high-weight monoculture mechanically, instead of trusting the LLM prose rules
(which it ignored in cycle 1 — cafe_crust/cafeteria_crust both survived at w5)."""
from council import consolidate_facets


def test_near_duplicate_content_collapses_to_highest_weight():
    # The real cycle-1 failure: two near-identical facets under different subject keys.
    facets = [
        {"subject": "cafe_crust", "weight": 5,
         "content": "scraping that burnt crust off the tray feels like the only part of the day"},
        {"subject": "cafeteria_crust", "weight": 3,
         "content": "scraping that burnt crust off the tray feels like the only part of the day that doesnt belong"},
        {"subject": "gus", "weight": 2,
         "content": "youre the only one who gets the silence after a shift"},
    ]
    out = consolidate_facets(facets)
    subjects = {f["subject"] for f in out}
    assert "cafe_crust" in subjects          # higher-weight twin kept
    assert "cafeteria_crust" not in subjects  # near-twin dropped
    assert "gus" in subjects                  # distinct facet untouched
    assert len(out) == 2


def test_distinct_content_is_not_merged():
    facets = [
        {"subject": "coffee", "weight": 3, "content": "i need a massive coffee before i can think"},
        {"subject": "westfall", "weight": 3, "content": "westfall is the only quiet place left"},
        {"subject": "gus", "weight": 2, "content": "drifting apart from gus lately"},
    ]
    out = consolidate_facets(facets)
    assert len(out) == 3  # nothing merged


def test_weight_ceiling_keeps_at_most_two_strong_demotes_rest():
    # Five DISTINCT facets all at w5 -> only the top 2 stay strong; the rest drop to 3.
    facets = [
        {"subject": "a", "weight": 5, "content": "alpha distinct line one"},
        {"subject": "b", "weight": 5, "content": "bravo distinct line two"},
        {"subject": "c", "weight": 5, "content": "charlie distinct line three"},
        {"subject": "d", "weight": 4, "content": "delta distinct line four"},
        {"subject": "e", "weight": 2, "content": "echo distinct line five"},
    ]
    out = {f["subject"]: f["weight"] for f in consolidate_facets(facets)}
    strong = [s for s, w in out.items() if w >= 4]
    assert len(strong) == 2          # at most two strong facets
    assert out["e"] == 2             # weak facet untouched
    assert all(w <= 3 for s, w in out.items() if s not in strong)


def test_empty_and_single_are_safe():
    assert consolidate_facets([]) == []
    one = [{"subject": "x", "weight": 5, "content": "only one here"}]
    assert consolidate_facets(one) == one
