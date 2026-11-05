"""Game-event ingestion (R9): /event payloads -> shared history + familiarity points."""
import threading
import time

import friendship
import history
import knowledge
from config import (COPRESENCE_DAILY_CAP, COPRESENCE_GAP_S, FAM_CLEAR_BONUS,
                    FAM_COPRESENCE_POINTS, FAM_GROUP_POINTS_PER_10MIN, FAM_GROUP_SESSION_CAP,
                    FAM_RUN_POINTS, RUN_MIN_S, RUN_REENTRY_S, WIPE_WINDOW_S)

DAY_S = 86400
_deaths: dict[str, dict[str, float]] = {}  # player -> {who: ts}
_lock = threading.Lock()  # /event runs in a threadpool; check-then-insert must be atomic


def reset_state() -> None:
    _deaths.clear()


def _date(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now))


def _canon(instance: str | None) -> str | None:
    return (knowledge.canonical_place(instance) or instance) if instance else None


def _places(instance: str | None) -> list[str]:
    return [instance] if instance else []


# --- closing sessions -----------------------------------------------------

def _close(player: str, row: dict, at: float) -> None:
    """Close one open session at `at` and award points. `row` must be fresh and open."""
    at = max(at, row["started_at"])
    bot = row["bot_name"]
    if row["kind"] == "group":
        minutes = (at - row["started_at"]) / 60
        points = min(FAM_GROUP_SESSION_CAP, minutes / 10 * FAM_GROUP_POINTS_PER_10MIN)
        history.close_session(row["id"], ended_at=at)
    else:
        outcome = row["outcome"]
        if at - row["started_at"] < RUN_MIN_S and not row["bosses"]:
            history.close_session(row["id"], ended_at=at, outcome="bounce")
            return
        points = FAM_RUN_POINTS + (FAM_CLEAR_BONUS if outcome == "cleared" else 0)
        history.close_session(row["id"], ended_at=at, outcome=outcome or "partial")
        if outcome != "cleared" and row["instance"]:
            history.add_moment(player, bot, f"ran {row['instance']} together, {_date(at)}",
                               source="run", source_id=row["id"],
                               places=_places(row["instance"]), now=at)
    if points > 0:
        friendship.add_play(bot, player, points, now=at)


def _close_all(player: str, at: float, kind: str | None = None, bots=None) -> None:
    for row in history.open_sessions(player, kind):
        if bots is None or row["bot_name"] in bots:
            _close(player, row, at)


def _open_run(player: str, bot: str, instance: str | None, zone, now: float) -> None:
    history.open_session(player, bot, "run", instance=instance, zone=zone, now=now)


def _open_run_for(player: str, bot: str) -> dict | None:
    for r in history.open_sessions(player, "run"):
        if r["bot_name"] == bot:
            return r
    return None


def _sync_roster(player: str, group: list[str], zone, now: float,
                 instance: str | None = None) -> None:
    open_group = {r["bot_name"] for r in history.open_sessions(player, "group")}
    roster = set(group)
    gone = open_group - roster
    if gone:
        _close_all(player, now, bots=gone)  # group and run sessions of departed bots
    runs = history.open_sessions(player, "run")
    run_instance = runs[0]["instance"] if runs else instance
    for bot in group:
        if bot not in open_group:
            history.open_session(player, bot, "group", zone=zone, now=now)
            if run_instance and not _open_run_for(player, bot):
                if not _reopen_recent(player, bot, run_instance, now):
                    _open_run(player, bot, run_instance, zone, now)


# --- handlers -------------------------------------------------------------

def _on_group(ev, group, now):
    _sync_roster(ev["player"], group, ev.get("zone"), now, _canon(ev.get("instance")))


def _reopen_recent(player: str, bot: str, instance: str, now: float) -> bool:
    """Re-entering the same instance soon after leaving continues that run (paid once)."""
    prev = history.recent_closed_run(player, bot, instance, since=now - RUN_REENTRY_S)
    if not prev:
        return False
    paid = 0 if prev["outcome"] == "bounce" else FAM_RUN_POINTS + (
        FAM_CLEAR_BONUS if prev["outcome"] == "cleared" else 0)
    if paid:
        friendship.add_play(bot, player, -paid, now=now)
    history.delete_moments("run", prev["id"], text_prefix="ran ")
    history.reopen_session(prev["id"])
    return True


