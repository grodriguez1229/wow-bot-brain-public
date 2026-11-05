from capabilities import MOTIVATIONS, capabilities


def test_motivations_list():
    assert MOTIVATIONS == ["gold_maker", "dungeon_seeker", "guild_recruiter",
                           "helper_social", "world_explorer", "farmer"]


def test_party_invite_always_present():
    for m in MOTIVATIONS:
        assert "party_invite" in capabilities(m, can_guild_invite=False)


def test_motivation_base_caps():
    assert "sell_goods" in capabilities("gold_maker", can_guild_invite=False)
    assert "party_recruit" in capabilities("dungeon_seeker", can_guild_invite=False)
    assert "help" in capabilities("helper_social", can_guild_invite=False)
    assert "explore" in capabilities("world_explorer", can_guild_invite=False)
    assert "farm" in capabilities("farmer", can_guild_invite=False)


def test_guild_invite_requires_rank():
    assert "guild_invite" not in capabilities("guild_recruiter", can_guild_invite=False)
    assert "guild_invite" in capabilities("guild_recruiter", can_guild_invite=True)
    assert "guild_invite" not in capabilities("gold_maker", can_guild_invite=True)
