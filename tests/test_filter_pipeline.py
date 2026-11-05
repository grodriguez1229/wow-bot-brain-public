import asyncio

import election
import main


def setup_function(_):
    election.reset_state()


def _r(msg):
    return {"message": msg, "channel": "SAY", "emote": None, "actions": []}


def _seq(*msgs):
    calls = []

    async def gen(extra):
        calls.append(extra)
        return _r(msgs[min(len(calls) - 1, len(msgs) - 1)])
    return gen, calls


def run(coro):
    return asyncio.run(coro)


def test_output_is_cleaned():
    gen, calls = _seq("gg 😂😂😂 " + "word " * 60)
    out = run(main.generate_deduped(gen, dedupe=True, max_len=140))
    assert "😂" not in out["message"] and len(out["message"]) <= 140
    assert len(calls) == 1


def test_narration_rerolled_once_with_nudge():
    gen, calls = _seq("Pazuwo sighs softly", "this inn is cozy")
    out = run(main.generate_deduped(gen, dedupe=True, bot_name="Pazuwo",
                                    silence_on_narration=True))
    assert out["message"] == "this inn is cozy"
    assert calls == ["", main.NARRATION_NUDGE]


def test_persistent_narration_silences_when_asked():
    gen, calls = _seq("Pazuwo sighs softly", "Pazuwo stretches and yawns")
    out = run(main.generate_deduped(gen, dedupe=True, bot_name="Pazuwo",
                                    silence_on_narration=True))
    assert out is None and len(calls) == 2


def test_persistent_narration_in_whisper_strips_actions():
    gen, calls = _seq("*waves* hi", "*grins* sure thing")
    out = run(main.generate_deduped(gen, dedupe=False, bot_name="Pazuwo"))
    assert out["message"] == "sure thing"


def test_two_call_cap_with_narration_then_duplicate():
    election.note_fleet_line("anyone up for Deadmines?")
    gen, calls = _seq("Pazuwo sighs", "anyone up for Deadmines?", "fresh line")
    out = run(main.generate_deduped(gen, dedupe=True, bot_name="Pazuwo",
                                    silence_on_narration=True))
    assert len(calls) == 2                        # no third call
    assert out["message"] == "anyone up for Deadmines?"   # no allow_silence -> emitted


def test_two_call_cap_duplicate_with_allow_silence_is_silent():
    election.note_fleet_line("anyone up for Deadmines?")
    gen, calls = _seq("Pazuwo sighs", "anyone up for Deadmines?")
    out = run(main.generate_deduped(gen, dedupe=True, allow_silence=True, bot_name="Pazuwo",
                                    silence_on_narration=True))
    assert out is None and len(calls) == 2


def test_recorded_line_is_the_cleaned_one():
    gen, _ = _seq("murlocs everywhere 🔥🔥")
    run(main.generate_deduped(gen, dedupe=True))
    assert election.is_duplicate_line("murlocs everywhere")


def test_fresh_nudge_reroll_is_checked_by_decline():
    election.note_fleet_line("anyone up for Deadmines?")
    gen, calls = _seq("anyone up for Deadmines?", "PASS")
    out = run(main.generate_deduped(gen, dedupe=True, bot_name="Pazuwo",
                                    decline=lambda r: r["message"] == "PASS"))
    assert out is None and len(calls) == 2