def _on_map(ev, group, now):
    player = ev["player"]
    instance = _canon(ev.get("instance"))
    for row in history.open_sessions(player, "run"):
        if instance and group and row["instance"] == instance and row["bot_name"] in group:
            continue  # re-sent map for the run already open: no-op
        _close(player, row, now)
    if not (instance and group):
        return
    for bot in group:
        if _open_run_for(player, bot):
            continue
        if not _reopen_recent(player, bot, instance, now):
            _open_run(player, bot, instance, ev.get("zone"), now)


def _on_boss_kill(ev, group, now):
    player, boss = ev["player"], ev.get("boss") or ""
    for bot in group:
        run = _open_run_for(player, bot)
        instance = (run["instance"] if run else None) or _canon(ev.get("instance"))
        history.add_event(player, bot, "boss_kill", instance=instance, zone=ev.get("zone"),
                          detail=boss, session_id=run["id"] if run else None, now=now)
        if not run:
            continue
        cleared = bool(boss) and boss == knowledge.FINAL_BOSSES.get(instance or "")
        history.bump_session(run["id"], bosses=1, outcome="cleared" if cleared else None)
        if cleared and run["outcome"] != "cleared":
            history.add_moment(player, bot, f"killed {boss} in {instance} together, {_date(now)}",
                               source="run", source_id=run["id"], places=_places(instance), now=now)


def _on_died(ev, group, now):
    player, who = ev["player"], ev.get("who")
    if not who or not group:
        return
    window = _deaths.setdefault(player, {})
    window[who] = now
    for k in [k for k, ts in window.items() if now - ts > WIPE_WINDOW_S]:
        del window[k]
    if not ({player, *group} <= set(window)):
        return
    window.clear()
    boss = ev.get("boss")
    for bot in group:
        run = _open_run_for(player, bot)
        instance = (run["instance"] if run else None) or _canon(ev.get("instance"))
        history.add_event(player, bot, "wipe", instance=instance, zone=ev.get("zone"),
                          detail=boss or "", session_id=run["id"] if run else None, now=now)
        if run:
            history.bump_session(run["id"], wipes=1)
        where = f"on {boss} in {instance}" if boss and instance else (
            f"on {boss}" if boss else f"in {instance}" if instance else "")
        text = f"wiped {where} together, {_date(now)}" if where else f"wiped together, {_date(now)}"
        history.add_moment(player, bot, text, source="wipe", source_id=run["id"] if run else 0,
                           places=_places(instance), now=now)


def _on_level_up(ev, group, now):
    player, level = ev["player"], ev.get("level")
    if not level:
        return
    for bot in group:
        history.add_event(player, bot, "level_up", zone=ev.get("zone"), detail=str(level), now=now)
        history.add_moment(player, bot, f"dinged {level} while grouped with you, {_date(now)}",
                           source="level_up", source_id=0, places=[], now=now)


def ingest(ev: dict, *, now: float | None = None) -> None:
    with _lock:
        _ingest(ev, now)


def _ingest(ev: dict, now: float | None) -> None:
    kind = ev.get("type")
    handlers = {"group": _on_group, "map": _on_map, "boss_kill": _on_boss_kill,
                "died": _on_died, "level_up": _on_level_up}
    if kind not in handlers and kind not in ("login", "logout"):
        return  # unknown types and ping write nothing
    player = ev["player"]
    now = time.time() if now is None else now
    group = list(ev.get("group") or [])
    prior = history.player_seen(player)
    seen = dict(level=ev.get("level"), faction=ev.get("faction"), zone=ev.get("zone"), now=now)
    if kind == "login":
        # a crash/missed logout must not mint a multi-day session: close at last activity
        _close_all(player, prior["last_seen"] if prior else now)
        history.note_player_seen(player, login=True, **seen)
        _sync_roster(player, group, ev.get("zone"), now, _canon(ev.get("instance")))
        return
    history.note_player_seen(player, logout=(kind == "logout"), **seen)
    if kind == "logout":
        _close_all(player, now)
        _deaths.pop(player, None)
        return
    handlers[kind](ev, group, now)


def note_copresence(bot: str, player: str, zone: str | None, *, now: float | None = None) -> bool:
    with _lock:
        return _note_copresence(bot, player, zone, now)


def _note_copresence(bot, player, zone, now) -> bool:
    now = time.time() if now is None else now
    last = history.last_event(player, bot, "same_zone")
    if last and now - last["ts"] < COPRESENCE_GAP_S:
        return False
    if history.count_events(player, bot, "same_zone", since=now - DAY_S) >= COPRESENCE_DAILY_CAP:
        return False
    history.add_event(player, bot, "same_zone", zone=zone, now=now)
    friendship.add_play(bot, player, FAM_COPRESENCE_POINTS, now=now)
    return True
