"""Code-built LFG / TRADE ads (R8). No LLM call.

Level-appropriate vanilla dungeons and items, per-bot abbreviation style (seeded by bot
name, stable forever), and fleet-wide recency so one item/dungeon can't loop (the
"Linen Bags" problem). Pure apart from the small in-memory recency windows."""
from __future__ import annotations

import hashlib
import random
from collections import deque

# (names/abbreviations, lo, hi, faction or None)
DUNGEONS = [
    (("RFC", "rfc", "ragefire"), 13, 18, "Horde"),
    (("WC", "wc", "wailing caverns"), 17, 24, None),
    (("deadmines", "DM", "VC", "dm"), 17, 26, "Alliance"),
    (("SFK", "sfk", "shadowfang"), 22, 30, None),
    (("BFD", "bfd"), 24, 32, None),
    (("stocks", "stockades", "stockade"), 24, 32, "Alliance"),
    (("gnomer", "gnomeregan", "Gnomer"), 29, 38, None),
    (("RFK", "rfk", "kraul"), 29, 38, None),
    (("SM GY", "sm gy", "graveyard"), 28, 34, None),
    (("SM lib", "sm lib", "library"), 32, 38, None),
    (("SM arm", "sm armory", "armory"), 34, 42, None),
    (("SM cath", "sm cath", "cath"), 36, 45, None),
    (("RFD", "rfd", "downs"), 37, 46, None),
    (("uld", "uldaman", "Ulda"), 41, 51, None),
    (("ZF", "zf", "zul'farrak"), 44, 54, None),
    (("mara", "maraudon", "Mara"), 46, 55, None),
    (("ST", "sunken temple", "temple"), 50, 58, None),
    (("BRD", "brd", "BRD arena", "BRD emp run"), 52, 60, None),
    (("LBRS", "lbrs"), 55, 60, None),
    (("UBRS", "ubrs"), 58, 60, None),
    (("DM east", "DM north", "DM west", "dire maul"), 56, 60, None),
    (("strat live", "strat UD", "strat", "baron run"), 58, 60, None),
    (("scholo", "Scholo", "scholomance"), 58, 60, None),
    (("MC", "molten core"), 60, 60, None),
    (("ony", "Ony", "onyxia"), 60, 60, None),
    (("ZG", "zg"), 60, 60, None),
]

CLASS_ROLES = {
    "Warrior": ("tank", "dps"), "Paladin": ("heals", "dps"), "Priest": ("heals",),
    "Druid": ("tank", "heals", "dps"), "Shaman": ("heals", "dps"), "Mage": ("dps",),
    "Warlock": ("dps",), "Rogue": ("dps",), "Hunter": ("dps",),
}
CLASS_ABBR = {
    "Warrior": ("warr", "warrior", "war"), "Paladin": ("pally", "paladin", "pal"),
    "Priest": ("priest", "pri"), "Druid": ("druid", "dru"), "Shaman": ("shammy", "shaman", "sham"),
    "Mage": ("mage",), "Warlock": ("lock", "warlock", "wl"), "Rogue": ("rogue", "rog"),
    "Hunter": ("hunter", "hunt"),
}
NEED_WORDS = {"tank": ("tank",), "heals": ("heals", "healer", "heal"), "dps": ("dps", "dps")}

