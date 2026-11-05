"""In-process last-tick state per bot (R9). Lost on restart by design."""
import time

import events
from config import ONLINE_WINDOW_S

_state: dict[str, dict] = {}


def reset_state() -> None:
    _state.clear()


def note_tick(bot: str, *, zone: str | None, subzone: str | None, activity: str | None,
              nearby_players=(), now: float | None = None) -> None:
    t = time.time() if now is None else now
    _state[bot] = {"zone": zone, "subzone": subzone, "activity": activity, "ts": t}
    for player in nearby_players or ():
        events.note_copresence(bot, player, zone, now=t)


def state(bot: str) -> dict | None:
    s = _state.get(bot)
    return dict(s) if s else None


def is_online(bot: str, *, now: float | None = None) -> bool:
    s = _state.get(bot)
    t = time.time() if now is None else now
    return bool(s) and t - s["ts"] <= ONLINE_WINDOW_S


def online_bots(*, now: float | None = None) -> list[str]:
    return sorted(b for b in _state if is_online(b, now=now))
