from sim.optimize.experiment_brain import uvicorn_cmd


def test_uvicorn_cmd_uses_fresh_db_and_port():
    cmd = uvicorn_cmd(port=5001, db_path="/tmp/wbb-exp.db")
    assert cmd[:3] == ["venv/bin/uvicorn", "main:app", "--host"]
    assert "5001" in cmd
    # db path is passed via env, not argv:
    assert "/tmp/wbb-exp.db" not in cmd
