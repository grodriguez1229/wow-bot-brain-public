"""Authored example bank for organic chat voice (R8). Pure data + a tiny parser.

All lines are ORIGINAL, written for this server: vanilla only (level cap 60, no
expansion content). They show register, not content: fragments, abbreviations,
lowercase, reactions, the odd typo, mostly short. Never sent verbatim — the model is
asked to match the register, and near-copies of an example are re-rolled.

Line prefix tags (optional, before a "|"):
  A / H      only shown to Alliance / Horde bots (city- or zone-specific lines)
  @lo-hi     only shown to bots whose level is within lo..hi
e.g. "H@13-18|LFG RFC" or "A|wheres the boat to auberdine".
"""
from __future__ import annotations

import re
from typing import NamedTuple

SHAPES = ("reaction", "question", "fragment", "ad", "ramble")
CHANNELS = ("GENERAL", "TRADE", "LFG", "GUILD", "SAY")

_RAW: dict[str, dict[str, list[str]]] = {
    "GENERAL": {
        "reaction": [
            "lol", "lmao", "haha", "rofl", "same", "ya", "yep", "nope", "true", "ugh", "rip",
            "omg", "wow", "gz", "grats", "o.O", "wtf", "lol what", "no way", "idk", "fair",
            "lol same", "gl", "nice", "hah", "lolol", "ikr", "yea no", "rly?", "LOL", "lol xD", "meh",
            "wtf!?", "ye", "fail", "nice one dude", "omg -.-",
        ],
        "question": [
            "H|where is mankrik's wife", "A|wheres the mage trainer in IF",
            "anyone know where to turn this in", "how do i get to booty bay",
            "is there a flight path here", "@1-20|what lvl do u get a mount",
            "where do u learn fishing", "@25-35|any1 know a good grind spot for 30s",
            "wheres the inn", "is the server lagging for anyone else",
            "whats a good prof for a warrior", "H|how do i get to UC from org",
            "A|wheres the boat to auberdine", "anyone else stuck on this quest",
            "where do the gnolls spawn", "whats the coords for the cave",
            "@10-25|is the barrens always this big", "how long till 60 usually",
            "who sells mana water here",
        ],
        "fragment": [
            "this zone is so ugly", "brb food", "@40-60|finally got my mount",
            "@28-32|ding 30", "ding!", "murlocs are the worst", "H|alliance camping the FP again",
            "A|horde ganking in stv again", "@30-45|stv is a warzone tonight",
            "server feels empty today", "that quest chain took forever",
            "got one shot by an elite lol", "forgot to train again", "nvm found it",
            "thx for the help earlier", "need more bag space", "im so broke",
            "this music is so good tho", "@1-15|wolves everywhere", "kobolds again...",
            "grinding is so boring", "nm i got it", "that took way too long",
            "my hearth is on cd ugh", "spent all my gold on skills",
            "H|barrens chat never changes", "tbh this quest is bugged", "lag is killing me =/",
        ],
        "ramble": [
            "just spent like an hour looking for this one named mob and some guy tagged it right in front of me. not even mad just impressed",
            "ok so i accidentally sold my good sword to the vendor and had to buy it back for way more, great start to the night",
            "tried to do the quest solo, died 3 times, corpse ran back every time, finally got it lol worth it",
            "why does every quest in this zone want 10 of something and the drop rate is like 5 percent",
        ],
    },
    "GUILD": {
        "reaction": [
            "gz!", "grats", "lol", "nice!", "ty", "np", "hey all", "hi", "o/", "night all", "gn",
            "wb", "lol nice", "ha", "ugh", "hahaha", "yay", "sweet", "ty ty", "gz man", ":D", "ok :D",
            "lol lol", "o.o",
        ],
        "question": [
            "anyone around?", "anyone need anything from the AH",
            "@28-45|who wants to run SM later", "can someone make me a bag",
            "@1-20|any1 have spare linen", "whos on", "@58-60|what time is MC tonight",
            "does anyone have tailoring", "@45-60|how far r u from 60", "where is everyone",
            "any1 got a spare stack of water", "who has mining",
        ],
        "fragment": [
            "back", "brb dog", "omw", "@38-42|40!!! mount time", "ding", "gonna log soon",
            "need 2 more lvls", "selling some greens if any1 wants", "on my alt",
            "thx for the bag", "afk 5", "lagging bad", "@28-32|just hit 30 lol",
            "that was fun guys", "made some gold today finally", "ok im back for real",
            "dying a lot tonight lol",
        ],
        "ramble": [
            "finally finished the whole quest chain, took me all night and the reward is a green i cant even use lol",
            "@40-50|if anyone needs help with the elite quests in the hinterlands later im around for a bit",
            "ok so my little brother logged onto my char and spent all my silver on a pet. im not even mad",
        ],
    },
    "SAY": {
        "reaction": [
            "oops", "oh no", "run!", "lol", "ty", "thx for the buff", "ty for heals", "np", "hi",
            "hey", "sorry", "my bad", "gg", "nice pull", "oof", "phew", "close one", "help",
            "wait", "omg", "yikes", "nice", "sry :(", "ooops :P", "OMG", "ty mate",
        ],
        "question": [
            "u doing this quest too?", "want to group for this?", "can i get a buff",
            "is this the right cave", "did u get the drop?", "is he up?", "u need this one?",
            "where does he spawn", "which way to the quest guy", "u almost done here?",
        ],
        "fragment": [
            "oom", "need to drink", "adds incoming", "this mob hits hard", "was that ur tag?",
            "sry was afk", "almost dead", "brb", "he respawned already", "ill wait",
            "go ahead u take it", "i need 3 more", "just looking around", "nice view up here",
            "lol he runs away at low hp", "stupid gnolls", "eating", "1 more and im done",
        ],
        "ramble": [
            "if u wait like 2 min he respawns, ill let u tag him first since u were here before me",
            "i swear this cave has more kobolds every time i come back, they must be breeding in here",
        ],
    },
    "TRADE": {
        "ad": [
            "WTS [Linen Cloth] x20", "wtb [Iron Ore] pst", "LF enchanter",
            "selling [Wool Cloth] stacks cheap", "@25-50|WTB [Mageweave Cloth]",
            "LF tailor to make [Linen Bag]", "@20-45|WTS [Heavy Leather] 2s ea",
            "@15-40|WTB stack of [Silk Cloth]", "lockbox opening pst", "wts [Minor Healing Potion]",
            "@35-60|LF smith to make [Mithril Spurs]", "wts [Copper Bar] x20",
        ],
        "question": [
            "how much is [Iron Ore] going for", "anyone selling bags?", "price check [Silk Cloth]?",
            "any enchanters on?", "anyone have a spare 6 slot bag", "any miners selling copper",
            "anyone selling [Swiftthistle]", "who can make [Heavy Linen Bandage]",
            "how much for a stack of wool", "any LW around",
        ],
        "reaction": [
            "lol no", "too much", "pst", "sold", "ty!", "nvm got it", "no ty", "cheaper on AH",
            "rofl", "ouch", "still need it?", "lol ok", "ha", "no shit", "meh", "xD",
        ],
        "fragment": [
            "trade chat is wild today", "AH prices are crazy rn", "price is firm",
            "still selling", "out of stock sorry", "someone undercut me by 1c lol",
            "AH is a ripoff", "nobody buys anything",
        ],
        "ramble": [
            "the AH is so broken today, someone put [Wool Cloth] up for like 10x what it sells for and people are actually buying it",
            "every time i list something somebody undercuts me by 1 copper within 5 minutes, its like they live on the AH",
        ],
    },
    "LFG": {
        "ad": [
            "@30-45|lf1m heals sm cath", "H@13-18|LFG RFC", "@17-25|lfm wc need tank",
            "@20-30|LF2M SFK", "A@17-26|lf tank deadmines", "A@22-30|need 1 more for stocks",
            "@28-38|lfg gnomer", "@44-52|LF3M ZF", "@40-50|lfm uld need heals",
            "@45-55|lf1m dps mara", "@52-60|lfg brd any", "@55-60|LFM UBRS need 2",
            "@57-60|lf healer strat ud", "@57-60|LFG scholo", "@28-36|lfm rfk last spot",
            "@22-30|LFG BFD", "@30-40|lf dps SM lib", "@50-58|need tank for ST",
        ],
        "reaction": [
            "inv", "inv pls", "x", "me", "still need?", "full", "ty all", "1 spot left",
            "where u at", "lol", "pst", "on my way", "gl",
        ],
        "question": [
            "need a tank?", "what lvl range?", "still need heals?", "@20-28|can a 24 come?",
            "do u have a healer", "@28-45|which wing?", "how many u need", "is it a full run",
            "any tanks around", "can u summon?",
        ],
        "fragment": [
            "omw", "need 1 more then go", "heading to the stone", "lf more", "ready when u are",
            "tank left, need new one", "group full ty", "still looking for heals",
        ],
        "ramble": [
            "@17-25|lf healer for wc, we have tank and 3 dps, just need someone who knows the way to the end lol",
        ],
    },
}

