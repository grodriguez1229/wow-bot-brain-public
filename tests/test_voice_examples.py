import statistics

from postfilter import has_emoji
from vanilla_guard import find_banned
from voice_examples import (CHANNEL_EXAMPLES, CHANNELS, REPLY_PAIRS, SHAPES, fits,
                            parse_tagged)


def _all_texts():
    for exs in CHANNEL_EXAMPLES.values():
        for e in exs:
            yield e.text
    for p in REPLY_PAIRS:
        yield p.prior
        yield p.reply


def test_every_channel_has_enough_lines():
    for ch in CHANNELS:
        assert len(CHANNEL_EXAMPLES[ch]) >= 40, ch


def test_reply_pairs_count():
    assert len(REPLY_PAIRS) >= 60


def test_shapes_valid_and_ads_only_in_trade_lfg():
    for ch, exs in CHANNEL_EXAMPLES.items():
        for e in exs:
            assert e.shape in SHAPES
            if e.shape == "ad":
                assert ch in ("TRADE", "LFG")


def test_bank_is_vanilla_clean():
    hits = {t: find_banned(t) for t in _all_texts() if find_banned(t)}
    assert hits == {}


def test_bank_has_no_emoji_or_quotes():
    for t in _all_texts():
        assert not has_emoji(t), t
        assert '"' not in t, t


def test_bank_register_is_short():
    lens = [len(e.text) for exs in CHANNEL_EXAMPLES.values() for e in exs]
    assert statistics.median(lens) <= 40
    assert sum(n <= 20 for n in lens) / len(lens) >= 0.25


def test_no_duplicate_lines_within_channel():
    for ch, exs in CHANNEL_EXAMPLES.items():
        texts = [e.text for e in exs]
        assert len(texts) == len(set(texts)), ch


def test_tags_parse():
    assert parse_tagged("H@13-18|LFG RFC") == ("LFG RFC", 13, 18, "Horde")
    assert parse_tagged("A|boat") == ("boat", 1, 60, "Alliance")
    assert parse_tagged("@20-30|x") == ("x", 20, 30, None)
    assert parse_tagged("plain line") == ("plain line", 1, 60, None)


def test_fits_filters_level_and_faction():
    rfc = next(e for e in CHANNEL_EXAMPLES["LFG"] if e.text == "LFG RFC")
    assert fits(rfc, 15, "Horde")
    assert not fits(rfc, 15, "Alliance")
    assert not fits(rfc, 40, "Horde")
