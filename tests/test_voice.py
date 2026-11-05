import collections
import json
import random

import voice
from voice_examples import CHANNEL_EXAMPLES


def setup_function():
    voice.reset_state()


def test_pick_shape_weights():
    rng = random.Random(1)
    lfg = collections.Counter(voice.pick_shape("LFG", rng) for _ in range(2000))
    assert lfg.most_common(1)[0][0] == "ad" and lfg["ad"] / 2000 > 0.7
    gen = collections.Counter(voice.pick_shape("GENERAL", rng) for _ in range(2000))
    assert "ad" not in gen and gen["fragment"] > gen["ramble"]
    assert 0.05 < gen["ramble"] / 2000 < 0.16


def test_reply_shapes_never_ad():
    rng = random.Random(2)
    shapes = {voice.pick_shape("TRADE", rng, reply=True) for _ in range(500)}
    assert "ad" not in shapes and "reaction" in shapes


def test_unknown_channel_falls_back_to_general():
    assert voice.pick_shape("YELL", random.Random(0)) in voice.SHAPE_WEIGHTS["GENERAL"]


def test_shape_budget():
    assert voice.shape_budget("reaction") == 25
    assert voice.shape_budget("ramble") == 140
    assert voice.shape_budget("nonsense") == 70


def test_sample_examples_mostly_matching_shape():
    rng = random.Random(3)
    ex = voice.sample_examples("GENERAL", "question", level=30, faction="Horde", k=10, rng=rng)
    assert len(ex) == 10
    qs = {e.text for e in CHANNEL_EXAMPLES["GENERAL"] if e.shape == "question"}
    assert sum(e in qs for e in ex) == 6


def test_sample_examples_respect_band_and_faction():
    rng = random.Random(4)
    for _ in range(50):
        ex = voice.sample_examples("LFG", "ad", level=15, faction="Alliance", k=12, rng=rng)
        assert "LFG RFC" not in ex                 # Horde-only
        assert "@57-60|LFG scholo" not in ex and "LFG scholo" not in ex   # level 57+


def test_rotation_never_repeats_set():
    rng = random.Random(5)
    prev = None
    for _ in range(100):
        cur = frozenset(voice.sample_examples("SAY", "reaction", level=20, k=10, rng=rng))
        assert cur != prev
        prev = cur


def test_reply_pairs_sample():
    pairs = voice.sample_reply_pairs(4, level=20, faction="Horde", rng=random.Random(6))
    assert len(pairs) == 4 and all(isinstance(p, tuple) and len(p) == 2 for p in pairs)


def test_is_example_copy():
    exs = ["anyone know where to turn this in", "lol"]
    assert voice.is_example_copy("anyone know where to turn this in?", exs)
    assert voice.is_example_copy("Anyone know where to turn this in lol", exs)
    assert not voice.is_example_copy("lol", exs)            # short lines exempt
    assert not voice.is_example_copy("where do i sell these wolf pelts", exs)


def test_corpus_loader_filters(tmp_path, monkeypatch):
    p = tmp_path / "c.jsonl"
    rows = [
        {"channel": "GENERAL", "text": "lol xD", "era": "unknown"},
        {"channel": "GENERAL", "text": "three flying mounts", "era": "unknown"},   # banned
        {"channel": "GENERAL", "text": "boost thru ulduar", "era": "wotlk"},       # era
        {"channel": "OTHER", "text": "nice one dude", "era": "unknown"},
        {"channel": "WHISPER_IN", "text": "hi", "era": "unknown"},                # not public
        {"channel": "OTHER", "text": "piss off", "era": "unknown"},              # profane
        {"channel": "SAY", "text": "is anyone else lagging?", "era": "vanilla"},
        {"channel": "TRADE", "text": "only 5 euros per 1000 gold", "era": "unknown"},  # spam
        {"channel": "SAY", "text": "healing 48k hp tank is hard", "era": "unknown"},  # numbers
        {"channel": "TRADE", "text": "wts [Lionseye]", "era": "unknown"},             # link
        {"channel": "SYSTEM", "text": "You receive loot", "era": "unknown"},          # system
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    out = voice.load_corpus(str(p))
    assert [e.text for e in out["GENERAL"]] == ["lol xD", "nice one dude"]
    assert out["SAY"][0].shape == "question"
    assert voice.load_corpus("") == {}
    assert voice.load_corpus(str(tmp_path / "missing.jsonl")) == {}


def test_corpus_off_by_default():
    assert voice.VOICE_CORPUS_PATH == ""
