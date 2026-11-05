"""Scene orchestration: drive bots turn-by-turn (reacting to each other and a
synthetic player) and record an ordered transcript.

This is the piece the live game forbids (bots never hear each other's words) —
here we feed each speaker's output as the next speaker's input, in our own
controllable, reproducible turn order.
"""
from __future__ import annotations

import random

from sim.synthetic_player import SyntheticPlayer
from sim.transcript import Scene, Turn


def run_scene(brain, scene_id, location, channel, bots, player="Gus",
              turns=8, seed=0, tick_prob=0.25, player_followup_prob=0.2,
              nearby_window=4, consolidate=False):
    r = random.Random(seed)
    sp = SyntheticPlayer(name=player, seed=seed) if player else None
    participants = list(bots) + ([player] if player else [])
    recorded: list[Turn] = []
    last_text = ""

    # Turn 0: the synthetic player opens the scene when present. With no player,
    # the first bot speaks unprompted (a tick) — how ambient chatter starts in-game.
    if player:
        last_text = sp.opener(location)
        recorded.append(Turn(idx=0, speaker=player, channel=channel, text=last_text, actions=[]))

    i = 0
    guard = 0
    while len(recorded) < turns and guard < turns * 4:
        guard += 1

        # Occasionally the human chimes in again instead of a bot.
        if player and r.random() < player_followup_prob:
            text = sp.followup([t.text for t in recorded[-4:]])
            if text:
                recorded.append(Turn(idx=len(recorded), speaker=player,
                                     channel=channel, text=text, actions=[]))
            continue

        bot = bots[i % len(bots)]
        i += 1
        nearby_bots = [b for b in bots if b != bot]

        recent_lines = [{"speaker": t.speaker, "text": t.text} for t in recorded[-nearby_window:]]

        # Nothing said yet (no-player scene) -> the bot must initiate via tick.
        # Also always tick when there is no player (chat requires a non-null player_name).
        force_tick = not recorded and not last_text
        if force_tick or not player or r.random() < tick_prob:
            resp = brain.tick(bot, location, [player] if player else [], nearby_bots,
                              recent_lines=recent_lines)
        else:
            resp = brain.chat(bot, player, last_text, channel, location,
                              recent_lines=recent_lines)

        msg = (resp.get("message") or "").strip()
        if not msg:
            continue  # never record empty LLM output; let the next speaker try

        ch = resp.get("channel") or channel
        recorded.append(Turn(idx=len(recorded), speaker=bot, channel=ch,
                             text=msg, actions=resp.get("actions", [])))
        last_text = msg

    scene = Scene(scene_id=scene_id, location=location, channel=channel,
                  participants=participants, turns=recorded)
    if consolidate:
        from consolidate import consolidate_scene
        consolidate_scene(scene, bots=list(bots))
    return scene
