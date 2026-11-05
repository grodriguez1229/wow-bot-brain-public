# Bot Motivation + Capability Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each bot a motivation (gold-maker / dungeon-seeker / guild-recruiter / helper-social / world-explorer / farmer) that gates which actions it offers and biases its ambient chatter, with guild-invites permitted only to bots that hold guild-invite rank.

**Architecture:** Pure capability function maps motivation + hard permissions → a set of capability tokens. The brain assigns a motivation at bot creation (game-state-weighted), then uses the capability set + motivation at three touchpoints: chat action-offering (`build_action_rules`), ambient tick weighting (`pick_tick_activity`), and a prompt flavor line. Entirely brain-side; rides the already-deployed `invite`/`guildinvite` C++ executors.

**Tech Stack:** Python 3.12, FastAPI, SQLite (`db.py`), pymysql (`gamedb.py`), pytest. Run tests with `venv/bin/pytest` from repo root. The live brain runs on `:5000` (`WBB_GUILD_ACTIONS=1` enables guild actions). MySQL game DB is `acore_characters` on the `ac-database` container.

---

## File Structure
- `capabilities.py` — NEW. `MOTIVATIONS` list + pure `capabilities(motivation, *, can_guild_invite)`.
- `gamedb.py` — MODIFY. Add `lookup_guild_invite_right(bot_name) -> bool`.
- `db.py` — MODIFY. Add `motivation` column + migration + `set_motivation()`.
- `personality.py` — MODIFY. Add `pick_motivation()`; store motivation in `get_or_create_personality` (+ lazy backfill); add `motivation` param to `pick_tick_activity`.
- `prompts.py` — MODIFY. `build_action_rules(player_name, *, caps)`; add `build_motivation_line(motivation)`; add `{motivation_line}` to CHAT_PROMPT + TICK_PROMPT.
- `main.py` — MODIFY. Compute caps from motivation + guild-invite-right + `WBB_GUILD_ACTIONS`; pass to `build_action_rules`, `pick_tick_activity`, and prompt formatting.
- Tests: `tests/test_capabilities.py`, `tests/test_gamedb_guild_right.py`, `tests/test_db_motivation.py`, `tests/test_pick_motivation.py`, `tests/test_motivation_flavor.py`; update `tests/test_action_rules.py`.

---

### Task 1: Capability function

**Files:** Create `capabilities.py`; Test `tests/test_capabilities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_capabilities.py
from capabilities import MOTIVATIONS, capabilities


def test_motivations_list():
    assert MOTIVATIONS == ["gold_maker", "dungeon_seeker", "guild_recruiter",
                           "helper_social", "world_explorer", "farmer"]


def test_party_invite_always_present():
    for m in MOTIVATIONS:
        assert "party_invite" in capabilities(m, can_guild_invite=False)


def test_motivation_base_caps():
    assert "sell_goods" in capabilities("gold_maker", can_guild_invite=False)
    assert "party_recruit" in capabilities("dungeon_seeker", can_guild_invite=False)
    assert "help" in capabilities("helper_social", can_guild_invite=False)
    assert "explore" in capabilities("world_explorer", can_guild_invite=False)
    assert "farm" in capabilities("farmer", can_guild_invite=False)


def test_guild_invite_requires_rank():
    # The headline permission rule.
    assert "guild_invite" not in capabilities("guild_recruiter", can_guild_invite=False)
    assert "guild_invite" in capabilities("guild_recruiter", can_guild_invite=True)
    # Non-recruiter never gets guild_invite even with rank.
    assert "guild_invite" not in capabilities("gold_maker", can_guild_invite=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_capabilities.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capabilities'`.

- [ ] **Step 3: Write minimal implementation**

