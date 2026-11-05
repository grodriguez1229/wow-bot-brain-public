# R1 Grounded Chatter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ambient bot chatter (the `/tick` path) reflects each bot's real current activity, target, and finer location instead of generic LFG spam.

**Architecture:** The C++ tick call site derives a coarse activity enum + combat target + sub-area and adds them to the `/tick` payload. The brain's `TickRequest`, `pick_tick_activity`, and `TICK_PROMPT` consume these to shape the topic. All new fields are optional/backward-compatible: absent (old image) or `idle` ⇒ today's behavior exactly.

**Tech Stack:** C++20 (mod-playerbots, boost::beast HTTP, hand-rolled JSON in `LlmBridge.cpp`); Python 3.12 FastAPI + Pydantic (wow-bot-brain, `venv/bin/python -m pytest`). Ollama qwen3.5:9b backend.

## Global Constraints

- **Backward-compatible:** when `activity`/`target`/`subzone` are absent OR `activity == "idle"`, tick behavior is byte-for-byte the current menu behavior. One code path for the legacy case.
- **Activity enum** is lowercase, first-match-wins in this order: `dead`, `in_combat`, `resting`, `traveling`, `idle` (default).
- **Serialize scalars only when non-empty** in the tick JSON (mirror the existing conditional `bot_guild` append); `activity` will always be present (defaults to `idle`).
- **Module-only C++** — no AzerothCore core edits.
- **Unchanged:** reply path, channel routing, cooldowns, LLM semaphore, `note_bot_spoke`.
- Brain changes hot-reload under uvicorn `--reload`; the C++ change (Task 4) requires a worldserver **image rebuild** to take effect.
- Two repos: brain = `~/wow-bot-brain` (branch `evolution-council`); module = `~/azerothcore/azerothcore-wotlk/modules/mod-playerbots` (branch `master`).

---

### Task 1: TickRequest gains grounded-state fields (brain)

**Files:**
- Modify: `models.py` (class `TickRequest`, ~line 22)
- Test: `tests/test_tick_models.py` (create)

**Interfaces:**
- Produces: `TickRequest` with optional `subzone: str|None`, `activity: str|None`, `target: str|None` (all default `None`), consumed by Tasks 2 and 3.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tick_models.py`:

```python
from models import TickRequest


def test_tick_request_accepts_grounded_state_fields():
    req = TickRequest(bot_name="Esterini", location="Elwynn Forest",
                      subzone="Goldshire", activity="in_combat", target="Kobold Vermin")
    assert req.subzone == "Goldshire"
    assert req.activity == "in_combat"
    assert req.target == "Kobold Vermin"


def test_tick_request_grounded_fields_default_none():
    req = TickRequest(bot_name="Esterini")
    assert req.subzone is None and req.activity is None and req.target is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_tick_models.py -q`
Expected: FAIL (`TickRequest` has no `subzone`/`activity`/`target` — Pydantic ignores/rejects unknown kwargs).

- [ ] **Step 3: Add the fields**

In `models.py`, class `TickRequest`, add after `recent_lines`:

```python
class TickRequest(BaseModel):
    bot_name: str
    location: Optional[str] = None
    nearby_players: Optional[list[str]] = None
    nearby_bots: Optional[list[str]] = None
    bot_in_group: Optional[bool] = False
    bot_guild: Optional[str] = None
    recent_lines: Optional[list[RecentLine]] = None
    subzone: Optional[str] = None
    activity: Optional[str] = None
    target: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_tick_models.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_tick_models.py
git commit -m "feat(r1): TickRequest gains optional subzone/activity/target fields"
```

---

### Task 2: State-driven pick_tick_activity (brain)

**Files:**
- Modify: `personality.py` (function `pick_tick_activity`, ~line 176)
- Test: `tests/test_tick_activity.py` (create)

**Interfaces:**
- Consumes: nothing from other tasks (pure function).
- Produces: `pick_tick_activity(level, class_name, location, has_guild, bias_say=False, motivation="", *, activity=None, target=None, subzone=None) -> dict` with keys `channel` and `prompt`. Grounded states (`in_combat`/`traveling`/`resting`/`dead`) short-circuit to a state-shaped dict; `None`/`"idle"` fall through to the existing menu unchanged. Consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tick_activity.py`:

