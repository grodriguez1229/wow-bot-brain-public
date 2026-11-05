from irl_identity import IRL_IDENTITIES, compose_identity

NAMES = [f"Bot{i:03d}x" for i in range(200)]


def test_deterministic_per_name():
    assert compose_identity("Pazuwo") == compose_identity("Pazuwo")


def test_archetype_kept_when_given():
    for a in IRL_IDENTITIES:
        assert compose_identity("Trean", a["id"])["archetype"] == a["id"]


def test_unknown_archetype_falls_back_to_valid_one():
    out = compose_identity("Trean", "no_such_archetype")
    assert out["archetype"] in {a["id"] for a in IRL_IDENTITIES}


def test_composed_people_are_distinct():
    whos = [compose_identity(n)["who"] for n in NAMES]
    assert len(set(whos)) >= 190


def test_sixteen_archetypes_all_reachable():
    seen = {compose_identity(n)["archetype"] for n in NAMES}
    assert len(IRL_IDENTITIES) == 16
    assert len(seen) >= 14


def test_typing_styles_have_no_quoted_catchphrases():
    for a in IRL_IDENTITIES:
        assert "'" not in a["typing_style"] and '"' not in a["typing_style"], a["id"]
        assert "roger" not in a["typing_style"].lower()


def test_minors_have_no_partner_and_live_with_family():
    for n in NAMES:
        out = compose_identity(n, "highschool_kid")
        facts = " ".join(out["irl_facts"]).lower()
        for w in ("girlfriend", "boyfriend", "wife", "husband", "married"):
            assert w not in facts
        assert any(w in facts for w in ("parents", "mom", "dad", "grandparents"))


def test_minors_never_get_alcohol():
    for n in NAMES:
        for arch in ("highschool_kid", "overenthusiastic_newbie", "shy_girl"):
            facts = " ".join(compose_identity(n, arch)["irl_facts"]).lower()
            assert "beer" not in facts and "wine" not in facts


def test_couples_player_partner_is_fixed_and_named():
    out = compose_identity("Caramian", "couples_player")
    facts = " ".join(out["irl_facts"])
    words = [w for w in ("girlfriend", "boyfriend", "wife", "husband") if w in facts]
    assert len(words) == 1                      # exactly one partner word -> no gf/bf flip
    assert out["irl_terms"]                     # partner name is a classifier term
    assert compose_identity("Caramian", "couples_player") == out


def test_stayathome_parent_has_kids():
    for n in NAMES[:30]:
        facts = " ".join(compose_identity(n, "stayathome_parent")["irl_facts"])
        assert "kid" in facts


def test_who_is_core_plus_facts_and_core_is_generic():
    out = compose_identity("Lelindea", "retail_worker")
    assert out["who"].startswith(out["who_core"])
    for f in out["irl_facts"]:
        assert f in out["who"]
    assert "Best Buy" not in out["who_core"]


def test_signature_rate_roughly_sixty_percent():
    sigs = [compose_identity(n)["signature"] for n in NAMES]
    share = sum(s is not None for s in sigs) / len(sigs)
    assert 0.45 <= share <= 0.75


def test_couples_signature_uses_own_partner_word():
    for n in NAMES:
        out = compose_identity(n, "couples_player")
        if out["signature"] and "says hi" in out["signature"]:
            facts = " ".join(out["irl_facts"])
            word = out["signature"].split()[1]
            assert word in facts
            assert out["signature_irl"] is True


def test_irl_terms_lowercase():
    for n in NAMES[:50]:
        for t in compose_identity(n)["irl_terms"]:
            assert t == t.lower() and t