# (prior line someone else said, a reply to it). Tags on the prior line apply to the pair.
_RAW_PAIRS: list[tuple[str, str]] = [
    ("anyone know where the flight master is", "on the hill by the inn"),
    ("H|where is mankrik's wife", "lol nobody knows"),
    ("@38-42|finally hit 40", "gz!"),
    ("@30-45|lf1m heals sm cath", "can heal, inv"),
    ("anyone selling bags", "got some 6 slots pst"),
    ("brb food", "k"),
    ("this zone is so ugly", "wait till u see the swamp lol"),
    ("is the server lagging for anyone else", "ya its bad"),
    ("how do i get to booty bay", "run south thru stv"),
    ("@28-32|ding 30", "grats"),
    ("gnolls everywhere", "ya theyre so annoying"),
    ("@28-38|lfg gnomer", "we need 1 more, want inv?"),
    ("wtb [Iron Ore]", "how many"),
    ("night all", "gn"),
    ("anyone around?", "yo"),
    ("can someone make me a bag", "what kind"),
    ("im so broke", "same lol"),
    ("got one shot by an elite lol", "rip"),
    ("whats a good prof for a warrior", "mining and smithing prob"),
    ("is this the right cave", "think its the next one"),
    ("u need this one?", "nah go ahead"),
    ("thx for the buff", "np"),
    ("ty for heals", "anytime"),
    ("oom", "same sec"),
    ("need to drink", "k waiting"),
    ("adds incoming", "on it"),
    ("did u get the drop?", "nope :("),
    ("where does he spawn", "back of the camp usually"),
    ("any enchanters on?", "me, what u need"),
    ("how much is [Silk Cloth] going for", "check AH lol"),
    ("still need heals?", "ya inv"),
    ("@28-45|which wing?", "cath"),
    ("what lvl range?", "25-30ish"),
    ("need a tank?", "yes pls"),
    ("trade chat is wild today", "always is"),
    ("selling [Wool Cloth] stacks cheap", "how cheap"),
    ("i hate this quest", "which one"),
    ("anyone want to group for the elites", "sure what lvl r u"),
    ("@50-59|almost 60", "nice almost there"),
    ("murlocs are the worst", "that noise tho"),
    ("forgot to train again", "lol every time"),
    ("@40-60|got my mount finally", "nice what kind"),
    ("guild run tonight?", "im down"),
    ("gonna log soon", "cya"),
    ("back", "wb"),
    ("lagging bad", "me too"),
    ("tank left, need new one", "ugh"),
    ("@1-20|anyone have spare linen", "got like 10 u can have"),
    ("does anyone have tailoring", "i do, what u need"),
    ("help", "omw"),
    ("sry was afk", "np"),
    ("my bad", "all good"),
    ("he respawned already", "lol fast"),
    ("go ahead u take it", "ty!"),
    ("need 2 more lvls", "u got this"),
    ("@58-60|what time is MC tonight", "8 server time"),
    ("selling some greens if any1 wants", "what u got"),
    ("anyone else hear the music in duskwood", "so creepy"),
    ("whos on", "me"),
    ("why is everything so expensive", "AH barons lol"),
    ("this mob hits hard", "its elite lol"),
    ("inv pls", "sent"),
    ("@17-25|lfm wc need tank", "warrior here, inv"),
    ("A|how do i get to kalimdor from here", "boat in menethil"),
    ("H|alliance camping the FP again", "where at"),
    ("server feels empty today", "ya dead tonight"),
    ("my hearth is on cd ugh", "lol walk"),
]