```python
from personality import pick_tick_activity


def _base(**kw):
    return pick_tick_activity(20, "Warrior", "Westfall", True, **kw)


def test_in_combat_names_target_and_uses_say():
    out = _base(activity="in_combat", target="Murloc Oracle", subzone="Murloc Camp")
    assert out["channel"] == "SAY"
    assert "Murloc Oracle" in out["prompt"]
    assert "LFG" not in out["prompt"]


def test_traveling_is_about_the_road():
    out = _base(activity="traveling", subzone="Sentinel Hill")
    assert out["channel"] == "SAY"
    assert "Sentinel Hill" in out["prompt"]


def test_dead_is_a_corpse_run_line():
    out = _base(activity="dead", subzone="The Deadmines")
    assert out["channel"] == "SAY"
    assert "died" in out["prompt"].lower() or "corpse" in out["prompt"].lower()


def test_resting_is_social_general():
    out = _base(activity="resting")
    assert out["channel"] == "GENERAL"


def test_idle_and_none_fall_through_to_menu():
    # No grounded state -> one of the legacy menu channels, never a combat target line.
    for act in (None, "idle"):
        out = _base(activity=act)
        assert out["channel"] in {"LFG", "TRADE", "GENERAL", "SAY", "GUILD"}
        assert "against" not in out["prompt"]  # no combat framing leaked in
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_tick_activity.py -q`
Expected: FAIL (`pick_tick_activity` has no `activity` keyword → `TypeError`).

- [ ] **Step 3: Add the state short-circuit**

In `personality.py`, change the signature of `pick_tick_activity` (~line 176) to add keyword-only params, and insert a grounded-state block at the very top of the body (before `activities = []`):

```python
def pick_tick_activity(level: int, class_name: str, location: str, has_guild: bool,
                       bias_say: bool = False, motivation: str = "",
                       *, activity: str | None = None, target: str | None = None,
                       subzone: str | None = None) -> dict:
    """Returns a tick prompt and suggested channel based on what the bot would naturally do.

    When `activity` names a grounded state (in_combat/traveling/resting/dead) the topic is
    shaped from that real state. When it is None or "idle", falls through to the goal-driven
    menu (legacy behavior)."""

    place = subzone or location or "somewhere"

    if activity == "in_combat":
        tgt = f" against {target}" if target else ""
        return {"channel": "SAY",
                "prompt": (f"You're in a fight{tgt} in {place}. Mutter a short in-character "
                           f"reaction to THIS fight — name the enemy, a close call, low health, "
                           f"the pull. One line. No LFG, no trade.")}
    if activity == "traveling":
        return {"channel": "SAY",
                "prompt": (f"You're traveling through {place}. Say one short line about the road, "
                           f"where you're headed, or the scenery — not looking for a group. One line.")}
    if activity == "dead":
        return {"channel": "SAY",
                "prompt": (f"You just died in {place}. One short in-character reaction — the corpse "
                           f"run, what killed you, frustration. One line.")}
    if activity == "resting":
        return {"channel": "GENERAL",
                "prompt": (f"You're resting at an inn in {place}, taking a break. Say something "
                           f"social and relaxed — banter, a real-life aside, an opinion, guild talk. "
                           f"Not an errand. One short line.")}

    activities = []
```

Leave the entire rest of the function (the `activities.append(...)` menu, the motivation boost, the weighting, and the final `return random.choices(...)`) exactly as-is — it is the `None`/`idle` path.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_tick_activity.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add personality.py tests/test_tick_activity.py
git commit -m "feat(r1): state-driven pick_tick_activity (combat/travel/rest/dead)"
```

---

### Task 3: Thread state into tick() and TICK_PROMPT (brain)

**Files:**
- Modify: `prompts.py` (`TICK_PROMPT`, ~line 35)
- Modify: `main.py` (`tick()` handler, ~line 215)
- Test: `tests/test_tick_state_line.py` (create)

**Interfaces:**
- Consumes: `TickRequest.subzone/activity/target` (Task 1); `pick_tick_activity(..., activity=, target=, subzone=)` (Task 2).
- Produces: `build_tick_state_line(activity, target, place) -> str` in `main.py`, used to fill the new `{state_line}` slot in `TICK_PROMPT`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tick_state_line.py`:

```python
from main import build_tick_state_line


def test_combat_state_line_names_target():
    line = build_tick_state_line("in_combat", "Kobold Vermin", "Goldshire")
    assert "fighting" in line.lower() and "Kobold Vermin" in line and "Goldshire" in line


def test_traveling_state_line():
    assert "traveling" in build_tick_state_line("traveling", None, "Westfall").lower()


def test_idle_and_none_state_line_is_plain_location():
    for act in (None, "idle"):
        line = build_tick_state_line(act, None, "Elwynn Forest")
        assert "Elwynn Forest" in line
        assert "fighting" not in line.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_tick_state_line.py -q`
Expected: FAIL (`cannot import name 'build_tick_state_line' from 'main'`).

- [ ] **Step 3a: Add the `{state_line}` slot to TICK_PROMPT**