```python
# capabilities.py
"""Pure mapping from a bot's motivation (+ hard permissions) to capability tokens.

A capability token gates a behavior the brain may offer/encourage. Hard permissions
overlay the motivation: guild_invite is granted ONLY when the bot actually holds
guild-invite rank (mirrors the engine's GR_RIGHT_INVITE), regardless of motivation.
"""
from __future__ import annotations

MOTIVATIONS = ["gold_maker", "dungeon_seeker", "guild_recruiter",
               "helper_social", "world_explorer", "farmer"]

_BASE: dict[str, set[str]] = {
    "gold_maker": {"sell_goods"},
    "dungeon_seeker": {"party_recruit"},
    "guild_recruiter": set(),      # guild_invite added only with rank
    "helper_social": {"help"},
    "world_explorer": {"explore"},
    "farmer": {"farm"},
}


def capabilities(motivation: str, *, can_guild_invite: bool = False) -> set[str]:
    caps = set(_BASE.get(motivation, set()))
    caps.add("party_invite")  # every bot can invite you to a party if you ask
    if motivation == "guild_recruiter" and can_guild_invite:
        caps.add("guild_invite")
    return caps
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_capabilities.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add capabilities.py tests/test_capabilities.py
git commit -m "feat(capabilities): motivation -> capability tokens with guild-rank gate"
```

---

### Task 2: Guild-invite-right lookup (game DB)

**Files:** Modify `gamedb.py`; Test `tests/test_gamedb_guild_right.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gamedb_guild_right.py
import gamedb


class _Cur:
    def __init__(self, row): self._row = row
    def execute(self, *a, **k): pass
    def fetchone(self): return self._row
    def __enter__(self): return self
    def __exit__(self, *a): pass


class _Conn:
    def __init__(self, row): self._row = row
    def cursor(self): return _Cur(self._row)
    def close(self): pass


def test_has_invite_right_when_bit_set(monkeypatch):
    # rights 0x04 = GR_RIGHT_INVITE set
    monkeypatch.setattr(gamedb.pymysql, "connect", lambda **k: _Conn((4,)))
    assert gamedb.lookup_guild_invite_right("Officerbot") is True


def test_no_invite_right_when_bit_clear(monkeypatch):
    monkeypatch.setattr(gamedb.pymysql, "connect", lambda **k: _Conn((1,)))
    assert gamedb.lookup_guild_invite_right("Memberbot") is False


def test_no_right_when_not_guilded(monkeypatch):
    monkeypatch.setattr(gamedb.pymysql, "connect", lambda **k: _Conn(None))
    assert gamedb.lookup_guild_invite_right("Solobot") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_gamedb_guild_right.py -v`
Expected: FAIL — `AttributeError: module 'gamedb' has no attribute 'lookup_guild_invite_right'`.

- [ ] **Step 3: Write minimal implementation**

Append to `gamedb.py`:

```python
_GR_RIGHT_INVITE = 0x04  # AzerothCore guild_rank.rights bit for inviting members


def lookup_guild_invite_right(bot_name: str) -> bool:
    """True if the bot is in a guild and its rank has the invite right."""
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT gr.rights FROM characters c
                JOIN guild_member gm ON c.guid = gm.guid
                JOIN guild_rank gr ON gr.guildid = gm.guildid AND gr.rid = gm.rank
                WHERE c.name = %s LIMIT 1
            """, (bot_name,))
            row = cur.fetchone()
        conn.close()
        return bool(row and (int(row[0]) & _GR_RIGHT_INVITE))
    except Exception:
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_gamedb_guild_right.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add gamedb.py tests/test_gamedb_guild_right.py
git commit -m "feat(gamedb): lookup_guild_invite_right via guild_rank GR_RIGHT_INVITE bit"
```

---

### Task 3: `motivation` column + DB helper

