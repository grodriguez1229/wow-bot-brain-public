import collections
import random
import re

import ad_templates as ad
from postfilter import has_emoji
from vanilla_guard import find_banned

CLASSES = list(ad.CLASS_ROLES)


def setup_function():
    ad.reset_state()


def _many(channel, n=2000, seed=0):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        lvl = rng.randint(1, 60)
        fac = rng.choice(("Alliance", "Horde"))
        out.append((lvl, fac, ad.make_ad(channel, f"Bot{i % 150}", lvl, rng.choice(CLASSES), fac, rng)))
    return out


def test_ads_are_vanilla_clean_short_and_plain():
    for ch in ("LFG", "TRADE"):
        for lvl, fac, s in _many(ch):
            if s is None:
                continue
            assert find_banned(s) == [], s
            assert not has_emoji(s) and '"' not in s
            assert 3 <= len(s) <= 60, s
            assert s == s.strip() and "  " not in s


def test_lfg_dungeons_level_and_faction_appropriate():
    rng = random.Random(1)
    for _ in range(300):
        s = ad.make_lfg("Zed", 15, "Warrior", "Alliance", rng).lower()
        assert "rfc" not in s and "ragefire" not in s       # horde-only
        assert not re.search(r"\b(?:brd|ubrs|mc|strat|scholo)\b", s)
    assert ad.make_lfg("Zed", 8, "Warrior", "Horde", rng) is None


def test_lfg_raids_only_at_60():
    rng = random.Random(2)
    texts = [ad.make_lfg("Y", lv, "Priest", "Horde", rng).lower() for lv in (45, 58, 59) for _ in range(100)]
    assert not any(re.search(r"\b(?:mc|ony|zg|molten core)\b", t) for t in texts)


def test_trade_item_variety():
    rng = random.Random(3)
    items = []
    for i in range(200):
        s = ad.make_trade(f"B{i}", 30, "Warrior", "Horde", rng)
        m = re.search(r"\[([^\]]+)\]", s)
        if m:
            items.append(m.group(1))
    top = collections.Counter(items).most_common(1)[0][1]
    assert top / len(items) <= 0.10
    assert len(set(items)) >= 15


def test_trade_items_level_appropriate():
    rng = random.Random(4)
    for _ in range(300):
        s = ad.make_trade("Low", 10, "Mage", "Alliance", rng)
        assert "Runecloth" not in s and "Black Lotus" not in s and "Arcanite" not in s


def test_per_item_recency_blocks_immediate_repeat():
    rng = random.Random(5)
    seen = []
    for _ in range(12):
        s = ad.make_trade("R", 30, "Warrior", "Horde", rng)
        m = re.search(r"\[([^\]]+)\]", s)
        if m:
            seen.append(m.group(1))
    assert len(seen) == len(set(seen))


def test_style_is_stable_per_bot_and_varies_across_bots():
    assert ad.ad_style("Gungran") == ad.ad_style("Gungran")
    styles = {tuple(sorted(ad.ad_style(f"N{i}").items())) for i in range(40)}
    assert len(styles) > 10


def test_lower_style_keeps_item_link_case():
    st = {"caps": "lower", "abbr": 0, "pst": "pst", "lvl": ""}
    assert ad._caps("WTS [Linen Cloth] x20", st, random.Random(0)) == "wts [Linen Cloth] x20"


def test_money():
    assert ad.money(5) == "5c"
    assert ad.money(250) == "2s" or ad.money(250) == "3s"
    assert ad.money(15000) == "1.5g"
    assert ad.money(150000) == "15g"


def test_non_ad_channel_returns_none():
    assert ad.make_ad("GENERAL", "X", 30, "Mage", "Horde") is None
