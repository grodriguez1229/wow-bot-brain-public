import asyncio

import election
import main


def setup_function():
    election.reset_state()


def _run(coro):
    return asyncio.run(coro)


def test_dedupe_rerolls_once_on_duplicate_then_emits_fresh():
    # Seed the fleet window with a line the first generation will collide with.
    election.note_fleet_line("anyone up for Deadmines?")
    calls = []

    async def gen(extra):
        calls.append(extra)
        # first call returns the duplicate; the re-roll (extra != "") returns something fresh
        msg = "this fight is brutal, low hp" if extra else "anyone up for Deadmines?"
        return {"message": msg, "channel": "SAY", "emote": None, "actions": []}

    result = _run(main.generate_deduped(gen, dedupe=True))
    assert result["message"] == "this fight is brutal, low hp"
    assert len(calls) == 2                      # re-rolled exactly once
    assert calls[1] == main.FRESH_NUDGE          # re-roll carried the nudge
    assert election.is_duplicate_line("this fight is brutal, low hp", now=2.0)  # recorded


def test_no_reroll_when_line_is_novel():
    calls = []

    async def gen(extra):
        calls.append(extra)
        return {"message": "the road to Westfall is long", "channel": "SAY",
                "emote": None, "actions": []}

    result = _run(main.generate_deduped(gen, dedupe=True))
    assert result["message"] == "the road to Westfall is long"
    assert len(calls) == 1                        # no duplicate -> no re-roll


def test_dedupe_false_never_rerolls_or_records():
    election.note_fleet_line("anyone up for Deadmines?")
    calls = []

    async def gen(extra):
        calls.append(extra)
        return {"message": "anyone up for Deadmines?", "channel": "SAY",
                "emote": None, "actions": []}

    result = _run(main.generate_deduped(gen, dedupe=False))
    assert result["message"] == "anyone up for Deadmines?"
    assert len(calls) == 1                        # dedupe off (e.g. direct /chat)
    # not recorded into the fleet window
    election.reset_state()
    assert not election.is_duplicate_line("anyone up for Deadmines?", now=2.0)


def test_decline_short_circuits_to_none():
    async def gen(extra):
        return {"message": "PASS", "channel": "SAY", "emote": None, "actions": []}

    result = _run(main.generate_deduped(
        gen, dedupe=True, decline=lambda r: r["message"] == "PASS"))
    assert result is None


def test_persistent_duplicate_with_allow_silence_returns_none():
    election.note_fleet_line("anyone up for Deadmines?")

    async def gen(extra):
        return {"message": "anyone up for Deadmines?", "channel": "SAY",
                "emote": None, "actions": []}   # always the duplicate

    result = _run(main.generate_deduped(gen, dedupe=True, allow_silence=True))
    assert result is None
