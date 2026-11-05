import importlib
import os


def test_db_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("WBB_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("WBB_OLLAMA_MODEL", "testmodel")
    import config
    importlib.reload(config)
    assert str(config.DB_PATH).endswith("x.db")
    assert config.OLLAMA_MODEL == "testmodel"


def test_defaults_preserved(monkeypatch):
    monkeypatch.delenv("WBB_DB_PATH", raising=False)
    monkeypatch.delenv("WBB_OLLAMA_MODEL", raising=False)
    import config
    importlib.reload(config)
    assert config.OLLAMA_MODEL == "qwen3.5:9b"
    assert str(config.DB_PATH).endswith("memory.db")
