"""Live A/B: qwen3.5:9b vs mistral-small:22b on the NEW persona prompts.

Builds the exact CHAT system prompt main.py builds, then sends identical inputs to
both models so the only variable is the model. Reports output + latency.

Run: venv/bin/python eval/persona_ab.py
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from config import OLLAMA_URL
from personality import IRL_IDENTITIES, get_or_create_personality, pick_mood
from db import get_relationship, get_memory, get_memory_sheet, describe_relationship
from prompts import CHAT_PROMPT, CHAT_LIFE_RULE_OPEN, build_action_rules, build_motivation_line
from capabilities import capabilities
from memory_prompt import build_nearby_section, build_relationship_section, build_self_section
from llm import truncate_sentences

MODELS = ["qwen3.5:9b", "mistral-small:22b"]
PLAYER = "Gus"

# (bot, message, why) — vivid Alliance personas to expose persona-surfacing
SCENARIOS = [
    ("Hadriano", "rough day?", "retail_worker — should surface real-life venting"),
    ("Metheri", "hey tell me about yourself", "college_kid — the old failure case"),
    ("Beaglivu", "hey whats up", "newbie — casual small talk"),
    ("Lelindea", "man this game is so grindy lol", "nurse — opinion/topic range"),
    ("Gaemwa", "anyone selling wool cloth?", "gold_maker — errand still works"),
]


def build_system(bot_name: str, channel: str = "whisper", location: str = "Stormwind") -> str:
    p = get_or_create_personality(bot_name)
    rel = get_relationship(bot_name, PLAYER)
    history = get_memory(bot_name, PLAYER)
    identity = next((i for i in IRL_IDENTITIES if i["id"] == p["identity_id"]), None)
    mood = pick_mood(identity) if identity else "chill"

    context_lines = [f"TALKING TO: {PLAYER} ({describe_relationship(rel)})"]
    if channel:
        context_lines.append(f"CHANNEL: {channel}")
    if location:
        context_lines.append(f"LOCATION: {location}")
    if p.get("guild_name"):
        context_lines.append(f"YOUR GUILD: {p['guild_name']}")
    context_section = "\n".join(context_lines)

    if history:
        mem_lines = [f"{'Them' if m['role']=='user' else 'You'}: {m['content']}" for m in history[-6:]]
        memory_section = "Recent chat with them:\n" + "\n".join(mem_lines)
    else:
        memory_section = ""
    rel_section = build_relationship_section(rel)
    if rel_section:
        memory_section = (memory_section + "\n" + rel_section).strip()

    caps = capabilities(p.get("motivation", ""), can_guild_invite=p.get("can_guild_invite", False))
    if os.getenv("WBB_GUILD_ACTIONS") != "1":
        caps.discard("guild_invite")

    return CHAT_PROMPT.format(
        name=bot_name, level=p["level"], race=p["race"], class_name=p["class_name"],
        faction=p["faction"], who=p["who"], typing_style=p["typing_style"], mood=mood,
        current_goal=p["current_goal"], motivation_line=build_motivation_line(p.get("motivation", "")),
        self_section=build_self_section(get_memory_sheet(bot_name, "self")),
        identity_section="", examples_section="", moments_section="",
        context_section=context_section, memory_section=memory_section,
        nearby_section=build_nearby_section([]),
        action_rules=build_action_rules(PLAYER, caps=caps),
        life_rule=CHAT_LIFE_RULE_OPEN,
    )


def call(model: str, system: str, message: str) -> tuple[str, float]:
    t0 = time.time()
    resp = httpx.post(OLLAMA_URL, timeout=120.0, json={
        "model": model, "think": False, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": message}],
        "options": {"num_predict": 160, "temperature": 0.9},
    })
    resp.raise_for_status()
    raw = resp.json()["message"]["content"].strip()
    return truncate_sentences(raw, 4), time.time() - t0


def main():
    results = []
    for bot, msg, why in SCENARIOS:
        system = build_system(bot)  # identical prompt for both models
        p = get_or_create_personality(bot)
        print(f"\n{'='*78}\n{bot}  (L{p['level']} {p['race']} {p['class_name']}, "
              f"{p['identity_id']}, mot={p['motivation']})\n  WHY: {why}\n  Gus: \"{msg}\"")
        row = {"bot": bot, "identity": p["identity_id"], "msg": msg, "why": why, "out": {}}
        for model in MODELS:
            out, dt = call(model, system, msg)
            row["out"][model] = {"text": out, "secs": round(dt, 1)}
            print(f"\n  [{model}]  ({dt:.1f}s)\n    {out}")
        results.append(row)

    os.makedirs("eval/persona_ab", exist_ok=True)
    with open("eval/persona_ab/results.json", "w") as f:
        json.dump(results, f, indent=2)
    # latency summary
    print(f"\n{'='*78}\nLATENCY (avg secs/reply):")
    for model in MODELS:
        avg = sum(r["out"][model]["secs"] for r in results) / len(results)
        print(f"  {model}: {avg:.1f}s")
    print("\nSaved -> eval/persona_ab/results.json")


if __name__ == "__main__":
    main()