**Files:** Modify `db.py`; Test `tests/test_db_motivation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_motivation.py
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_bot_personalities_has_motivation_column(fresh_db):
    conn = fresh_db.get_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bot_personalities)").fetchall()]
    conn.close()
    assert "motivation" in cols


def test_set_motivation_roundtrip(fresh_db):
    conn = fresh_db.get_db()
    conn.execute("""INSERT INTO bot_personalities
        (bot_name, race, class_name, level, gender, faction, identity_id, who, typing_style, current_goal)
        VALUES ('Geysse','Dwarf','Rogue',16,'male','Alliance','class_clown','x','y','z')""")
    conn.commit(); conn.close()
    fresh_db.set_motivation("Geysse", "gold_maker")
    conn = fresh_db.get_db()
    row = conn.execute("SELECT motivation FROM bot_personalities WHERE bot_name='Geysse'").fetchone()
    conn.close()
    assert row["motivation"] == "gold_maker"


def test_init_db_idempotent(fresh_db):
    fresh_db.init_db()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_db_motivation.py -v`
Expected: FAIL — no `motivation` column / no `set_motivation`.

- [ ] **Step 3: Write minimal implementation**

In `db.py` `init_db()`, add the column to the `bot_personalities` CREATE TABLE (after `guild_name TEXT DEFAULT ''`):

```python
            motivation TEXT DEFAULT '',
```

And add an idempotent migration next to the existing `guild_name`/`in_group` ALTER blocks:

```python
    try:
        conn.execute("ALTER TABLE bot_personalities ADD COLUMN motivation TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
```

Add at the end of `db.py`:

```python
def set_motivation(bot_name: str, motivation: str):
    conn = get_db()
    conn.execute("UPDATE bot_personalities SET motivation = ? WHERE bot_name = ?",
                 (motivation, bot_name))
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_db_motivation.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db_motivation.py
git commit -m "feat(db): motivation column on bot_personalities + set_motivation"
```

---

### Task 4: `pick_motivation` (game-state-weighted)

**Files:** Modify `personality.py`; Test `tests/test_pick_motivation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pick_motivation.py
import random
from personality import pick_motivation
from capabilities import MOTIVATIONS


def test_always_returns_valid_motivation():
    random.seed(1)
    for _ in range(50):
        assert pick_motivation("Mage", 30, has_guild=False, can_guild_invite=False) in MOTIVATIONS


def test_non_guilded_never_recruiter():
    random.seed(2)
    for _ in range(200):
        m = pick_motivation("Warrior", 40, has_guild=False, can_guild_invite=False)
        assert m != "guild_recruiter"


def test_rank_holder_can_be_recruiter():
    random.seed(3)
    got = {pick_motivation("Warrior", 40, has_guild=True, can_guild_invite=True)
           for _ in range(200)}
    assert "guild_recruiter" in got


def test_lowbie_skews_explore_farm():
    random.seed(4)
    low = [pick_motivation("Mage", 8, has_guild=False, can_guild_invite=False) for _ in range(300)]
    frac = sum(m in ("world_explorer", "farmer") for m in low) / len(low)
    assert frac > 0.4  # weighted up for low levels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_pick_motivation.py -v`
Expected: FAIL — `ImportError: cannot import name 'pick_motivation'`.

- [ ] **Step 3: Write minimal implementation**

In `personality.py`, add the import at top (with the other imports):

```python
from capabilities import MOTIVATIONS
```

Add the function (near `pick_mood`):

```python
_GROUP_CLASSES = {"Warrior", "Paladin", "Priest", "Druid", "Shaman"}


def pick_motivation(class_name: str, level: int, has_guild: bool = False,
                    can_guild_invite: bool = False) -> str:
    """Game-state-weighted motivation pick. guild_recruiter only when the bot holds
    guild-invite rank (else weight 0). Uses the module `random` (seed in tests)."""
    w = {m: 1 for m in MOTIVATIONS}          # baseline variety
    w["gold_maker"] += 1
    w["helper_social"] += 1
    if class_name in _GROUP_CLASSES:
        w["dungeon_seeker"] += 3
    if level <= 15:
        w["world_explorer"] += 2
        w["farmer"] += 2
    if can_guild_invite:
        w["guild_recruiter"] += 4
    else:
        w["guild_recruiter"] = 0             # can't recruit without rank
    return random.choices(list(w), weights=list(w.values()), k=1)[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_pick_motivation.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add personality.py tests/test_pick_motivation.py
git commit -m "feat(personality): pick_motivation, game-state-weighted with rank gate"
```