# (item, lo, hi, base copper per unit, sold in stacks)
ITEMS = [
    ("Linen Cloth", 5, 20, 12, True), ("Wool Cloth", 15, 30, 30, True),
    ("Silk Cloth", 20, 40, 60, True), ("Mageweave Cloth", 30, 50, 90, True),
    ("Runecloth", 45, 60, 140, True), ("Felcloth", 55, 60, 2500, False),
    ("Light Leather", 5, 20, 20, True), ("Medium Leather", 15, 30, 45, True),
    ("Heavy Leather", 25, 40, 90, True), ("Thick Leather", 35, 50, 120, True),
    ("Rugged Leather", 45, 60, 180, True),
    ("Copper Ore", 5, 20, 20, True), ("Tin Ore", 15, 30, 40, True), ("Iron Ore", 25, 45, 120, True),
    ("Mithril Ore", 35, 55, 150, True), ("Thorium Ore", 45, 60, 250, True),
    ("Copper Bar", 5, 20, 25, True), ("Bronze Bar", 15, 30, 70, True), ("Steel Bar", 25, 45, 150, True),
    ("Mithril Bar", 35, 55, 180, True), ("Thorium Bar", 45, 60, 300, True),
    ("Arcanite Bar", 58, 60, 60000, False), ("Dark Iron Ore", 55, 60, 2000, False),
    ("Peacebloom", 1, 15, 8, True), ("Silverleaf", 1, 15, 8, True), ("Earthroot", 5, 20, 15, True),
    ("Mageroyal", 10, 25, 30, True), ("Briarthorn", 10, 25, 30, True), ("Bruiseweed", 15, 30, 40, True),
    ("Swiftthistle", 15, 30, 60, True), ("Kingsblood", 20, 35, 50, True), ("Liferoot", 20, 35, 60, True),
    ("Fadeleaf", 25, 40, 70, True), ("Goldthorn", 25, 40, 70, True),
    ("Khadgar's Whisker", 30, 45, 80, True), ("Sungrass", 40, 55, 120, True),
    ("Arthas' Tears", 40, 55, 110, True), ("Gromsblood", 45, 60, 150, True),
    ("Dreamfoil", 50, 60, 200, True), ("Mountain Silversage", 50, 60, 250, True),
    ("Plaguebloom", 55, 60, 200, True), ("Black Lotus", 58, 60, 150000, False),
    ("Minor Healing Potion", 1, 15, 15, False), ("Lesser Healing Potion", 10, 25, 60, False),
    ("Healing Potion", 20, 35, 150, False), ("Greater Healing Potion", 30, 50, 300, False),
    ("Superior Healing Potion", 45, 60, 600, False), ("Major Healing Potion", 55, 60, 1500, False),
    ("Lesser Mana Potion", 15, 30, 100, False), ("Greater Mana Potion", 40, 55, 500, False),
    ("Major Mana Potion", 55, 60, 2000, False), ("Free Action Potion", 40, 60, 3000, False),
    ("Elixir of the Mongoose", 50, 60, 3000, False), ("Elixir of Giants", 50, 60, 2000, False),
    ("Heavy Linen Bandage", 5, 20, 20, False), ("Silk Bandage", 20, 35, 60, False),
    ("Heavy Mageweave Bandage", 35, 50, 150, False), ("Heavy Runecloth Bandage", 50, 60, 300, False),
    ("Linen Bag", 5, 25, 3000, False), ("Woolen Bag", 15, 30, 6000, False),
    ("Small Silk Pack", 20, 40, 15000, False), ("Mageweave Bag", 30, 60, 40000, False),
    ("Runecloth Bag", 45, 60, 100000, False),
    ("Strange Dust", 10, 30, 40, True), ("Lesser Magic Essence", 10, 25, 150, False),
    ("Soul Dust", 25, 40, 150, True), ("Vision Dust", 35, 50, 300, True),
    ("Dream Dust", 45, 55, 500, True), ("Illusion Dust", 50, 60, 800, True),
    ("Large Brilliant Shard", 55, 60, 30000, False), ("Arcane Crystal", 58, 60, 50000, False),
    ("Essence of Fire", 52, 60, 20000, False), ("Essence of Earth", 52, 60, 15000, False),
    ("Elemental Earth", 40, 60, 1500, False), ("Righteous Orb", 58, 60, 20000, False),
]
CRAFTS = {
    "tailor": ("Linen Bag", "Woolen Bag", "Small Silk Pack", "Mageweave Bag", "Runecloth Bag"),
    "LW": ("Heavy Leather", "Thick Leather"),
    "alch": ("Free Action Potion", "Greater Healing Potion", "Elixir of the Mongoose"),
    "smith": ("Steel Bar", "Mithril Bar", "Arcanite Bar"),
}
CITIES = {"Alliance": ("SW", "IF", "darn"), "Horde": ("org", "UC", "TB")}

_recent_items: deque = deque(maxlen=12)
_recent_dungeons: deque = deque(maxlen=6)


def reset_state() -> None:
    _recent_items.clear()
    _recent_dungeons.clear()


def ad_style(bot_name: str) -> dict:
    """Stable per-bot ad habits."""
    seed = int(hashlib.sha256(f"ad:{bot_name}".encode()).hexdigest()[:12], 16)
    r = random.Random(seed)
    return {
        "caps": r.choices(("upper", "lower", "mixed"), weights=(3, 5, 2))[0],
        "abbr": r.randrange(3),                       # which name variant it prefers
        "pst": r.choice(("pst", "PST", "/w me", "w me", "pm me", "", "")),
        "lvl": r.choice(("{lvl}", "lvl {lvl}", "L{lvl}", "")),
    }


def _pick_fresh(cands, recent: deque, key, rng):
    fresh = [c for c in cands if key(c) not in recent]
    return rng.choice(fresh or cands)


def _name(names, st, rng) -> str:
    if rng.random() < 0.75:
        return names[min(st["abbr"], len(names) - 1)]
    return rng.choice(names)


def _caps(text: str, st, rng) -> str:
    """Upper/lower the ad words but never the [Item Links]."""
    mode = st["caps"]
    out, inside = [], False
    for ch in text:
        if ch == "[":
            inside = True
        elif ch == "]":
            inside = False
        if inside:
            out.append(ch)
        elif mode == "lower":
            out.append(ch.lower())
        else:
            out.append(ch)
    s = "".join(out)
    if mode == "upper":
        for w in ("lfm", "lfg", "wts", "wtb", "pst"):
            s = " ".join(t.upper() if t == w else t for t in s.split(" "))
    return s


