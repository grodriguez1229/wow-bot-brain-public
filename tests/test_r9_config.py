import importlib

import pytest

_KEYS = ("WBB_OLLAMA_MODEL", "WBB_OLLAMA_CHAT_MODEL", "WBB_FRIENDS", "WBB_FAM_CHAT_CAP",
         "WBB_LOGIN_WHISPER_RATE", "WBB_KIND_WEIGHTS")


@pytest.fixture(autouse=True)
def _restore_config(monkeypatch):
    yield
    monkeypatch.undo()
    import config
    importlib.reload(config)


def _reload(monkeypatch, **env):
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import config
    return importlib.reload(config)


def test_r9_defaults(monkeypatch):
    c = _reload(monkeypatch)
    assert c.OLLAMA_CHAT_MODEL == c.OLLAMA_MODEL
    assert c.FRIENDS_ENABLED is True
    assert (c.FAM_CHAT_POINTS, c.FAM_CHAT_CAP, c.FAM_FRIEND_MIN) == (1.0, 12, 25)
    assert (c.FAM_GROUP_POINTS_PER_10MIN, c.FAM_GROUP_SESSION_CAP) == (1.0, 6)
    assert (c.FAM_RUN_POINTS, c.FAM_CLEAR_BONUS, c.RUN_MIN_S) == (5, 3, 300)
    assert (c.FAM_COPRESENCE_POINTS, c.COPRESENCE_GAP_S, c.COPRESENCE_DAILY_CAP) == (1, 1800, 3)
    assert c.FAM_DECAY_PER_DAY == 1.0
    assert (c.WHISPER_MIN_RUNS, c.LONG_SESSION_S) == (2, 2700)
    assert (c.LOGIN_WHISPER_RATE, c.LOGIN_WHISPER_MAX, c.SECOND_WHISPER_RATE) == (0.5, 2, 0.3)
    assert (c.LOGIN_DELAY_MIN_S, c.LOGIN_DELAY_MAX_S) == (20, 120)
    assert (c.LOGIN_WHISPER_COOLDOWN_S, c.ONLINE_WINDOW_S) == (72000, 300)
    assert c.KIND_WEIGHTS == {"callback": 45, "invite": 25, "checkin": 30}
    assert (c.LONG_ABSENCE_DAYS, c.INVITE_LEVEL_SPREAD) == (7, 5)
    assert (c.RUN_OFFER_MIN_GAP, c.RUN_OFFER_RATE, c.RAID_MIN_LEVEL) == (10, 0.2, 55)
    assert (c.WHISPER_MAX_CHARS, c.CHAT_MAX_CHARS) == (60, 120)
    assert (c.WIPE_WINDOW_S, c.PENDING_EXPIRE_S) == (60, 600)


def test_r9_env_override(monkeypatch):
    c = _reload(monkeypatch, WBB_FAM_CHAT_CAP="10", WBB_LOGIN_WHISPER_RATE="1",
                WBB_KIND_WEIGHTS="0,100,0", WBB_OLLAMA_CHAT_MODEL="qwen3:14b",
                WBB_FRIENDS="0")
    assert c.FAM_CHAT_CAP == 10
    assert c.LOGIN_WHISPER_RATE == 1.0
    assert c.KIND_WEIGHTS == {"callback": 0, "invite": 100, "checkin": 0}
    assert c.OLLAMA_CHAT_MODEL == "qwen3:14b"
    assert c.FRIENDS_ENABLED is False