---

### Task 5: Assign + persist motivation in `get_or_create_personality`

**Files:** Modify `personality.py`; Test `tests/test_pick_motivation.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pick_motivation.py`:

```python
import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    return db


def test_new_personality_gets_motivation(fresh_db, monkeypatch):
    import personality
    personality._personality_cache.clear()
    monkeypatch.setattr(personality, "lookup_bot_from_game_db",
                        lambda n: {"race": "Dwarf", "class_name": "Warrior", "level": 20,
                                   "gender": "male", "faction": "Alliance"})
    monkeypatch.setattr(personality, "lookup_bot_guild", lambda n: "")
    monkeypatch.setattr(personality, "lookup_guild_invite_right", lambda n: False)
    p = personality.get_or_create_personality("Newbot")
    from capabilities import MOTIVATIONS
    assert p["motivation"] in MOTIVATIONS
    # persisted
    row = fresh_db.get_db().execute(
        "SELECT motivation FROM bot_personalities WHERE bot_name='Newbot'").fetchone()
    assert row["motivation"] in MOTIVATIONS


def test_existing_row_without_motivation_is_backfilled(fresh_db, monkeypatch):
    import personality
    personality._personality_cache.clear()
    conn = fresh_db.get_db()
    conn.execute("""INSERT INTO bot_personalities
        (bot_name, race, class_name, level, gender, faction, identity_id, who, typing_style, current_goal, motivation)
        VALUES ('Oldbot','Dwarf','Rogue',16,'male','Alliance','class_clown','x','y','z','')""")
    conn.commit(); conn.close()
    monkeypatch.setattr(personality, "lookup_guild_invite_right", lambda n: False)
    p = personality.get_or_create_personality("Oldbot")
    from capabilities import MOTIVATIONS
    assert p["motivation"] in MOTIVATIONS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_pick_motivation.py -k "motivation and (new or backfill)" -v`
Expected: FAIL — `KeyError: 'motivation'` / not assigned.

- [ ] **Step 3: Write minimal implementation**

In `personality.py`:

Add to the imports from gamedb:

```python
from gamedb import lookup_bot_from_game_db, lookup_bot_guild, lookup_guild_invite_right
```

In `get_or_create_personality`, in the **existing-row branch** (where `if row:`), backfill if missing:

```python
    if row:
        data = dict(row)
        if not data.get("motivation"):
            can_inv = lookup_guild_invite_right(bot_name)
            data["motivation"] = pick_motivation(
                data["class_name"], data["level"],
                has_guild=bool(data.get("guild_name")), can_guild_invite=can_inv)
            set_motivation(bot_name, data["motivation"])
        _personality_cache[bot_name] = data
        return data
```

(Add `from db import get_db, set_motivation` — extend the existing `from db import ...` line to include `set_motivation`.)

In the **new-personality branch**, after `guild = lookup_bot_guild(bot_name)`:

```python
    can_inv = lookup_guild_invite_right(bot_name)
    motivation = pick_motivation(game_info["class_name"], game_info["level"],
                                 has_guild=bool(guild), can_guild_invite=can_inv)
```

Add `"motivation": motivation,` to the `data` dict, and add `motivation` to the INSERT column list + values:

```python
    conn.execute("""
        INSERT OR IGNORE INTO bot_personalities
        (bot_name, race, class_name, level, gender, faction, identity_id, who, typing_style, current_goal, guild_name, in_group, motivation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        bot_name, data["race"], data["class_name"], data["level"],
        data["gender"], data["faction"], data["identity_id"],
        data["who"], data["typing_style"], data["current_goal"],
        data["guild_name"], data["in_group"], data["motivation"],
    ))
```


- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_pick_motivation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add personality.py tests/test_pick_motivation.py
git commit -m "feat(personality): assign+persist+backfill motivation at creation"
```

---

### Task 6: `build_action_rules(caps)` + motivation flavor line

**Files:** Modify `prompts.py`; Update `tests/test_action_rules.py`; Test `tests/test_motivation_flavor.py`

- [ ] **Step 1: Update the failing tests**

Replace the body of `tests/test_action_rules.py` with the new `caps`-based API:

```python
# tests/test_action_rules.py
from prompts import build_action_rules


def test_invite_tag_targets_the_player():
    out = build_action_rules("Abril", caps={"party_invite"})
    assert "[ACTION:invite Abril]" in out
    assert "[ACTION:emote" in out


def test_handles_missing_name():
    assert "[ACTION:invite them]" in build_action_rules("", caps={"party_invite"})


def test_guildinvite_present_only_with_capability():
    assert "guildinvite" not in build_action_rules("Gus", caps={"party_invite"})
    out = build_action_rules("Gus", caps={"party_invite", "guild_invite"})
    assert "[ACTION:guildinvite Gus]" in out


def test_does_not_leak_tag_instruction_as_speech():
    assert "Never say the tag out loud" in build_action_rules("Gus", caps={"party_invite"})
```

Create `tests/test_motivation_flavor.py`:

```python
from prompts import build_motivation_line, CHAT_PROMPT, TICK_PROMPT


def test_flavor_line_per_motivation():
    assert "gold" in build_motivation_line("gold_maker").lower()
    assert build_motivation_line("dungeon_seeker")
    assert build_motivation_line("") == ""


def test_prompts_have_motivation_placeholder():
    assert "{motivation_line}" in CHAT_PROMPT
    assert "{motivation_line}" in TICK_PROMPT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_action_rules.py tests/test_motivation_flavor.py -v`
Expected: FAIL — `build_action_rules()` got unexpected keyword `caps` / no `build_motivation_line` / no placeholder.

- [ ] **Step 3: Write minimal implementation**

In `prompts.py`, replace the whole `build_action_rules` function with the caps-based version:

```python
def build_action_rules(player_name: str, *, caps: set[str] | None = None) -> str:
    """Action rules gated by the bot's capability set. party_invite + emote are always
    offered; guildinvite only when 'guild_invite' in caps (rank + WBB_GUILD_ACTIONS,
    decided by the caller)."""
    caps = caps or set()
    p = player_name or "them"
    rules = f"""
- You can DO things, not just talk. To act, put a tag on its OWN line at the very end, after your message:
  [ACTION:invite {p}] — send {p} a REAL party invite.
  [ACTION:emote wave] — emote (wave, laugh, cheer, dance, bow, salute, flex)."""
    if "guild_invite" in caps:
        rules += f"""
  [ACTION:guildinvite {p}] — invite {p} to YOUR guild (you're an officer who can)."""
    rules += f"""
- IMPORTANT: if you agree to group up in ANY way — "yeah", "sure", "ok", "come over", "lets go", "hop on" — you MUST end your message with [ACTION:invite {p}]. Saying yes WITHOUT the tag does nothing in the game and is the #1 mistake — don't make it."""
    if "guild_invite" in caps:
        rules += f"""
- If {p} asks to join your guild and you agree, you MUST end with [ACTION:guildinvite {p}]."""
    rules += f"""
- Only invite {p} (the person you're talking to), by that exact name. Never say the tag out loud — just act and say something natural like "yeah lets do it, sending inv".
- If you're NOT grouping, don't add the tag. One invite is enough — don't repeat it."""
    return rules


_MOTIVATION_LINES = {
    "gold_maker": "You're focused on making gold — you notice deals and mention what you're buying or selling.",
    "dungeon_seeker": "You're itching to run a dungeon — you look for groups and suggest instances.",
    "guild_recruiter": "You're proud of your guild and like bringing in new members.",
    "helper_social": "You're friendly and like helping newer players and just chatting.",
    "world_explorer": "You love exploring and taking in the world; you comment on places you see.",
    "farmer": "You're grinding a good spot for gold and xp; you think about drop rates and efficiency.",
}


