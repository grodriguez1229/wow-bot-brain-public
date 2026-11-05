"""Line shapes + example sampling for organic chat voice (R8).

Before generating, code picks a SHAPE (reaction / question / fragment / ad / ramble) per
channel. Each shape has a char budget (post-filter max_len) and a token budget. The
prompt shows 8-12 example lines of that channel, mostly of the chosen shape, rotated so
two consecutive prompts for a channel never show the same set."""
from __future__ import annotations

import json
import random
import re

from config import EXAMPLES_PER_PROMPT, FLEET_DEDUP_THRESHOLD, SHAPE_BUDGETS, VOICE_CORPUS_PATH
from vanilla_guard import find_banned
from voice_examples import CHANNEL_EXAMPLES, REPLY_PAIRS, WHISPER_PAIRS, Example, fits

# Ambient (not replying) shape weights per channel. LFG/TRADE are mostly template ads.
SHAPE_WEIGHTS: dict[str, dict[str, int]] = {
# Tuned toward a real-chat calibration (non-system lines: median 18ch, 54% <=20ch).
    "GENERAL": {"reaction": 25, "question": 25, "fragment": 42, "ramble": 8},
    "GUILD":   {"reaction": 40, "question": 18, "fragment": 37, "ramble": 5},
    "SAY":     {"reaction": 40, "question": 12, "fragment": 43, "ramble": 5},
    "TRADE":   {"ad": 70, "question": 15, "reaction": 5, "fragment": 8, "ramble": 2},
    "LFG":     {"ad": 82, "question": 8, "reaction": 4, "fragment": 6},
}
# Replying to someone: mostly quick reactions and short remarks, never an ad.
REPLY_SHAPE_WEIGHTS = {"reaction": 55, "question": 10, "fragment": 32, "ramble": 3}
# Whispering back (R9): still short, a bit more room for a real answer now and then.
WHISPER_SHAPE_WEIGHTS = {"reaction": 35, "question": 15, "fragment": 40, "ramble": 10}

SHAPE_NUM_PREDICT = {"reaction": 12, "question": 22, "fragment": 30, "ad": 30, "ramble": 64}
SHAPE_MAX_SENTENCES = {"reaction": 1, "question": 1, "fragment": 2, "ad": 1, "ramble": 3}
SHAPE_HINT = {
    "reaction": "a quick reaction, 1 to 3 words",
    "question": "a short question, at most 7 words",
    "fragment": "a short remark, at most 6 words, no explaining",
    "ad": "a short ad, abbreviations",
    "ramble": "a longer rant or story, one run-on sentence, at most 25 words",
}


def pick_shape(channel: str, rng=None, *, reply: bool = False, whisper: bool = False) -> str:
    rng = rng or random
    if reply:
        w = WHISPER_SHAPE_WEIGHTS if whisper else REPLY_SHAPE_WEIGHTS
    else:
        w = SHAPE_WEIGHTS.get(channel, SHAPE_WEIGHTS["GENERAL"])
    return rng.choices(list(w), weights=list(w.values()), k=1)[0]


def shape_budget(shape: str) -> int:
    return SHAPE_BUDGETS.get(shape, SHAPE_BUDGETS["fragment"])


# ── optional real-chat corpus (style reference, off by default) ─────────────
_CORPUS_CHANNELS = {"GENERAL": "GENERAL", "OTHER": "GENERAL", "SAY": "SAY", "PARTY": "SAY",
                    "YELL": "SAY", "GUILD": "GUILD", "TRADE": "TRADE", "LFG": "LFG"}
_PROFANE = re.compile(r"\b(?:fuck\w*|shit\w*|bitch\w*|cunt\w*|\w*rape\w*|fag\w*|retard\w*|"
                      r"nigg\w*|piss\w*|whore\w*|slut\w*|fuk\w*|fck\w*|abortion|porn\w*|"
                      r"cock\w*|dick\w*|stfu)", re.IGNORECASE)
