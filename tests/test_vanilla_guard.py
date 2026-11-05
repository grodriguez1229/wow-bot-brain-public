from vanilla_guard import find_banned


def test_flags_post_vanilla_content():
    assert find_banned("anyone flying to Outland") == ["flying", "outland"]
    assert find_banned("lf dk for ICC") == ["dk", "icc"]
    assert find_banned("whats ur ilvl") == ["ilvl"]
    assert find_banned("in queue for LFD") == ["queue", "lfd"]
    assert find_banned("my Draenei shaman") == ["draenei"]


def test_vanilla_lines_pass():
    for s in ("lf1m heals sm cath", "wtb [Linen Cloth] x20", "where is mankrik's wife",
              "uldaman anyone", "omg finally dinged 40", "need 2 for ubrs", "naxx is so hard",
              "ironforge", "arthas' tears for sale", "gz", "karma lol"):
        assert find_banned(s) == [], s


def test_word_boundaries():
    assert find_banned("uldaman") == []          # not "ulduar"
    assert find_banned("dkp") == []              # dkp is vanilla, "dk" is not
    assert find_banned("gemstone") == []
    assert find_banned("tocs") == []
