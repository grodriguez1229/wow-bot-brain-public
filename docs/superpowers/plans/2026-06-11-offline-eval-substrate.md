# Offline Eval Substrate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build the offline scene simulator that drives the brain's `/chat` + `/tick` logic bot-to-bot (plus a synthetic player), against an isolated throwaway DB, and records ordered scene-level transcripts the judge can later score.

**Architecture:** Add env-configurable isolation to the existing brain (separate DB path + port → an "experiment" instance that never touches prod). A new `sim/` package orchestrates scenes by calling the experiment brain's HTTP endpoints, feeding each speaker's output as the next speaker's input, and writing JSON transcripts. No change to the running prod brain's default behavior.

**Tech Stack:** Python 3.12, FastAPI (existing brain), httpx (existing), pytest (new dev dep), Ollama (qwen3.5:9b) via the existing brain.

**Safety:** All new code is additive. The running prod brain on `:5000` (pid serving live bots) is never modified or restarted by this plan. The simulator uses its own brain instance on `:5001` with `WBB_DB_PATH=/tmp/wbb-sim.db`.

---

## ✅ STATUS: COMPLETE (2026-06-11)

All 5 tasks done. Tests written in **Gherkin BDD** (pytest-bdd) rather than plain
pytest — the `.feature` files under `tests/features/` are the executable specs.
Full suite: **11 passed**. Live smoke verified: `westfall-lfg` produced 8 turns of
coherent bot↔bot chatter against the `:5001` experiment brain.

| Task | Commit |
|------|--------|
| 1 — env-configurable isolation | `b74c67b` |
| 2 — transcript model | `2afafb4` |
| 3 — brain client + synthetic player | `64037f3` |
| 4 — scene runner (+ Gherkin spec) | `1d0a6d0` |
| 5 — scene catalog + run CLI (+ Gherkin spec) | `2440aef` |

Deviation from plan: tests are BDD/Gherkin (user is learning spec-driven/BDD), and
`requirements.txt` pins `pytest-bdd` in addition to `pytest`. Next subsystem
(judge + optimize loop) gets its own plan and consumes these transcripts.

---

### Task 1: Make brain isolation env-configurable

