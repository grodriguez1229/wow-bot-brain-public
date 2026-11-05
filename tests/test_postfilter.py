from postfilter import clean_line, has_emoji, is_narration, strip_asterisk_actions

NAMES = ["Montacedo", "Neimo", "Esterini", "Pazuwo", "Cetroh"]


def test_strips_emoji_runs():
    out, flags = clean_line("gg everyone 🎉🎉🔥🔥😂😂😂👍🏽❤️✨")
    assert out == "gg everyone" and "emoji" in flags
    assert not has_emoji(out)


def test_all_emoji_line_becomes_empty():
    out, _ = clean_line("😂😂😂")
    assert out == ""


def test_clean_text_untouched():
    out, flags = clean_line("anyone up for Deadmines? need a healer")
    assert out == "anyone up for Deadmines? need a healer" and flags == []


def test_drops_mashed_name_tokens():
    out, flags = clean_line("lol montacedo neimocedrocetroh you there", known_names=NAMES)
    assert "neimocedrocetroh" not in out and "mashed" in flags
    assert out.startswith("lol montacedo")      # exact name kept


def test_keeps_exact_and_possessive_names():
    text = "hey Esterini, nice sword Esterinis"
    out, flags = clean_line(text, known_names=NAMES)
    assert out == text and flags == []


def test_keeps_laughter_and_allowlisted_long_words():
    text = "hahahahahahaha noooooooooooooo congratulations on 40"
    out, flags = clean_line(text, known_names=NAMES)
    assert out == text and flags == []


def test_truncates_at_sentence_end():
    text = "Grinding murlocs here in Westfall all night. " + "the drops are terrible and " * 8
    out, flags = clean_line(text, max_len=140)
    assert out == "Grinding murlocs here in Westfall all night." and "truncated" in flags


def test_truncates_at_word_boundary_without_sentence_end():
    text = "so i was running around the lake looking for the last few crawlers, " * 4
    out, flags = clean_line(text, max_len=140)
    assert len(out) <= 140 and not out.endswith(",") and "truncated" in flags
    assert text.startswith(out)


def test_truncation_drops_dangling_function_words():
    out, _ = clean_line("nah expensive later i think so", max_len=25)
    assert out == "nah expensive later"
    out, _ = clean_line("heading north for westfall first then ill hit it", max_len=44)
    assert out == "heading north for westfall first"
    out, _ = clean_line("the the the the the the the the the", max_len=10)
    assert out                                  # never trims to nothing


def test_no_cap_when_max_len_none():
    text = "a" * 10 + " word" * 80
    out, flags = clean_line(text)
    assert "truncated" not in flags


def test_narration_detected():
    assert is_narration("...sighs Pazuwo softly while walking toward the inn", "Pazuwo")
    assert is_narration("Pazuwo stretches and looks around", "Pazuwo")
    assert is_narration("*stretches* ok who wants to group", "Pazuwo")


def test_narration_not_flagged_for_normal_chat():
    assert not is_narration("its Pazuwo, the warrior from earlier", "Pazuwo")
    assert not is_narration("thanks Esterini, appreciate it", "Pazuwo")
    assert not is_narration("hey whats up", "Pazuwo")
    assert not is_narration("ok", "")


def test_strip_asterisk_actions():
    assert strip_asterisk_actions("*waves* hey there *grins*") == "hey there"


def test_keeps_role_slash_and_hyphen_and_url_tokens():
    for text in ["LF warrior/paladin/druid for SFK",
                 "thinking about taking leatherworking",
                 "damage-over-time is nuts",
                 "check wowhead.com/item=19019"]:
        out, flags = clean_line(text, known_names=NAMES)
        assert out == text and flags == [], text


def test_drops_mashed_run_inside_plain_word():
    out, flags = clean_line("lol marshmarshlands everywhere", known_names=NAMES)
    assert out == "lol everywhere" and "mashed" in flags


def test_narration_detected_verb_list():
    assert is_narration("Bapoh watches as some grumpy wolf trots past", "Bapoh")
    assert is_narration("Pazuwo sighed and walked off", "Pazuwo")


def test_narration_not_flagged_verb_list_false_positives():
    assert not is_narration("my Zozhee takes some damage", "Zozhee")
    assert not is_narration("Zozhee needs a healer", "Zozhee")
    assert not is_narration("Zozhee always tanks", "Zozhee")
    assert not is_narration("hey guys Zozhee here", "Zozhee")
    assert not is_narration("bless Zozhee", "Zozhee")
    assert not is_narration("Hope Ykanu finds some mana potions", "Ykanu")
    assert not is_narration("My boyfriend says Trean looks like he hasnt slept", "Trean")
    assert not is_narration("**bold** point", "Zozhee")


def test_long_legit_words_not_mangled():
    for w in ("procrastinating", "procrastination", "responsibilities", "straightforward",
              "recommendation", "weaponsmithing", "hammersmithing", "troubleshooting",
              "accomplishments", "unfortunately"):
        line = f"just {w} on my essay lol"
        out, flags = clean_line(line, known_names=NAMES)
        assert out == line, (w, flags)
