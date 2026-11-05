"""Election for /heard: who answers when a player talks in a channel."""
import election
from election import named_in, cap_hearers, elect, note_bot_spoke, note_replied, reset_state, is_pass


def _h(name, distance=10.0):
    return {"bot_name": name, "distance": distance, "same_party": False, "same_guild": False}


def test_named_full_and_prefix_match():
    bots = ["Esterini", "Brogdurn", "Vivi"]
    assert named_in("hey esterini wanna group?", bots) == ["Esterini"]
    assert named_in("ester you there?", bots) == ["Esterini"]        # >=4-char prefix
    assert named_in("yo brogdurn and esterini!", bots) == ["Brogdurn", "Esterini"] or \
           named_in("yo brogdurn and esterini!", bots) == ["Esterini", "Brogdurn"]


def test_named_short_prefix_and_substring_do_not_match():
    bots = ["Esterini", "Vivi"]
    assert named_in("est is my favorite time zone", bots) == []      # <4 chars
    assert named_in("investing in linen", bots) == []                # substring, not word prefix
    assert named_in("vivi!", bots) == ["Vivi"]                       # exact name shorter than 4 ok


def test_cap_hearers_keeps_named_and_nearest():
    hearers = [_h(f"Bot{i:02d}", distance=float(i)) for i in range(40)]
    hearers.append(_h("Esterini", distance=999.0))
    kept = cap_hearers(hearers, "esterini help!", cap=30)
    names = [h["bot_name"] for h in kept]
    assert len(kept) == 30
    assert "Esterini" in names           # named retained despite max distance
    assert "Bot00" in names and "Bot38" not in names  # nearest fill the rest


class FakeRng:
    """random() returns queued values in order (then 1.0 = never fires)."""
    def __init__(self, values):
        self.values = list(values)
    def random(self):
        return self.values.pop(0) if self.values else 1.0


def _deps(fam=None, persona=None, convo=None):
    return dict(
        get_familiarity=lambda b: (fam or {}).get(b, 0),
        get_persona_text=lambda b: (persona or {}).get(b, ""),
        recent_convo=lambda b: (convo or {}).get(b, False),
    )


def setup_function(_):
    reset_state()


def test_named_always_elected_even_on_cooldown():
    note_replied("Esterini", "SAY", now=1000.0)
    out = elect([_h("Esterini")], "esterini hello again", "Abril", "SAY",
                **_deps(), now=1005.0, rng=FakeRng([]))
    assert out == [{"bot_name": "Esterini", "tier": "named"}]


def test_engaged_recent_channel_speaker_elected_on_roll():
    note_bot_spoke("Vivi", "GENERAL", now=1000.0)
    out = elect([_h("Vivi")], "anyone selling bags?", "Abril", "GENERAL",
                **_deps(), now=1060.0, rng=FakeRng([0.5]))   # 0.5 < 0.6 => fires
    assert out == [{"bot_name": "Vivi", "tier": "engaged"}]


def test_engaged_window_expired_falls_through():
    note_bot_spoke("Vivi", "GENERAL", now=1000.0)
    out = elect([_h("Vivi")], "anyone selling bags?", "Abril", "GENERAL",
                **_deps(), now=1200.0, rng=FakeRng([0.5]))   # 200s > 120s window
    assert out == []


def test_recent_convo_counts_as_engaged():
    out = elect([_h("Vivi")], "anyone selling bags?", "Abril", "GENERAL",
                **_deps(convo={"Vivi": True}), now=1000.0, rng=FakeRng([0.5]))
    assert out == [{"bot_name": "Vivi", "tier": "engaged"}]


def test_candidate_scored_by_familiarity_and_keywords_rolls_low_chance():
    deps = _deps(fam={"Esterini": 5}, persona={"Esterini": "run Deadmines or Wailing Caverns"})
    out = elect([_h("Esterini"), _h("Brogdurn")], "who wants deadmines?", "Abril", "GENERAL",
                **deps, now=1000.0, rng=FakeRng([0.1]))      # 0.1 < 0.15 => fires
    assert out == [{"bot_name": "Esterini", "tier": "candidate"}]


def test_zero_score_hearers_are_never_candidates():
    out = elect([_h("Brogdurn")], "who wants deadmines?", "Abril", "GENERAL",
                **_deps(), now=1000.0, rng=FakeRng([0.0]))
    assert out == []


def test_cap_two_non_named_but_named_exempt():
    for b in ("A1", "A2", "A3"):
        note_bot_spoke(b, "SAY", now=1000.0)
    hearers = [_h("A1"), _h("A2"), _h("A3"), _h("Esterini"), _h("Brogdurn")]
    out = elect(hearers, "esterini brogdurn look at this", "Abril", "SAY",
                **_deps(), now=1010.0, rng=FakeRng([0.0, 0.0, 0.0]))
    names = [e["bot_name"] for e in out]
    assert "Esterini" in names and "Brogdurn" in names       # named, exempt
    assert len([e for e in out if e["tier"] != "named"]) == 0  # cap already used by 2 named


def test_cooldown_blocks_non_named():
    note_bot_spoke("Vivi", "GENERAL", now=1000.0)
    note_replied("Vivi", "GENERAL", now=1005.0)
    out = elect([_h("Vivi")], "hello?", "Abril", "GENERAL",
                **_deps(), now=1010.0, rng=FakeRng([0.0]))   # 5s < 30s cooldown
    assert out == []


def test_is_pass():
    assert is_pass("PASS") and is_pass(" pass ") and is_pass("")
    assert not is_pass("PASSing through Deadmines")


def test_named_tier_capped_at_three():
    hearers = [_h(n) for n in ("Aaaa", "Bbbb", "Cccc", "Dddd")]
    out = elect(hearers, "aaaa bbbb cccc dddd help!", "Abril", "SAY",
                **_deps(), now=1000.0, rng=FakeRng([]))
    named = [e for e in out if e["tier"] == "named"]
    assert len(named) == 3
