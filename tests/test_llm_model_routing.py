import importlib


def test_default_lane_uses_base_model(monkeypatch):
    monkeypatch.setenv("WBB_OLLAMA_MODEL", "base-model")
    monkeypatch.delenv("WBB_OLLAMA_HEARD_MODEL", raising=False)
    import config, llm
    importlib.reload(config); importlib.reload(llm)
    assert llm.pick_model(None, "default") == "base-model"
    # heard defaults to the base model when its own env is unset (backward-compatible)
    assert llm.pick_model(None, "heard") == "base-model"


def test_heard_lane_uses_heard_model_when_set(monkeypatch):
    monkeypatch.setenv("WBB_OLLAMA_MODEL", "base-model")
    monkeypatch.setenv("WBB_OLLAMA_HEARD_MODEL", "big-model")
    import config, llm
    importlib.reload(config); importlib.reload(llm)
    assert llm.pick_model(None, "heard") == "big-model"
    assert llm.pick_model(None, "default") == "base-model"


def test_explicit_model_arg_always_wins(monkeypatch):
    # the A/B harness passes model= explicitly; that must override lane routing
    import llm
    assert llm.pick_model("ab-candidate", "heard") == "ab-candidate"
    assert llm.pick_model("ab-candidate", "default") == "ab-candidate"


def test_chat_lane_uses_chat_model(monkeypatch):
    import llm
    monkeypatch.setattr(llm, "OLLAMA_CHAT_MODEL", "big")
    assert llm.pick_model(None, "chat") == "big"
    assert llm.pick_model(None, "default") == llm.OLLAMA_MODEL
    assert llm.pick_model("x", "chat") == "x"