def build_motivation_line(motivation: str) -> str:
    return _MOTIVATION_LINES.get(motivation, "")
```

Add `{motivation_line}` to both prompts. In `CHAT_PROMPT`, put it right after `IN-GAME GOAL: {current_goal}`:

```
IN-GAME GOAL: {current_goal}
{motivation_line}
```

In `TICK_PROMPT`, same — right after `IN-GAME GOAL: {current_goal}` (before the existing blank line + `{nearby_section}`).

Also update the two existing full-format tests in `tests/test_memory_prompt.py`
(`test_chat_prompt_formats_with_nearby_section` and `test_tick_prompt_formats_with_nearby_section`)
to pass the new placeholder — add `motivation_line=""` to BOTH `.format(...)` calls so they
still succeed with the new `{motivation_line}` field.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_action_rules.py tests/test_motivation_flavor.py tests/test_memory_prompt.py -v`
Expected: PASS (incl. the updated memory-prompt format tests).

- [ ] **Step 5: Commit**

```bash
git add prompts.py tests/test_action_rules.py tests/test_motivation_flavor.py tests/test_memory_prompt.py
git commit -m "feat(prompts): caps-based action rules + motivation flavor line"
```

---

### Task 7: Motivation-biased tick activity

**Files:** Modify `personality.py`; Test `tests/test_motivation_flavor.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_motivation_flavor.py`:

```python
import random
from personality import pick_tick_activity


def _channel_dist(motivation, n=300):
    random.seed(7)
    counts = {}
    for _ in range(n):
        a = pick_tick_activity(20, "Mage", "Elwynn Forest", has_guild=True, motivation=motivation)
        counts[a["channel"]] = counts.get(a["channel"], 0) + 1
    return counts


def test_gold_maker_favors_trade():
    d = _channel_dist("gold_maker")
    assert d.get("TRADE", 0) > d.get("SAY", 0)


def test_dungeon_seeker_favors_lfg():
    d = _channel_dist("dungeon_seeker")
    assert d.get("LFG", 0) >= max(d.values()) * 0.5  # LFG is prominent


def test_explorer_favors_say():
    d = _channel_dist("world_explorer")
    assert d.get("SAY", 0) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_motivation_flavor.py -k tick -v`
Expected: FAIL — `pick_tick_activity()` got unexpected keyword `motivation`.

- [ ] **Step 3: Write minimal implementation**

In `personality.py`, change `pick_tick_activity` signature to accept `motivation`:

```python
def pick_tick_activity(level: int, class_name: str, location: str, has_guild: bool,
                       bias_say: bool = False, motivation: str = "") -> dict:
```

Replace the weight-building loop at the end with motivation-aware weights:

```python
    # Per-motivation channel boosts (added on top of the baseline weights).
    boost = {
        "gold_maker": {"TRADE": 6},
        "dungeon_seeker": {"LFG": 6},
        "guild_recruiter": {"GUILD": 6},
        "helper_social": {"GENERAL": 5},
        "world_explorer": {"SAY": 6},
        "farmer": {"SAY": 6},
    }.get(motivation, {})

    weights = []
    for a in activities:
        ch = a["channel"]
        if bias_say and ch == "SAY":
            w = 5
        elif ch == "LFG":
            w = 3
        elif ch in ("TRADE", "GENERAL", "GUILD"):
            w = 2
        else:
            w = 1
        weights.append(w + boost.get(ch, 0))

    return random.choices(activities, weights=weights, k=1)[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_motivation_flavor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add personality.py tests/test_motivation_flavor.py
git commit -m "feat(personality): pick_tick_activity biased by motivation"
```

---

### Task 8: Wire it through `main.py`

**Files:** Modify `main.py`

- [ ] **Step 1: Wire `/chat`**

In `main.py`, add the import:

```python
from capabilities import capabilities
from gamedb import lookup_guild_invite_right
```

In `chat()`, replace the `action_rules = build_action_rules(...)` block with caps computation:

