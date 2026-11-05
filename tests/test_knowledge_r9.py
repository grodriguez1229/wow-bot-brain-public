import pytest

import knowledge as k
from knowledge import (DUNGEONS, FINAL_BOSSES, RAIDS, canonical_place, dungeons_for_level,
                       mentioned_places, ungrounded_mentions, zones_for_level)
from vanilla_guard import find_banned


def test_final_bosses_cover_every_dungeon():
    assert set(FINAL_BOSSES) == {d[0] for d in DUNGEONS}
    for v in FINAL_BOSSES.values():
        assert find_banned(v) == []
    assert FINAL_BOSSES["Wailing Caverns"] == "Mutanus the Devourer"
    assert FINAL_BOSSES["Deadmines"] == "Edwin VanCleef"


def test_canonical_place_maps_map_names():
    assert canonical_place("The Deadmines") == "Deadmines"
    assert canonical_place("The Deadmines") in FINAL_BOSSES
    assert canonical_place("Wailing Caverns") == "Wailing Caverns"
    assert canonical_place("Teldrassil") == "Teldrassil"
    assert canonical_place("The Temple of Atal'Hakkar") == "Sunken Temple"
    assert canonical_place("Blackrock Spire") == "Lower Blackrock Spire"
    assert canonical_place("Nowhere") is None


def test_every_dungeon_name_canonicalises_to_itself():
    for d in DUNGEONS:
        assert canonical_place(d[0]) == d[0] or d[0] == "The Stockade"
        assert canonical_place(d[0]) in FINAL_BOSSES


def test_ungrounded_mentions():
    assert ungrounded_mentions("lol mutanus again?", "ran Wailing Caverns") == []
    assert ungrounded_mentions("deadmines later?", "ran Wailing Caverns") == ["Deadmines"]
    assert ungrounded_mentions("yo", "") == []


@pytest.mark.parametrize("alias,place", [
    ("wc", "Wailing Caverns"), ("dm", "Deadmines"), ("vc", "Deadmines"), ("sfk", "Shadowfang Keep"),
    ("rfk", "Razorfen Kraul"), ("rfd", "Razorfen Downs"), ("bfd", "Blackfathom Deeps"),
    ("zf", "Zul'Farrak"), ("st", "Sunken Temple"), ("brd", "Blackrock Depths"),
    ("lbrs", "Lower Blackrock Spire"), ("ubrs", "Upper Blackrock Spire"), ("strat", "Stratholme"),
    ("scholo", "Scholomance"), ("mc", "Molten Core"), ("bwl", "Blackwing Lair"),
    ("zg", "Zul'Gurub"), ("ony", "Onyxia's Lair"), ("sm", "Scarlet Monastery"),
    ("ulda", "Uldaman"), ("mara", "Maraudon"), ("gnomer", "Gnomeregan"), ("stocks", "The Stockade"),
])
def test_short_aliases(alias, place):
    assert canonical_place(alias) == place


def test_short_alias_flagged_unless_in_history():
    assert ungrounded_mentions("wc again?", "ran Deadmines") == ["Wailing Caverns"]
    assert ungrounded_mentions("wc again?", "we did Wailing Caverns") == []
    assert ungrounded_mentions("WC again?", "ran Wailing Caverns last night") == []


def test_short_aliases_not_matched_mid_word():
    for t in ("lol i'm still here", "my dmg sucks", "stuff and things", "wcw", "smile", "mcdonalds",
              "ground", "costs a lot", "first strategy"):
        assert mentioned_places(t) == set(), t


def test_find_violations_unchanged_for_ambiguous_shorts():
    assert k.find_violations("wc and st and dm", 5) == []


def test_levels_tables():
    assert dungeons_for_level(10, "Alliance") == []
    assert "Deadmines" in dungeons_for_level(14, "Alliance")
    assert "Ragefire Chasm" not in dungeons_for_level(14, "Alliance")
    assert "Darkshore" in zones_for_level(10, "Alliance")
    assert "Stranglethorn Vale" not in zones_for_level(10, "Alliance")
    raids = {r[0] for r in RAIDS}
    for lv in range(1, 61):
        assert not raids & set(dungeons_for_level(lv, None))
