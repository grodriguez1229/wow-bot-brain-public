import os
from pathlib import Path

OLLAMA_URL = os.getenv("WBB_OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("WBB_OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_HEARD_MODEL = os.getenv("WBB_OLLAMA_HEARD_MODEL", OLLAMA_MODEL)

# ── LLM sampling (anti-repetition; env-overridable for tuning + A/B) ─────────
LLM_TEMPERATURE = float(os.getenv("WBB_LLM_TEMPERATURE", "0.9"))
LLM_TOP_P = float(os.getenv("WBB_LLM_TOP_P", "0.9"))
LLM_MIN_P = float(os.getenv("WBB_LLM_MIN_P", "0.05"))
LLM_REPEAT_PENALTY = float(os.getenv("WBB_LLM_REPEAT_PENALTY", "1.2"))
LLM_REPEAT_LAST_N = int(os.getenv("WBB_LLM_REPEAT_LAST_N", "256"))

DB_PATH = Path(os.getenv("WBB_DB_PATH", str(Path(__file__).parent / "memory.db")))
MEMORY_WINDOW = 10

MYSQL_CONFIG = {
    "host": os.getenv("WBB_MYSQL_HOST", "localhost"),
    "port": int(os.getenv("WBB_MYSQL_PORT", "3306")),
    "user": os.getenv("WBB_MYSQL_USER", "acore"),
    "password": os.getenv("WBB_MYSQL_PASSWORD", ""),
    "database": os.getenv("WBB_MYSQL_DATABASE", "acore_characters"),
}

RACE_NAMES = {
    1: "Human", 2: "Orc", 3: "Dwarf", 4: "Night Elf", 5: "Undead",
    6: "Tauren", 7: "Gnome", 8: "Troll", 10: "Blood Elf", 11: "Draenei",
}
CLASS_NAMES = {
    1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest",
    7: "Shaman", 8: "Mage", 9: "Warlock", 11: "Druid",
}
GENDER_NAMES = {0: "male", 1: "female"}
FACTION_FOR_RACE = {
    1: "Alliance", 3: "Alliance", 4: "Alliance", 7: "Alliance", 11: "Alliance",
    2: "Horde", 5: "Horde", 6: "Horde", 8: "Horde", 10: "Horde",
}

ROLE_FOR_CLASS = {
    "Warrior": "tank/melee dps",
    "Paladin": "healer/tank",
    "Hunter": "ranged dps",
    "Rogue": "melee dps",
    "Priest": "healer",
    "Shaman": "healer/caster dps",
    "Mage": "caster dps",
    "Warlock": "caster dps",
    "Druid": "healer/tank/dps (jack of all trades)",
}

# ── /heard election (slice 1: heard-chat election) ──────────────────────────
HEARD_ENGAGED_WINDOW_S = 120     # bot spoke in this channel this recently => engaged
HEARD_CONVO_WINDOW_S = 600      # bot<->speaker messages this recent => engaged
HEARD_ENGAGED_CHANCE = 0.6
HEARD_CANDIDATE_CHANCE = 0.15
HEARD_MAX_RESPONDERS = 2        # named bots exempt
HEARD_COOLDOWN_S = 30           # per bot per channel
HEARD_MAX_HEARERS = 30
HEARD_MAX_NAMED = 3     # ceiling on guaranteed named responders per message
LLM_MAX_CONCURRENCY = 2
LLM_HEARD_CONCURRENCY = 1  # dedicated lane so /heard replies never queue behind tick backlog

# ── fleet-wide anti-repetition (ambient chatter dedup) ──────────────────────
FLEET_DEDUP_WINDOW_S = int(os.getenv("WBB_FLEET_DEDUP_WINDOW_S", "180"))
FLEET_DEDUP_MAXLEN = int(os.getenv("WBB_FLEET_DEDUP_MAXLEN", "200"))
FLEET_DEDUP_THRESHOLD = float(os.getenv("WBB_FLEET_DEDUP_THRESHOLD", "0.6"))

# ── IRL-bleed budget + output post-filter (R3) ──────────────────────────────
IRL_TARGET = float(os.getenv("WBB_IRL_TARGET", "0.15"))        # fleet share of ambient lines
IRL_WINDOW = int(os.getenv("WBB_IRL_WINDOW", "200"))           # rolling window, in lines
SIGNATURE_RATE = float(os.getenv("WBB_SIGNATURE_RATE", "0.1"))  # chance a line offers the bot's phrase
TICK_MAX_CHARS = int(os.getenv("WBB_TICK_MAX_CHARS", "140"))
HEARD_MAX_CHARS = int(os.getenv("WBB_HEARD_MAX_CHARS", "200"))

# ── organic voice (R8) ──────────────────────────────────────────────────────
REPLY_RATE = float(os.getenv("WBB_REPLY_RATE", "0.5"))          # tick replies to a recent line when one exists
SILENCE_RATE = float(os.getenv("WBB_SILENCE_RATE", "0.25"))     # ticks skipped before any LLM call
REPLY_DEPTH_CAP = int(os.getenv("WBB_REPLY_DEPTH_CAP", "3"))    # max replies chained off one line
EXAMPLES_PER_PROMPT = int(os.getenv("WBB_EXAMPLES_PER_PROMPT", "10"))
VOICE_TRANSFORM = os.getenv("WBB_VOICE_TRANSFORM", "1") == "1"  # per-bot typing habits
CHAT_LOG_TTL_S = int(os.getenv("WBB_CHAT_LOG_TTL_S", "420"))    # how long a line stays reply-able
CHAT_LOG_MAXLEN = int(os.getenv("WBB_CHAT_LOG_MAXLEN", "400"))
# Optional extra style examples from a local, gitignored real-chat transcript (jsonl with
# channel/text/era). Empty = off. Only vanilla/unknown-era, guard-clean lines are used.
VOICE_CORPUS_PATH = os.getenv("WBB_VOICE_CORPUS_PATH", "")
# Per-shape char budget (post-filter max_len). "ad" is template-built, no LLM.
SHAPE_BUDGETS = {"reaction": 25, "question": 50, "fragment": 70, "ad": 60, "ramble": TICK_MAX_CHARS}

# ── friends who remember you (R9) ───────────────────────────────────────────
OLLAMA_CHAT_MODEL = os.getenv("WBB_OLLAMA_CHAT_MODEL", OLLAMA_MODEL)
FRIENDS_ENABLED = os.getenv("WBB_FRIENDS", "1") == "1"
FAM_CHAT_POINTS = float(os.getenv("WBB_FAM_CHAT_POINTS", "1.0"))
FAM_CHAT_CAP = int(os.getenv("WBB_FAM_CHAT_CAP", "12"))
FAM_FRIEND_MIN = int(os.getenv("WBB_FAM_FRIEND_MIN", "25"))
FAM_GROUP_POINTS_PER_10MIN = float(os.getenv("WBB_FAM_GROUP_POINTS_PER_10MIN", "1.0"))
FAM_GROUP_SESSION_CAP = int(os.getenv("WBB_FAM_GROUP_SESSION_CAP", "6"))
FAM_RUN_POINTS = int(os.getenv("WBB_FAM_RUN_POINTS", "5"))
FAM_CLEAR_BONUS = int(os.getenv("WBB_FAM_CLEAR_BONUS", "3"))
RUN_MIN_S = int(os.getenv("WBB_RUN_MIN_S", "300"))
FAM_COPRESENCE_POINTS = int(os.getenv("WBB_FAM_COPRESENCE_POINTS", "1"))
COPRESENCE_GAP_S = int(os.getenv("WBB_COPRESENCE_GAP_S", "1800"))
COPRESENCE_DAILY_CAP = int(os.getenv("WBB_COPRESENCE_DAILY_CAP", "3"))
FAM_DECAY_PER_DAY = float(os.getenv("WBB_FAM_DECAY_PER_DAY", "1.0"))
WHISPER_MIN_RUNS = int(os.getenv("WBB_WHISPER_MIN_RUNS", "2"))
LONG_SESSION_S = int(os.getenv("WBB_LONG_SESSION_S", "2700"))
LOGIN_WHISPER_RATE = float(os.getenv("WBB_LOGIN_WHISPER_RATE", "0.5"))
LOGIN_WHISPER_MAX = int(os.getenv("WBB_LOGIN_WHISPER_MAX", "2"))
SECOND_WHISPER_RATE = float(os.getenv("WBB_SECOND_WHISPER_RATE", "0.3"))
LOGIN_GEN_BUDGET_S = float(os.getenv("WBB_LOGIN_GEN_BUDGET_S", "45"))
LOGIN_DELAY_MIN_S = int(os.getenv("WBB_LOGIN_DELAY_MIN_S", "20"))
LOGIN_DELAY_MAX_S = int(os.getenv("WBB_LOGIN_DELAY_MAX_S", "120"))
LOGIN_WHISPER_COOLDOWN_S = int(os.getenv("WBB_LOGIN_WHISPER_COOLDOWN_S", "72000"))
ONLINE_WINDOW_S = int(os.getenv("WBB_ONLINE_WINDOW_S", "300"))
_kw = [int(x) for x in os.getenv("WBB_KIND_WEIGHTS", "45,25,30").split(",")]
KIND_WEIGHTS = dict(zip(("callback", "invite", "checkin"), _kw))
LONG_ABSENCE_DAYS = int(os.getenv("WBB_LONG_ABSENCE_DAYS", "7"))
INVITE_LEVEL_SPREAD = int(os.getenv("WBB_INVITE_LEVEL_SPREAD", "5"))
RUN_OFFER_MIN_GAP = int(os.getenv("WBB_RUN_OFFER_MIN_GAP", "10"))
RUN_OFFER_RATE = float(os.getenv("WBB_RUN_OFFER_RATE", "0.2"))
RAID_MIN_LEVEL = int(os.getenv("WBB_RAID_MIN_LEVEL", "55"))
WHISPER_MAX_CHARS = int(os.getenv("WBB_WHISPER_MAX_CHARS", "60"))
CHAT_MAX_CHARS = int(os.getenv("WBB_CHAT_MAX_CHARS", "120"))
WIPE_WINDOW_S = int(os.getenv("WBB_WIPE_WINDOW_S", "60"))
PENDING_EXPIRE_S = int(os.getenv("WBB_PENDING_EXPIRE_S", "600"))
RUN_REENTRY_S = int(os.getenv("WBB_RUN_REENTRY_S", "600"))