**Files:**
- Modify: `config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test**
```python
# tests/test_config.py
import importlib, os
def test_db_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("WBB_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("WBB_OLLAMA_MODEL", "testmodel")
    import config; importlib.reload(config)
    assert str(config.DB_PATH).endswith("x.db")
    assert config.OLLAMA_MODEL == "testmodel"
def test_defaults_preserved(monkeypatch):
    monkeypatch.delenv("WBB_DB_PATH", raising=False)
    monkeypatch.delenv("WBB_OLLAMA_MODEL", raising=False)
    import config; importlib.reload(config)
    assert config.OLLAMA_MODEL == "qwen3.5:9b"
    assert str(config.DB_PATH).endswith("memory.db")
```
- [ ] **Step 2: Run → FAIL** (`venv/bin/pytest tests/test_config.py -v`)
- [ ] **Step 3: Implement** — in `config.py`, replace the hardcoded `OLLAMA_MODEL`, `OLLAMA_URL`, `DB_PATH` with env-backed values:
```python
import os
from pathlib import Path
OLLAMA_URL = os.getenv("WBB_OLLAMA_URL", "http://<ollama-host>:11434/api/chat")
OLLAMA_MODEL = os.getenv("WBB_OLLAMA_MODEL", "qwen3.5:9b")
DB_PATH = Path(os.getenv("WBB_DB_PATH", str(Path(__file__).parent / "memory.db")))
```
(Leave MYSQL_CONFIG and the name tables unchanged.)
- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git add config.py tests/test_config.py && git commit -m "feat(config): env-configurable DB path + ollama params for experiment isolation"`

---

### Task 2: Transcript data model

**Files:**
- Create: `sim/__init__.py` (empty), `sim/transcript.py`
- Test: `tests/test_transcript.py`

- [ ] **Step 1: Write failing test**
```python
# tests/test_transcript.py
from sim.transcript import Turn, Scene
def test_roundtrip(tmp_path):
    s = Scene(scene_id="s1", location="Westfall", channel="GENERAL",
              participants=["Brumdar","Sylvara"], turns=[
                  Turn(idx=0, speaker="Brumdar", channel="GENERAL", text="lfg dm anyone?", actions=[]),
                  Turn(idx=1, speaker="Sylvara", channel="GENERAL", text="sure inv", actions=[{"type":"invite","target":"Brumdar"}]),
              ])
    p = tmp_path / "s1.json"; s.save(p)
    s2 = Scene.load(p)
    assert s2.scene_id == "s1" and len(s2.turns) == 2
    assert s2.turns[1].actions[0]["type"] == "invite"
```
- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implement** `sim/transcript.py` with `@dataclass Turn(idx:int, speaker:str, channel:str, text:str, actions:list, ts:str="")` and `@dataclass Scene(scene_id, location, channel, participants:list, turns:list[Turn])` with `save(path)` (json.dump, dataclasses.asdict) and `@classmethod load(path)` (re-hydrate Turns).
- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git commit -m "feat(sim): scene/turn transcript model with json save/load"`

---

### Task 3: Brain client + synthetic player

**Files:**
- Create: `sim/brain_client.py`, `sim/synthetic_player.py`
- Test: `tests/test_synthetic_player.py`

- [ ] **Step 1: Write failing test** (synthetic player is deterministic-seedable; no network)
```python
# tests/test_synthetic_player.py
from sim.synthetic_player import SyntheticPlayer
def test_opener_and_followups_are_short_strings():
    p = SyntheticPlayer(name="Gus", seed=1)
    o = p.opener("Westfall")
    assert isinstance(o, str) and 0 < len(o) <= 120
    f = p.followup(["hey", "sup"])
    assert isinstance(f, str) and len(f) > 0
```
- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implement**
  - `sim/brain_client.py`: `class BrainClient(base_url)` with `chat(bot_name, player_name, message, channel, location)` and `tick(bot_name, location, nearby_players, nearby_bots)` → POST to `{base_url}/chat|/tick` via httpx (timeout 60), returns parsed dict `{message, channel, actions}`.
  - `sim/synthetic_player.py`: `SyntheticPlayer(name, seed)` with `opener(location)` and `followup(history)` returning short canned 2005-WoW-style lines from a seeded `random.Random` pool (e.g. "anyone lfg {dungeon}?", "wts linen pst", "where is the FP here"). Pure, no network.
- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git commit -m "feat(sim): brain http client + seeded synthetic player"`

---

### Task 4: Scene runner (orchestration)

**Files:**
- Create: `sim/scene_runner.py`
- Test: `tests/test_scene_runner.py`

- [ ] **Step 1: Write failing test** with a FAKE brain client (no network) to assert orchestration shape:
```python
# tests/test_scene_runner.py
from sim.scene_runner import run_scene
class FakeBrain:
    def __init__(self): self.calls=[]
    def tick(self, bot, loc, np_, nb): self.calls.append(("tick",bot)); return {"message":f"{bot} ambient","channel":"SAY","actions":[]}
    def chat(self, bot, player, msg, ch, loc): self.calls.append(("chat",bot)); return {"message":f"{bot} replies","channel":ch,"actions":[]}
def test_run_scene_produces_ordered_transcript():
    fb=FakeBrain()
    sc = run_scene(brain=fb, scene_id="t1", location="Westfall", channel="GENERAL",
                   bots=["Brumdar","Sylvara"], player="Gus", turns=4, seed=1)
    assert sc.scene_id=="t1" and len(sc.turns)==4
    assert all(t.text for t in sc.turns)
    assert [t.idx for t in sc.turns]==[0,1,2,3]
```
- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implement** `run_scene(brain, scene_id, location, channel, bots, player, turns, seed)`:
  - seeded `random.Random(seed)`.
  - turn 0: synthetic player opener → recorded as a Turn(speaker=player).
  - subsequent turns: pick a bot (round-robin or random), call `brain.chat(bot, player, last_text, channel, location)`; occasionally (seeded) call `brain.tick(...)` for ambient; record each as a Turn. Feed the most recent non-empty text as the next `message`.
  - skip/replace empty messages (don't record empty turns; retry next speaker) so an empty LLM reply doesn't poison the scene.
  - return a `Scene` with all turns.
- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git commit -m "feat(sim): scene runner orchestration (bot<->bot + synthetic player)"`

---

### Task 5: CLI + live smoke run

**Files:**
- Create: `sim/run.py`, `sim/scenes.py`
- Modify: `requirements.txt` (add `pytest`)

- [ ] **Step 1:** Add `pytest` to `requirements.txt`; `venv/bin/pip install pytest`.
- [ ] **Step 2:** `sim/scenes.py` — a list of ~5 `SceneSpec` dicts (location, channel, bots, player, turns) spanning LFG/Trade/General/social contexts.
- [ ] **Step 3:** `sim/run.py` — argparse CLI: `--base-url` (default `http://localhost:5001`), `--out sim/transcripts/`, `--seed`. For each scene spec: `run_scene(...)`, `scene.save(out/<id>.json)`. Print a summary line per scene.
- [ ] **Step 4: Live smoke (integration).** Start an isolated experiment brain, run one scene, verify a transcript with non-empty turns:
```bash
WBB_DB_PATH=/tmp/wbb-sim.db venv/bin/uvicorn main:app --host 127.0.0.1 --port 5001 &
sleep 3
venv/bin/python -m sim.run --base-url http://localhost:5001 --out /tmp/sim-out --seed 1
python -c "import json,glob; t=json.load(open(glob.glob('/tmp/sim-out/*.json')[0])); assert any(x['text'] for x in t['turns']); print('turns:', len(t['turns']))"
kill %1
```
Expected: a transcript file with multiple non-empty turns from real qwen3.5:9b output.
- [ ] **Step 5: Commit** — `git commit -m "feat(sim): CLI runner + scene specs + offline eval substrate complete"`

---

## Notes for the executor
- Run all pytest via `venv/bin/pytest`.
- Never restart or modify the prod brain on `:5000`; the experiment brain is `:5001` with `WBB_DB_PATH=/tmp/wbb-sim.db`.
- Commit after every task (local repo `~/wow-bot-brain`, fine to commit).
- This substrate is consumed by the next subsystem (judge + optimize loop), which gets its own plan.
