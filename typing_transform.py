"""Per-bot typing habits applied to generated chat lines (R8).

Each bot gets a stable style seeded by its name (like irl_identity): caps habit, how often
it drops trailing punctuation and apostrophes, which abbreviations it uses (u, ur, ty, np,
lf, pls, prob, idk, ppl, rn, ...), a small typo rate, and a lol / emoticon habit.
Applied AFTER the post-filter. Whispers get `light=True` (caps/punctuation/apostrophes
only). Never touches [bracketed item links], protected names, or tokens with digits."""
from __future__ import annotations

import hashlib
import random
import re

# (pattern, replacements). Matched case-insensitively on whole words.
ABBREVIATIONS = [
    (r"you are", ("ur", "u r")), (r"you're", ("ur",)), (r"your", ("ur",)), (r"you", ("u",)),
    (r"thanks|thank you", ("ty", "thx", "thanks")), (r"no problem", ("np",)),
    (r"looking for", ("lf", "looking for")), (r"please", ("pls", "plz")),
    (r"probably", ("prob", "prolly")), (r"i don'?t know", ("idk", "dunno")),
    (r"people", ("ppl",)), (r"right now", ("rn", "atm")), (r"because", ("cuz", "bc")),
    (r"though", ("tho",)), (r"okay", ("ok", "k")), (r"anyone", ("any1", "anyone", "ne1")),
    (r"going to", ("gonna",)), (r"want to", ("wanna",)), (r"got to", ("gotta",)),
    (r"really", ("rly", "really")), (r"level", ("lvl",)), (r"with", ("w/", "with")),
    (r"oh my god", ("omg",)), (r"be right back", ("brb",)), (r"for real", ("fr", "4 real")),
    (r"tonight", ("tonite", "tonight")), (r"something", ("somethin", "something")),
]
_ABBR_RE = [(re.compile(rf"(?<![\w'])(?:{p})(?![\w'])", re.IGNORECASE), reps) for p, reps in ABBREVIATIONS]
LAUGHS = ("lol", "lol", "haha", "lmao", "heh")
EMOTICONS = (":P", ":D", ":)", "=/", "xD", ":(")
_SEG = re.compile(r"(\[[^\]]*\])")


def style_for(bot_name: str) -> dict:
    seed = int(hashlib.sha256(f"type:{bot_name}".encode()).hexdigest()[:12], 16)
    r = random.Random(seed)
    n_abbr = r.randint(len(ABBREVIATIONS) // 4, len(ABBREVIATIONS) * 3 // 4)
    return {
        "caps": r.choices(("lower", "sentence", "asis"), weights=(55, 30, 15))[0],
        "drop_punct": r.uniform(0.5, 1.0),
        "drop_apos": r.choice((0.0, 0.3, 0.7, 0.9)),
        "abbrevs": frozenset(r.sample(range(len(ABBREVIATIONS)), n_abbr)),
        "abbr_rate": r.uniform(0.4, 1.0),
        "typo_rate": 0.0 if r.random() < 0.4 else r.uniform(0.01, 0.04),
        "laugh_rate": 0.0 if r.random() < 0.5 else r.uniform(0.05, 0.15),
        "laugh": r.choice(LAUGHS),
        "emoticon_rate": 0.0 if r.random() < 0.6 else r.uniform(0.03, 0.08),
        "emoticon": r.choice(EMOTICONS),
        "shout_rate": 0.0 if r.random() < 0.7 else 0.15,   # "LOL" / "OMG" on reactions
    }


def _protected(tok: str, protect: set[str]) -> bool:
    core = re.sub(r"[^\w']", "", tok).lower()
    return bool(re.search(r"\d", tok)) or (core and core in protect)


def _typo(word: str, rng) -> str:
    i = rng.randrange(1, len(word) - 1)
    op = rng.randrange(3)
    if op == 0:
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]   # swap
    if op == 1:
        return word[:i] + word[i + 1:]                           # drop
    return word[:i] + word[i] + word[i:]                         # double


def _words(seg: str, fn) -> str:
    return re.sub(r"\S+", lambda m: fn(m.group(0)), seg)


def transform(text: str, bot_name: str, *, light: bool = False, protect=(), rng=None,
              max_len: int | None = None) -> str:
    if not text or not text.strip():
        return text
    rng = rng or random
    st = style_for(bot_name)
    prot = {p.lower() for p in protect if p}
    segs = _SEG.split(text)          # odd indexes are [links]

    def plain(fn):
        for i in range(0, len(segs), 2):
            segs[i] = fn(segs[i])

    if not light:
        def abbr(seg):
            for idx in st["abbrevs"]:
                rx, reps = _ABBR_RE[idx]
                seg = rx.sub(lambda m: m.group(0) if _protected(m.group(0), prot)
                             or rng.random() > st["abbr_rate"] else rng.choice(reps), seg)
            return seg
        plain(abbr)

        def typo(tok):
            if (st["typo_rate"] and len(tok) >= 4 and tok.isalpha() and not _protected(tok, prot)
                    and rng.random() < st["typo_rate"]):
                return _typo(tok, rng)
            return tok
        plain(lambda s: _words(s, typo))

    if st["drop_apos"] and rng.random() < st["drop_apos"]:
        plain(lambda s: _words(s, lambda t: t if _protected(t, prot) else
                               re.sub(r"(?<=[a-z])'(?=(?:m|t|s|re|ve|ll|d)\b)", "", t, flags=re.I)))

    if st["caps"] == "lower":
        plain(lambda s: _words(s, lambda t: t if _protected(t, prot) else t.lower()))

    out = "".join(segs).strip()
    if st["caps"] == "sentence" and out[:1].isalpha() and not _protected(out.split()[0], prot):
        out = out[0].upper() + out[1:]

    if out and out[-1] in ".!" and not out.endswith("..") and rng.random() < st["drop_punct"]:
        out = out.rstrip(".!").rstrip()
    elif out.endswith("?") and rng.random() < st["drop_punct"] * 0.5:
        out = out[:-1].rstrip()

    if not light:
        words = out.split()
        if (st["shout_rate"] and len(words) <= 2 and "[" not in out
                and rng.random() < st["shout_rate"]):
            out = out.upper()
        cap = max_len or 10 ** 6
        add = None
        if st["laugh_rate"] and rng.random() < st["laugh_rate"] and st["laugh"] not in out.lower():
            add = st["laugh"]
        elif st["emoticon_rate"] and rng.random() < st["emoticon_rate"]:
            add = st["emoticon"]
        if add and len(out) + len(add) + 1 <= cap:
            out = f"{out} {add}"
    return out or text