```python
    can_inv = lookup_guild_invite_right(req.bot_name)
    caps = capabilities(p.get("motivation", ""), can_guild_invite=can_inv)
    if os.getenv("WBB_GUILD_ACTIONS") != "1":
        caps.discard("guild_invite")
    action_rules = build_action_rules(req.player_name, caps=caps)
```

Add `motivation_line` to the `CHAT_PROMPT.format(...)` call:

```python
        current_goal=p["current_goal"],
        motivation_line=build_motivation_line(p.get("motivation", "")),
```

(Import `build_motivation_line` from prompts — extend the existing prompts import.)

- [ ] **Step 2: Wire `/tick`**

In `tick()`, pass motivation to `pick_tick_activity` (both call sites — the `nearby_players` branch and the else):

```python
        activity = pick_tick_activity(p["level"], p["class_name"], location_str, has_guild,
                                      bias_say=True, motivation=p.get("motivation", ""))
```
and
```python
        activity = pick_tick_activity(p["level"], p["class_name"], location_str, has_guild,
                                      motivation=p.get("motivation", ""))
```

Add `motivation_line` to the `TICK_PROMPT.format(...)` call:

```python
        current_goal=p["current_goal"],
        motivation_line=build_motivation_line(p.get("motivation", "")),
```

- [ ] **Step 3: Smoke-test import + prompt formatting**

Run: `venv/bin/python -c "import main; print('ok')"`
Expected: `ok` (no KeyError on the new `{motivation_line}` placeholder).

- [ ] **Step 4: Full suite**

Run: `venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat(brain): wire motivation -> caps (chat actions), tick weighting, prompt flavor"
```

---

### Task 9: Live verification + done check

**Files:** none (verification)

- [ ] **Step 1: Full suite**

Run: `venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 2: Restart the live brain (keep guild actions on)**

```bash
cd ~/wow-bot-brain
OLD=$(ss -ltnp 2>/dev/null | grep -oP ':5000.*pid=\K[0-9]+' | head -1); [ -n "$OLD" ] && kill "$OLD"; sleep 1
WBB_GUILD_ACTIONS=1 setsid nohup venv/bin/uvicorn main:app --host 0.0.0.0 --port 5000 >/tmp/wbb-prod.log 2>&1 &
sleep 5; curl -s -m6 http://127.0.0.1:5000/health
```
Expected: `{"status":"ok",...}`.

- [ ] **Step 3: Verify motivations assigned + behavior**

Check a few bots got motivations and that a non-officer is NOT offered guildinvite while an officer is:
```bash
cd ~/wow-bot-brain
venv/bin/python -c "
from personality import get_or_create_personality as g
for n in ['Astianon','Beaglivu','Caramian','Unvasu','Gaemwa']:
    p=g(n); print(n, p.get('motivation'), 'guild=', p.get('guild_name') or '-')
"
```
Expected: each prints a motivation from the list.

- [ ] **Step 4: Confirm Definition-of-Done vs spec**

- motivation stored + assigned/backfilled (Tasks 3–5).
- `capabilities()` gates guild_invite by rank (Task 1) + WBB_GUILD_ACTIONS (Task 8).
- chat offers guildinvite only to guild_recruiter+rank (Tasks 6,8).
- tick biased by motivation (Task 7,8); prompt flavor injected (Tasks 6,8).
- full suite green.

- [ ] **Step 5: Commit any final notes**

```bash
git add -A && git commit -m "chore(motivation): layer complete — full suite green" || echo "nothing to commit"
```

---

## Notes for the implementer
- Run tests with `venv/bin/pytest` from repo root.
- The game DB (`gamedb.py`) is never hit in tests — monkeypatch `pymysql.connect`.
- SQLite tests isolate via `monkeypatch.setattr(db, "DB_PATH", ...)` + `db.init_db()`.
- This is brain-only — NO worldserver rebuild. The deployed `invite`/`guildinvite` C++
  executors run the actions; this layer only decides which bots offer them.
- Private/local repo — commit locally, never push to a remote.
