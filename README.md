# wow-bot-brain

An LLM sidecar that gives World of Warcraft playerbots personalities, memory and organic chat,
so a private server feels like a populated 2005 realm. The goal is bots that read as real
people at a keyboard, not NPCs: short lines, typos, in-jokes, and friendships that form from
playing together.

It runs as a small FastAPI service. A game-server plugin (not included here) posts chat and
game events to it over HTTP, and it answers with what a bot should say and do. Generation uses
a local model through [Ollama](https://ollama.com).

## What's in here

| Area | Files |
|---|---|
| Endpoints and generation pipeline | `main.py` (`/tick`, `/heard`, `/chat`, `/event`, `/reflect*`) |
| Prompts and voice | `prompts.py`, `voice.py`, `voice_examples.py`, `typing_transform.py`, `ad_templates.py` |
| Personas | `personality.py`, `irl_identity.py` (game character + a real-life player behind it) |
| Who replies to overheard chat | `election.py`, `chat_log.py` |
| Memory and relationships | `db.py` (SQLite), `consolidate.py`, `council.py`, `self_memory.py` |
| Friendships and login whispers | `history.py`, `friendship.py`, `events.py`, `login_whisper.py`, `presence.py` |
| Guardrails | `knowledge.py` (level-appropriate zones), `vanilla_guard.py`, `postfilter.py` |
| Evaluation | `eval/` (metrics, A/B and model bake-off tools), `sim/` (offline scene simulator, LLM judge) |
| Design history | `docs/superpowers/` (specs, plans and before/after results per slice) |

## Running it

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python -m pytest -q          # tests are hermetic: no Ollama, MySQL or network
./start.sh                            # serves on :5000
```

Configuration is environment variables (see `config.py`), for example:

| Variable | Default |
|---|---|
| `WBB_OLLAMA_URL` | `http://localhost:11434/api/chat` |
| `WBB_OLLAMA_MODEL` | `qwen3.5:9b` |
| `WBB_MYSQL_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_DATABASE` | `localhost` / `3306` / `acore` / empty / `acore_characters` |
| `WBB_DB_PATH` | `./memory.db` |

The MySQL connection reads character race, class, level and guild from an AzerothCore
`acore_characters` database. Without it, personas fall back to defaults.

## Notes

- Bot chat is intentionally uncensored; profanity is part of the realism.
- Lore guardrails target vanilla (patch 1.12): level cap 60, no expansion content.