class Example(NamedTuple):
    text: str
    shape: str
    lo: int
    hi: int
    faction: str | None   # "Alliance" / "Horde" / None (both)


_TAG = re.compile(r"^([AH])?(?:@(\d+)-(\d+))?\|(.*)$")
_FACTION = {"A": "Alliance", "H": "Horde"}


def parse_tagged(raw: str) -> tuple[str, int, int, str | None]:
    m = _TAG.match(raw)
    if not m:
        return raw, 1, 60, None
    f, lo, hi, text = m.groups()
    return text, int(lo or 1), int(hi or 60), _FACTION.get(f) if f else None


def _build() -> dict[str, list[Example]]:
    out: dict[str, list[Example]] = {}
    for ch, by_shape in _RAW.items():
        out[ch] = [Example(*_split(raw, shape)) for shape, lines in by_shape.items() for raw in lines]
    return out


def _split(raw: str, shape: str):
    text, lo, hi, fac = parse_tagged(raw)
    return text, shape, lo, hi, fac


CHANNEL_EXAMPLES: dict[str, list[Example]] = _build()


class ReplyPair(NamedTuple):
    prior: str
    reply: str
    lo: int
    hi: int
    faction: str | None


REPLY_PAIRS: list[ReplyPair] = [
    ReplyPair(p[0], r, p[1], p[2], p[3]) for raw, r in _RAW_PAIRS for p in [parse_tagged(raw)]
]


