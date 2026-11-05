import importlib

_KEYS = ("WBB_REPLY_RATE", "WBB_SILENCE_RATE", "WBB_REPLY_DEPTH_CAP",
         "WBB_EXAMPLES_PER_PROMPT", "WBB_VOICE_TRANSFORM", "WBB_CHAT_LOG_TTL_S")


def _reload(monkeypatch, **env):
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import config
    return importlib.reload(config)


def test_r8_defaults(monkeypatch):
    c = _reload(monkeypatch)
    assert c.REPLY_RATE == 0.5
    assert c.SILENCE_RATE == 0.25
    assert c.REPLY_DEPTH_CAP == 3
    assert c.EXAMPLES_PER_PROMPT == 10
    assert c.VOICE_TRANSFORM is True
    assert c.CHAT_LOG_TTL_S == 420
    assert c.SHAPE_BUDGETS == {"reaction": 25, "question": 50, "fragment": 70,
                               "ad": 60, "ramble": 140}


def test_r8_env_override(monkeypatch):
    c = _reload(monkeypatch, WBB_REPLY_RATE="0", WBB_SILENCE_RATE="0.1",
                WBB_VOICE_TRANSFORM="0", WBB_EXAMPLES_PER_PROMPT="8")
    assert c.REPLY_RATE == 0.0 and c.SILENCE_RATE == 0.1
    assert c.VOICE_TRANSFORM is False and c.EXAMPLES_PER_PROMPT == 8
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)
    importlib.reload(c)