# gold-seller spam, real-money talk, post-vanilla numbers (48k hp), item links of unknown era
_JUNK = re.compile(r"euro|\$|www\.|\.com\b|per \d+ ?gold|\d+(?:\.\d+)?k\b|\[|\]", re.IGNORECASE)
_corpus_cache: dict[str, dict[str, list[Example]]] = {}


def _infer_shape(text: str) -> str:
    if len(text) <= 12:
        return "reaction"
    if text.rstrip().endswith("?"):
        return "question"
    return "ramble" if len(text) > 70 else "fragment"


def load_corpus(path: str) -> dict[str, list[Example]]:
    """Extra examples from a jsonl transcript (fields: channel, text, era). Keeps only
    vanilla/unknown-era lines of a public channel that pass the vanilla guard and a
    profanity filter. Missing/unreadable file -> {}. Cached per path."""
    if not path:
        return {}
    if path in _corpus_cache:
        return _corpus_cache[path]
    out: dict[str, list[Example]] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                ch = _CORPUS_CHANNELS.get(str(row.get("channel", "")).upper())
                text = " ".join(str(row.get("text", "")).split())
                if (not ch or not text or len(text) > 90 or '"' in text
                        or str(row.get("era", "unknown")).lower() not in ("vanilla", "unknown")
                        or find_banned(text) or _PROFANE.search(text) or _JUNK.search(text)):
                    continue
                out.setdefault(ch, []).append(Example(text, _infer_shape(text), 1, 60, None))
    except OSError:
        out = {}
    _corpus_cache[path] = out
    return out


# ── example sampling with rotation ──────────────────────────────────────────
_last_sets: dict[str, frozenset] = {}


def reset_state() -> None:
    _last_sets.clear()


def _pool(channel: str, level: int, faction: str | None) -> list[Example]:
    base = CHANNEL_EXAMPLES.get(channel, CHANNEL_EXAMPLES["GENERAL"])
    extra = load_corpus(VOICE_CORPUS_PATH).get(channel, [])
    return [e for e in base + extra if fits(e, level, faction)]


def sample_examples(channel: str, shape: str, *, level: int = 30, faction: str | None = None,
                    k: int | None = None, rng=None) -> list[str]:
    """~60% of `k` examples of `shape` from this channel, the rest other shapes, shuffled.
    Never returns the same set as the previous call for the same channel."""
    rng = rng or random
    k = k or EXAMPLES_PER_PROMPT
    pool = _pool(channel, level, faction)
    primary = [e.text for e in pool if e.shape == shape]
    other = [e.text for e in pool if e.shape != shape]
    picked: list[str] = []
    for _ in range(6):
        n_p = min(len(primary), max(1, round(k * 0.6)))
        picked = rng.sample(primary, n_p) + rng.sample(other, min(len(other), k - n_p))
        if frozenset(picked) != _last_sets.get(channel):
            break
    rng.shuffle(picked)
    _last_sets[channel] = frozenset(picked)
    return picked


def sample_reply_pairs(n: int = 4, *, level: int = 30, faction: str | None = None,
                       rng=None) -> list[tuple[str, str]]:
    rng = rng or random
    pool = [(p.prior, p.reply) for p in REPLY_PAIRS if fits(p, level, faction)]
    return rng.sample(pool, min(n, len(pool)))


def sample_whisper_pairs(n: int = 4, rng=None) -> list[tuple[str, str]]:
    """`n` distinct (their whisper, your reply) examples for the whisper lane (R9)."""
    rng = rng or random
    return rng.sample(WHISPER_PAIRS, min(n, len(WHISPER_PAIRS)))


def _toks(text: str) -> frozenset:
    return frozenset(re.findall(r"[a-z0-9]+", (text or "").lower()))


def is_example_copy(text: str, examples) -> bool:
    """True when `text` is a verbatim/near copy of a shown example. Lines of <=3 tokens
    are exempt — "lol" or "inv pls" are everyone's words, not a copy."""
    t = _toks(text)
    if len(t) <= 3:
        return False
    for ex in examples:
        e = _toks(ex)
        if e and len(t & e) / len(t | e) >= FLEET_DEDUP_THRESHOLD:
            return True
    return False
