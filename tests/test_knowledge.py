from knowledge import build_knowledge_section, find_violations, find_postvanilla


# ── post-vanilla terms at runtime (narrower than the authored-text guard) ────────

def test_postvanilla_flags_expansion_content():
    assert find_postvanilla("anyone doing dailies") == ["dailies"]
    assert find_postvanilla("lf heroics tonight") == ["heroics"]
    assert find_postvanilla("leveling in Outland") == ["outland"]


def test_postvanilla_allows_vanilla_words_the_authored_guard_bans():
    for s in ("used heroic strike", "flying to IF", "queued for wsg", "casting wrath",
              "hellfire on the pack", "illidan was in wc3", "my daily walk"):
        assert find_postvanilla(s) == [], s


def test_postvanilla_still_catches_the_unambiguous_phrases():
    assert find_postvanilla("doing my daily quests") == ["daily quests"]
    assert find_postvanilla("got a flying mount") == ["flying mount"]
    assert find_postvanilla("hellfire peninsula") == ["hellfire peninsula"]


# ── level-gated content ───────────────────────────────────────────────────────

def test_raid_talk_at_low_level_is_a_violation():
    assert find_violations("anyone for MC tonight?", level=15) == ["mc"]
    assert find_violations("finally got my onyxia attunement", level=20) == ["onyxia", "attunement"]


def test_raid_talk_near_cap_is_fine():
    assert find_violations("anyone for MC tonight?", level=60) == []
    assert find_violations("need ony attunement still", level=56) == []


def test_dungeon_a_few_levels_ahead_is_fine():
    assert find_violations("cant wait for SM", level=26) == []
    assert find_violations("LF stratholme run", level=30) == ["stratholme"]


def test_ambiguous_words_are_not_matched():
    for s in ("whats the strat for this", "the temple is pretty", "going to the library irl",
              "DM me later", "so much xp"):
        assert find_violations(s, level=10) == [], s


def test_high_zone_at_low_level_is_a_violation():
    assert find_violations("questing in silithus", level=12) == ["silithus"]
    assert find_violations("questing in silithus", level=56) == []
    assert find_violations("questing in westfall", level=12) == []


def test_postvanilla_is_a_violation_at_any_level():
    assert find_violations("doing dailies", level=60) == ["dailies"]


def test_terms_the_other_person_said_are_allowed():
    # A level 20 answering "you been to MC?" may say MC back.
    assert find_violations("nah never been to MC", level=20, allowed_from="you been to MC yet?") == []
    assert find_violations("nah never been to MC, ony either", level=20,
                           allowed_from="you been to MC yet?") == ["ony"]


# ── prompt section ─────────────────────────────────────────────────────────────

def test_section_lists_level_appropriate_places():
    s = build_knowledge_section(12, "Alliance")
    assert "Westfall" in s and "Deadmines" in s
    assert "Silithus" not in s and "Molten Core" not in s
    assert "Durotar" not in s                      # other faction's starter zone


def test_section_respects_faction():
    s = build_knowledge_section(14, "Horde")
    assert "Barrens" in s and "Ragefire" in s
    assert "Westfall" not in s and "Deadmines" not in s


def test_section_at_cap_mentions_raids():
    s = build_knowledge_section(60, "Horde")
    assert "Molten Core" in s


def test_section_tells_the_model_what_it_does_not_know():
    s = build_knowledge_section(12, "Alliance").lower()
    assert "only heard of" in s or "never been" in s
