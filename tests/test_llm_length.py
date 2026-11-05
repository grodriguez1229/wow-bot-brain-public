from llm import truncate_sentences


def test_keeps_short_reply_intact():
    assert truncate_sentences("lol yeah", 4) == "lol yeah"


def test_truncates_to_max_sentences():
    text = "one here. two here. three here. four here. five here."
    out = truncate_sentences(text, 2)
    assert out == "one here. two here."


def test_allows_up_to_four_for_chat():
    text = "ugh yeah. retail sucks. some guy yelled at me. anyway killing murlocs. this is the fifth."
    out = truncate_sentences(text, 4)
    assert out.count(".") == 4
    assert "fifth" not in out


def test_swallows_consecutive_punctuation():
    out = truncate_sentences("omg how do i get there?? no idea lol. extra here.", 1)
    assert out == "omg how do i get there??"


def test_ignores_early_period_below_min_chars():
    # "u." should not count as a full sentence and chop the reply
    out = truncate_sentences("u. wanna group up for deadmines later", 1)
    assert "deadmines" in out
