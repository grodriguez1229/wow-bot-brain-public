"""Cheap output post-filter for generated chat lines (R3, live-check finding #4). Pure.

clean_line repairs what is mechanical (emoji, mashed bot-name tokens, run-on length);
is_narration flags third-person narration so the caller can re-roll or stay silent."""
from __future__ import annotations

import re

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍⃣\U000E0020-\U000E007F]")
_ASTERISK = re.compile(r"(?<!\*)\*(?!\*)[^*\n]{2,}?(?<!\*)\*(?!\*)")
_LONG_OK = {"congratulations", "responsibility", "transportation", "disappointment",
            "accomplishment", "recommendations", "professionally", "unfortunately",
            "understandable", "characteristics", "internationally", "misunderstanding",
            "leatherworking", "blacksmithing", "procrastinating", "procrastination",
            "responsibilities", "straightforward", "recommendation", "weaponsmithing",
            "hammersmithing", "troubleshooting", "accomplishments"}
_NARR_VERBS = ("sigh|smile|grin|laugh|nod|shrug|stretch|yawn|look|watch|walk|wander|glance|mutter|"
               "whisper|chuckle|frown|wave|sit|stand|lean|rub|scratch|peer|gaze|turn|pause|wink|giggle|"
               "groan|mumble|hum|sip|adjust|tilt|step|trot|stroll|smirk|blink|stare")
_NARR_VERB_RE = rf"(?:{_NARR_VERBS})(?:s|es|ed|d)"
_NARR_EXEMPT = {"my", "our", "hope", "says", "said", "tell", "told", "thanks", "thx", "think",
                "guess", "bless", "hey"}
_MIN_NAME = 5
_DANGLING = {"i", "a", "an", "the", "to", "and", "or", "but", "for", "of", "in", "on", "at", "my",
             "u", "you", "ur", "your", "then", "so", "with", "w/", "if", "im", "i'm", "ill", "i'll",
             "is", "was", "are", "be", "it", "its", "that", "this", "we", "he", "she", "they",
             "just", "like", "from", "by", "as", "when"}


def has_emoji(text: str) -> bool:
    return bool(_EMOJI.search(text or ""))


def _is_mashed(core: str, names: list[str]) -> bool:
    if core in _LONG_OK or len(set(core)) < 6:          # laughter / elongations
        return False
    for n in names:
        if n in core and len(core) >= len(n) + 3:
            return True
    return len(core) >= 14


def _truncate(text: str, max_len: int) -> str:
    head = text[:max_len]
    cut = max(head.rfind("."), head.rfind("!"), head.rfind("?"))
    if cut >= max_len // 4:
        return head[:cut + 1].strip()
    sp = head.rfind(" ")
    out = head[:sp] if sp > 0 else head
    out = out.rstrip(" ,;:-—")
    # R8: a cut mid-thought shouldn't end on "... then ill" / "... later i".
    words = out.split()
    while len(words) > 1 and words[-1].lower().strip(",;:") in _DANGLING:
        words.pop()
    return " ".join(words).rstrip(" ,;:-—")


def clean_line(text: str, *, max_len: int | None = None, known_names=()) -> tuple[str, list[str]]:
    flags: list[str] = []
    out = text or ""
    if _EMOJI.search(out):
        out = _EMOJI.sub("", out)
        flags.append("emoji")
    names = [n.lower() for n in known_names if n and len(n) >= _MIN_NAME]
    kept = []
    for tok in out.split():
        runs = re.findall(r"[a-z]+", tok.lower())
        if any(_is_mashed(r, names) for r in runs):
            if "mashed" not in flags:
                flags.append("mashed")
            continue
        kept.append(tok)
    out = " ".join(kept).strip()
    if max_len and len(out) > max_len:
        out = _truncate(out, max_len)
        flags.append("truncated")
    return out, flags


def is_narration(text: str, bot_name: str) -> bool:
    text = text or ""
    if _ASTERISK.search(text):
        return True
    if not bot_name:
        return False
    n = re.escape(bot_name)
    if re.search(rf"\b{_NARR_VERB_RE}\s+{n}\b", text, re.IGNORECASE):
        return True
    for m in re.finditer(rf"(\w+\s+)?\b{n}\s+{_NARR_VERB_RE}\b", text, re.IGNORECASE):
        prev = (m.group(1) or "").strip().lower()
        if prev not in _NARR_EXEMPT:
            return True
    return False


def strip_asterisk_actions(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _ASTERISK.sub("", text or "")).strip()


# ── self-introduction (R9) ───────────────────────────────────────────────────
_INTRO_ANY = re.compile(r"\bmy name(?:'s|s| is)\b|\bname's\b|\b(?:i am|im|i'm) a (?:level|lvl)\b")
_YOU = re.compile(r"\b(?:ur|u|you|your|you're|youre|ya'll)\b")
_ME = re.compile(r"\b(?:i|im|i'm|my|me)\b")
_CLAUSE = re.compile(r"(?<=[.!?,;])\s+")


def _words_rx(phrase: str) -> str:
    return r"\s+".join(re.escape(w) for w in (phrase or "").lower().split())


def is_self_intro(text: str, *, bot_name: str, race: str, class_name: str, level: int) -> bool:
    """True when a reply introduces the bot: its own name ("im X", "X here", "my name is"),
    or its own level / race+class stated as a fact ("lvl 60 hunter here", "night elf hunter",
    "im level 20"). Questions about the other person ("ur a rogue right", "lvl 10 rogue?")
    are not intros. Whether the player asked is the caller's call."""
    t = " ".join((text or "").lower().replace("’", "'").split())
    if not t:
        return False
    name = _words_rx(bot_name)
    if name and re.search(rf"\b(?:im|i'm|i am)\s+{name}\b|\b{name}\s+here\b", t):
        return True
    if _INTRO_ANY.search(t):
        return True
    race_rx, cls_rx = _words_rx(race), _words_rx(class_name)
    attrs = [rf"\b(?:level|lvl)\s*{int(level)}\b"] if level else []
    if race_rx and cls_rx:
        attrs.append(rf"\b{race_rx}\s+{cls_rx}\b")
    own = "|".join(x for x in (race_rx, cls_rx) if x)
    if own:
        attrs.append(rf"\b(?:level|lvl)\s*\d+\s+(?:{own})\b")
    rx = re.compile("|".join(attrs)) if attrs else None
    for clause in _CLAUSE.split(t):
        if not rx or not rx.search(clause):
            continue
        if clause.rstrip().endswith("?") or (_YOU.search(clause) and not _ME.search(clause)):
            continue                                    # asking about them, not stating
        return True
    return False
