# Bot Motivation + Capability Layer — Design (2026-06-15)

North star: a server that feels alive. Right now every bot offers the same actions and
chatters the same way. This adds a **motivation** to each bot that decides which behaviors
it exhibits and which actions it's *allowed* to take — gold-makers bark WTS, dungeon-seekers
recruit, only guild officers send guild invites, etc. Entirely **brain-side, no worldserver
rebuild** (it rides the `guildinvite`/`invite` C++ executors already deployed). Local/private.

## Motivations (one primary per bot)
`gold_maker`, `dungeon_seeker`, `guild_recruiter`, `helper_social`, `world_explorer`,
`farmer`. The IRL identity (persona, e.g. highschool_kid) stays; motivation is the in-game
*drive*, orthogonal to persona.

| motivation | flavor / behaviors |
|---|---|
| gold_maker | TRADE WTS/WTB barking, profession services, gold/AH talk, haggling |
| dungeon_seeker | LFG posts, proactively recruits to parties, eager to group, dungeon/gear talk |
| guild_recruiter | invites + talks up the guild — **only if it holds guild-invite rank** (else just talks) |
| helper_social | answers questions, helps lowbies, friendly banter, offers buffs |
| world_explorer | wanders, admires scenery/zones, comments on the world, low transactional |
| farmer | grinds a spot, talks drops/efficiency/xp-per-hour, mostly solo |

## Architecture (brain-side)

### 1. Storage + assignment
- New `motivation TEXT` column on `bot_personalities` (alongside `identity_id`),
  populated at `get_or_create_personality` time, cached in `_personality_cache`.
- `pick_motivation(class_name, level, has_guild, guild_rank) -> str`: **game-state-weighted,
  seeded-deterministic** choice:
  - tank/healer-capable classes (Warrior/Paladin/Priest/Druid/Shaman) weight `dungeon_seeker` up;
  - guilded bots with invite rank weight `guild_recruiter` up;
  - low level (<=15) weights `world_explorer` + `farmer` up;
  - `gold_maker`/`helper_social` get a baseline weight for all;
  - remaining spread keeps variety. Uses `random` (same module the rest of personality uses).

### 2. Capability function (the "permissions list")
`sim`-free pure module `capabilities.py`:
```python
def capabilities(motivation: str, *, can_guild_invite: bool) -> set[str]:
    """Return the set of enabled capabilities for a bot. Hard permissions overlay the
    motivation: 'guild_invite' is granted ONLY when the bot actually holds guild-invite
    rank, regardless of motivation."""
```
- Capability tokens: `party_invite` (all — reactive grouping on request), `party_recruit`
  (dungeon_seeker — proactive), `guild_invite` (guild_recruiter AND can_guild_invite),
  `sell_goods` (gold_maker), `help` (helper_social), `explore` (world_explorer),
  `farm` (farmer).
- `can_guild_invite` comes from a new game-DB lookup (below). The engine remains the final
  hard gate (`GR_RIGHT_INVITE`); the brain mirrors it so it never offers an invite the
  game would refuse (avoids "said yes, nothing happened").

### 3. Game-DB: guild-invite rank lookup (`gamedb.py`)
`lookup_guild_invite_right(bot_name) -> bool`: join `characters`→`guild_member`→`guild_rank`
and test `rights & 0x04` (GR_RIGHT_INVITE). Returns False if not guilded / no right.
(Cached with the personality; refreshed on fresh DB like other identity data.)

### 4. Enforcement — three brain touchpoints
- **`build_action_rules(player_name, *, caps)`** (chat): supersedes the current
  `guilded`/`guild_enabled` params. Offer `[ACTION:guildinvite]` only when `'guild_invite'
  in caps` AND the global `WBB_GUILD_ACTIONS` safety flag is on (keep that flag — it gates
  whether the deployed C++ executor is trusted); party invite stays offered to all
  (reactive). Proactive recruiting language only when `party_recruit`/`guild_invite` in caps.
  `caps` is computed once in `main.py` from motivation + guild-invite-right and passed in.
- **`pick_tick_activity(..., motivation)`** (ambient): bias channel + prompt by motivation —
  gold_maker→TRADE, dungeon_seeker→LFG, guild_recruiter→GUILD recruit, helper→GENERAL help,
  explorer→SAY scenery, farmer→SAY grind. Keep a small baseline so bots aren't one-note.
- **CHAT/TICK prompt**: inject one motivation-flavor line (e.g. "You're mainly here to make
  gold — you notice deals and mention what you're selling.").

### 5. Data flow
creation → `pick_motivation(...)` + `lookup_guild_invite_right(...)` → store motivation →
per chat/tick → load motivation + recompute caps → shapes offered actions, tick weights,
and prompt flavor.

## Testing (BDD + unit)
- `capabilities()` table: each motivation → expected caps; `guild_recruiter` WITH vs WITHOUT
  `can_guild_invite` (the headline permission test).
- `pick_motivation()` seeded determinism + game-state weighting (tank/healer skews
  dungeon_seeker; lowbie skews explorer/farmer).
- `build_action_rules` gates `guildinvite` on caps; party invite always present.
- `pick_tick_activity` channel distribution shifts with motivation (statistical/seeded).

## Scope / YAGNI
- One primary motivation per bot (no multi/secondary yet).
- Motivation does NOT rewrite `current_goal` this round (possible later: bias goal text).
- No C++ / no rebuild. Reuses deployed `invite`/`guildinvite` executors.
- Fresh `memory.db` (already in effect) so motivations populate on next bot contact; existing
  cached personalities get a motivation lazily on next `get_or_create_personality` (add a
  light migration: if row lacks motivation, assign + persist).