def money(copper: int) -> str:
    if copper >= 10000:
        g = copper / 10000
        return f"{g:.0f}g" if g >= 3 else f"{g:.1f}g".replace(".0g", "g")
    if copper >= 100:
        return f"{round(copper / 100)}s"
    return f"{max(1, copper)}c"


def make_lfg(bot_name: str, level: int, class_name: str, faction: str | None, rng=None) -> str | None:
    rng = rng or random
    cands = [d for d in DUNGEONS if d[1] - (2 if d[1] < 60 else 0) <= level <= d[2] + 2 and (d[3] is None or d[3] == faction)]
    if not cands:
        return None
    d = _pick_fresh(cands, _recent_dungeons, lambda d: d[0][0], rng)
    _recent_dungeons.append(d[0][0])
    st = ad_style(bot_name)
    dng = _name(d[0], st, rng)
    my_roles = CLASS_ROLES.get(class_name, ("dps",))
    cls = rng.choice(CLASS_ABBR.get(class_name, ("dps",)))
    missing = [r for r in ("tank", "heals", "dps") if r not in my_roles[:1]]
    need = rng.choice([[missing[0]], missing[:2], ["dps"], [rng.choice(missing)]])
    need_s = " and ".join(rng.choice(NEED_WORDS[n]) for n in dict.fromkeys(need))
    n = rng.randint(1, 4)
    lvl = st["lvl"].format(lvl=level)
    pst = st["pst"]
    role = rng.choice(my_roles)
    templates = [
        f"LFM {dng} need {need_s}", f"lfm {dng} {need_s}", f"{dng} LF{n}M {need_s}",
        f"LF{n}M {dng}", f"need {need_s} for {dng}", f"{dng} need {n} more {pst}",
        f"lf {need_s} {dng} then go", f"LFM {dng} {need_s} {pst}",
        f"{lvl} {cls} lfg {dng}", f"lfg {dng}", f"{cls} LFG {dng} {pst}",
        f"{role} lfg {dng}", f"LFG {dng} can {role}", f"{lvl} {role} looking for {dng}",
    ]
    return _finish(rng.choice(templates), st, rng)


def make_trade(bot_name: str, level: int, class_name: str, faction: str | None, rng=None) -> str | None:
    rng = rng or random
    st = ad_style(bot_name)
    pst = st["pst"] or "pst"
    services = []
    if class_name == "Rogue" and level >= 16:
        services.append(rng.choice(("lockbox opening pst", "can open lockboxes, tips welcome",
                                    "rogue LF lockboxes to open")))
    if class_name == "Mage" and level >= 40 and faction in CITIES:
        services.append(f"portal to {rng.choice(CITIES[faction])} {pst}")
    if level >= 20:
        prof = rng.choice(list(CRAFTS))
        craft = rng.choice(CRAFTS[prof])
        services.append(rng.choice((f"LF {prof} to make [{craft}]", f"{prof} LF work {pst}",
                                    "LF enchanter", "enchanter LF work, ur mats")))
    cands = [it for it in ITEMS if it[1] <= level <= it[2] + 3]
    if not cands:
        return None
    if services and rng.random() < 0.15:
        return _finish(rng.choice(services), st, rng)
    it = _pick_fresh(cands, _recent_items, lambda i: i[0], rng)
    _recent_items.append(it[0])
    name, _, _, base, stacks = it
    unit = int(base * rng.uniform(0.7, 1.3))
    n = rng.choice((5, 10, 20)) if stacks else rng.choice((1, 2, 5, 10))
    ea = money(unit)
    templates = [f"WTB [{name}] {pst}", f"wtb [{name}] x{n}", f"buying [{name}] {pst}",
                 f"WTB [{name}] paying {ea} ea"]
    if stacks:
        templates += [f"WTS [{name}] {money(unit * 20)}/stack", f"wts [{name}] x{n} {ea} ea",
                      f"selling [{name}] stacks {pst}", f"WTS [{name}] x20"]
    else:
        templates += [f"WTS [{name}] {ea}", f"wts [{name}] {ea} ea", f"selling [{name}] {pst}",
                      f"WTS [{name}] x{n} cheap"]
    return _finish(rng.choice(templates), st, rng)


def _finish(text: str, st, rng) -> str:
    text = " ".join(text.split())
    return _caps(text, st, rng)


def make_ad(channel: str, bot_name: str, level: int, class_name: str, faction: str | None,
            rng=None) -> str | None:
    """A template ad for LFG / TRADE, or None when nothing fits (caller falls back)."""
    if channel == "LFG":
        return make_lfg(bot_name, level, class_name, faction, rng)
    if channel == "TRADE":
        return make_trade(bot_name, level, class_name, faction, rng)
    return None