In `prompts.py`, insert a `{state_line}` line into `TICK_PROMPT` right after the `IN-GAME GOAL` / `{motivation_line}` block (before `{self_section}`):

```python
YOUR CHARACTER: {name}, level {level} {race} {class_name} ({faction})
IN-GAME GOAL: {current_goal}
{motivation_line}
{state_line}
{self_section}
```

- [ ] **Step 3b: Add the helper and wire tick()**

In `main.py`, add this module-level helper (near the top, after imports):

```python
def build_tick_state_line(activity: str | None, target: str | None, place: str) -> str:
    """One-line 'RIGHT NOW' anchor for the tick system prompt, from the bot's real state."""
    if activity == "in_combat":
        return f"RIGHT NOW: fighting{f' {target}' if target else ''} in {place}."
    if activity == "traveling":
        return f"RIGHT NOW: traveling through {place}."
    if activity == "resting":
        return f"RIGHT NOW: resting at an inn in {place}."
    if activity == "dead":
        return f"RIGHT NOW: dead in {place}, doing a corpse run."
    return f"RIGHT NOW: in {place}."
```

Then in `tick()`, thread the new fields. Replace the two `pick_tick_activity(...)` calls so each passes the grounded state, and build `state_line` for the `.format(...)` call.

Change the activity-selection block:

```python
    if nearby_players:
        activity = pick_tick_activity(p["level"], p["class_name"], location_str, has_guild,
                                      bias_say=True, motivation=p.get("motivation", ""),
                                      activity=req.activity, target=req.target, subzone=req.subzone)
        nearby_str = ", ".join(nearby_players)
        activity["prompt"] += f" Players nearby: {nearby_str}. You might say something to them or about them."
    else:
        activity = pick_tick_activity(p["level"], p["class_name"], location_str, has_guild,
                                      motivation=p.get("motivation", ""),
                                      activity=req.activity, target=req.target, subzone=req.subzone)
```

Add the `state_line` variable just before the `system = TICK_PROMPT.format(` call:

```python
    place = req.subzone or location_str
    state_line = build_tick_state_line(req.activity, req.target, place)
```

And add `state_line=state_line,` to the `TICK_PROMPT.format(...)` keyword arguments.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_tick_state_line.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full brain suite (no regressions)**

Run: `venv/bin/python -m pytest -q`
Expected: PASS — all tests green, output otherwise pristine. If any pre-existing test formats `TICK_PROMPT` without `state_line`, update that test's call to pass `state_line=""`.

- [ ] **Step 6: Commit**

```bash
git add prompts.py main.py tests/test_tick_state_line.py
git commit -m "feat(r1): thread real activity/target/subzone into tick prompt"
```

---

### Task 4: Derive activity/target/subzone and extend the tick payload (C++)

**Files:**
- Modify: `src/Bot/LlmBridge.h` (`PostTick` declaration, ~line 58)
- Modify: `src/Bot/LlmBridge.cpp` (`PostTick` body, ~line 315)
- Modify: `src/Bot/PlayerbotAI.cpp` (tick call site, ~lines 605–641)

**Interfaces:**
- Consumes: brain `/tick` now reads `subzone`/`activity`/`target` (Tasks 1–3). Any brain not yet updated simply ignores unknown JSON keys, so this task is safe to compile/ship independently.
- Produces: `/tick` JSON gains `"subzone"`, `"activity"`, `"target"` (scalars, sent only when non-empty; `activity` always present).

There is no C++ test harness in this repo — this task is verified by the manual live checklist in the spec after the image rebuild. Read each edit back for brace/scope correctness; there is no local compiler (first real compile is the image build).

- [ ] **Step 1: Extend the `PostTick` declaration**

In `src/Bot/LlmBridge.h` (~line 58), change the signature to add three scalars after `location`:

```cpp
    void PostTick(const std::string& botName, const std::string& location,
                  const std::string& subzone, const std::string& activity,
                  const std::string& target,
                  const std::vector<std::string>& nearbyPlayers,
                  const std::vector<std::string>& nearbyBots,
                  const std::string& guild);
```

- [ ] **Step 2: Extend the `PostTick` body**

In `src/Bot/LlmBridge.cpp` (~line 315), update the definition signature to match Step 1, add the three params to the `std::thread([...])` capture list (after `location`), and serialize them conditionally. The JSON-building block becomes:

```cpp
    std::thread([this, botName, location, subzone, activity, target, playersArr, botsArr, guild]()
    {
        std::ostringstream oss;
        oss << "{\"bot_name\":\"" << botName << "\""
            << ",\"location\":\"" << location << "\"";
        if (!subzone.empty())
            oss << ",\"subzone\":\"" << subzone << "\"";
        if (!activity.empty())
            oss << ",\"activity\":\"" << activity << "\"";
        if (!target.empty())
            oss << ",\"target\":\"" << target << "\"";
        oss << ",\"nearby_players\":" << playersArr
            << ",\"nearby_bots\":" << botsArr;
        if (!guild.empty())
            oss << ",\"bot_guild\":\"" << guild << "\"";
        oss << "}";
        std::string json = oss.str();
```

Leave everything below `std::string json = oss.str();` (the `HttpPost`, parse, queue push) unchanged. Target/subzone are wrapped in quotes without escaping — matches the existing convention for `nearby_*` names and `location` in this file.

- [ ] **Step 3: Derive the state at the tick call site**

In `src/Bot/PlayerbotAI.cpp`, in the tick block right after `location` is computed (~line 614, after the closing brace of the zone lookup) and before the "Gather nearby players and bots" comment, insert:

```cpp
            // Finer sub-area (e.g. "Goldshire" inside Elwynn) — parallel to the zone lookup.
            std::string subzone;
            if (bot->GetMap())
            {
                if (AreaTableEntry const* area = sAreaTableStore.LookupEntry(
                        bot->GetMap()->GetAreaId(bot->GetPhaseMask(),
                            bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ())))
                {
                    std::string areaName = area->area_name[sWorld->GetDefaultDbcLocale()];
                    if (areaName != location)   // only send when finer than the zone
                        subzone = areaName;
                }
            }

            // Coarse activity + combat target — cheap accessors, first match wins.
            std::string activity;
            std::string target;
            if (!bot->IsAlive())
                activity = "dead";
            else if (bot->IsInCombat())
            {
                activity = "in_combat";
                if (Unit* victim = bot->GetVictim())
                    target = victim->GetName();
            }
            else if (bot->HasPlayerFlag(PLAYER_FLAGS_RESTING))
                activity = "resting";
            else if (bot->isMoving())
                activity = "traveling";
            else
                activity = "idle";
```

**Verify against the core headers before relying on them** (grep the module + core include tree):
- `Map::GetAreaId(uint32 phaseMask, float x, float y, float z)` — parallel to the existing `GetZoneId`. If the signature differs, match the local `GetZoneId` call already used a few lines above.
- `Player::HasPlayerFlag(PLAYER_FLAGS_RESTING)` — WotLK core API. If unavailable, **delete the `resting` branch** and let that state fall to `traveling`/`idle`; do not block the slice on it.
- `Unit::isMoving()`, `Unit::GetVictim()`, `Player::IsAlive()`, `Unit::GetName()` — standard AC; confirm `isMoving` capitalization against nearby usage.

- [ ] **Step 4: Update the `PostTick` call**

In the same block (~line 641), change the call to pass the new scalars in signature order:

```cpp
            sLlmBridge.PostTick(bot->GetName(), location, subzone, activity, target,
                                nearbyPlayers, nearbyBots, guildName);
```

- [ ] **Step 5: Read the three edits back**

Re-read each hunk (`LlmBridge.h`, `LlmBridge.cpp`, `PlayerbotAI.cpp`) and confirm: signatures match across all three sites, the lambda capture list includes `subzone, activity, target`, and braces balance. Note in the report any accessor you could not verify against headers.

- [ ] **Step 6: Commit**

```bash
git add src/Bot/LlmBridge.h src/Bot/LlmBridge.cpp src/Bot/PlayerbotAI.cpp
git commit -m "feat(r1): derive activity/target/subzone and add to tick payload"
```

---

## Deploy (after all tasks reviewed)

1. Brain (Tasks 1–3) is already live via uvicorn `--reload` — the new fields sit unused until the worldserver sends them.
2. Rebuild + recreate the worldserver for Task 4:
   ```bash
   cd ~/azerothcore/azerothcore-wotlk
   docker compose build ac-worldserver      # slow (CPARALLEL_JOBS=2)
   docker compose up -d ac-worldserver
   ```
3. Manual live checklist (watch `brain.log` for `[tick] … activity=…` lines and in-game chat):
   - A bot in combat mentions its fight / the named mob in SAY.
   - A moving bot mentions the road or destination.
   - A bot at an inn does social/downtime chatter, not LFG.
   - Overall LFG-recruit share of ambient chatter drops noticeably.
   - Sanity: no tick 500s in `brain.log`; bots still chatter on all channels.

## Notes for the executor
- Push after review: brain `git push origin evolution-council`; module `git push personal master`.
- The C++ change is the only one needing the multi-hour rebuild; batch it with other C++ slices (e.g. R5) if you are doing several.