def fits(ex, level: int, faction: str | None) -> bool:
    return ex.lo <= level <= ex.hi and (ex.faction is None or faction is None or ex.faction == faction)


# (their whisper, your reply) for the whisper lane (R9). Level- and faction-neutral:
# no dungeon/raid/zone names, no self-introductions, mostly a few words.
WHISPER_PAIRS: list[tuple[str, str]] = [
    ("hey", "yo"),
    ("sup", "not much, questing"),
    ("hows it going", "eh cant complain"),
    ("u there?", "ya whats up"),
    ("hi!", "hey hey"),
    ("wanna group?", "what for"),
    ("can u help me with a quest", "which one"),
    ("thx for earlier", "np anytime"),
    ("ty for the help", "np"),
    ("lol that was close", "way too close"),
    ("u still on?", "for a bit"),
    ("whatcha doing", "grinding, u?"),
    ("you busy?", "kinda, whats up"),
    ("need anything?", "nah im good"),
    ("got a sec?", "sure"),
    ("hows the grind", "slow lol"),
    ("u see that guy in chat", "lmao ya"),
    ("are u a bot", "lol no"),
    ("what u up to tonight", "prob just leveling"),
    ("nice gear", "ty finally"),
    ("gz on the ding", "ty!"),
    ("i died again", "rip"),
    ("this quest is killing me", "which one lol"),
    ("want to duel", "maybe later"),
    ("you know where the trainer is", "back of town i think"),
    ("can i get a buff", "sure sec"),
    ("lag is awful rn", "ya same"),
    ("brb food", "k"),
    ("back", "wb"),
    ("gonna log soon", "cya"),
    ("good night", "night!"),
    ("any tips?", "keep ur bags empty lol"),
    ("u selling anything", "nah sorry"),
    ("how much gold u got", "like 3g lol"),
    ("you play a lot?", "too much honestly"),
    ("long day?", "ugh yes"),
    ("you at work tomorrow", "ya sadly"),
    ("lol", "lol"),
    ("u mad?", "nah just tired"),
    ("help me kill this guy", "omw"),
    ("where u at", "out questing"),
    ("thanks man", "anytime"),
    ("u remember me?", "kinda? remind me"),
    ("this zone sucks", "for real"),
    ("lets do this", "ok lead"),
]


# Login-whisper openers (R9): what a friend whispers when you log on. Grouped by kind.
# No place names at all (the prompt supplies the only places a bot may name), no
# self-introductions, mostly a few words.
OPENER_EXAMPLES: dict[str, list[str]] = {
    "callback": [
        "round 2?", "we gotta do that again", "gg on that run btw", "that run was fun",
        "that was a good one", "same crew again?", "again sometime?", "that was fun lol",
        "good times lol", "u up for another?", "we should go back", "ready for round 2?",
        "fun run btw", "we make a good team lol", "still thinking about that run lol",
        "that was a blast", "go again tonight?",
    ],
    "invite": [
        "want an inv?", "need a hand?", "wanna group up?", "questing nearby, join?",
        "got room for 1 more", "come group, im close", "want help w/ quests?",
        "lets duo some quests", "im around, want an inv?", "need a run thru?",
        "i can carry u thru", "wanna come along?", "free run if u want",
        "got time for a run?", "u wanna quest together?", "sending inv if u want",
    ],
    "checkin": [
        "yo", "hey", "o/", "sup", "hey u on", "hey dude", "wb", "evening", "yo whats up",
        "back at it huh", "hey hows it goin", "sup man", "ah u made it", "hey hey",
        "what u up to tonight", "u leveling tonight?",
    ],
}

# Check-in lines that imply the player was away a while: shown only after a long absence.
OPENER_LONG_ABSENCE_EXAMPLES: list[str] = [
    "hey stranger lol", "about time lol", "where u been", "been a while man", "look who it is",
    "long time no see",
]

# Authored openers used when the model can't produce a grounded line twice (R9).
# "where u been" is only used after a long absence (login_whisper decides).
OPENER_FALLBACKS: dict[str, list[str]] = {
    "callback": ["yo", "hey u on"],
    "invite": ["want an inv?", "u wanna group?"],
    "checkin": ["yo", "hey", "o/", "sup", "where u been"],
}
