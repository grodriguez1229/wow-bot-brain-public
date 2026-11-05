import asyncio
import re

import httpx
from config import (OLLAMA_URL, OLLAMA_MODEL, OLLAMA_HEARD_MODEL, OLLAMA_CHAT_MODEL, LLM_MAX_CONCURRENCY, LLM_HEARD_CONCURRENCY,
                    LLM_TEMPERATURE, LLM_TOP_P, LLM_MIN_P, LLM_REPEAT_PENALTY,
                    LLM_REPEAT_LAST_N)

_TAG_RE = re.compile(r"\[(?:ACTION|EMOTE):[^\]]*\]", re.IGNORECASE)
_llm_sem = asyncio.Semaphore(LLM_MAX_CONCURRENCY)
_llm_heard_sem = asyncio.Semaphore(LLM_HEARD_CONCURRENCY)


def build_llm_options(num_predict: int) -> dict:
    """Ollama sampling options. Anti-repetition knobs (repeat_penalty/min_p) fight the
    fleet-wide sameness that makes ambient chatter read as one bot. All values come from
    config so they can be tuned via env and A/B'd without code changes."""
    return {
        "num_predict": num_predict,
        "temperature": LLM_TEMPERATURE,
        "top_p": LLM_TOP_P,
        "min_p": LLM_MIN_P,
        "repeat_penalty": LLM_REPEAT_PENALTY,
        "repeat_last_n": LLM_REPEAT_LAST_N,
    }


def pick_model(model: str | None, lane: str) -> str:
    """Explicit model (from the A/B harness) always wins. Otherwise the heard lane —
    the player-facing replies people actually read — gets OLLAMA_HEARD_MODEL, which
    defaults to the base model so this is a no-op until an operator sets it."""
    if model:
        return model
    if lane == "chat":
        return OLLAMA_CHAT_MODEL
    return OLLAMA_HEARD_MODEL if lane == "heard" else OLLAMA_MODEL


def truncate_sentences(text: str, max_sentences: int, min_chars: int = 15) -> str:
    """Safety net so the model can't ramble past the intended length. Returns text up
    to and including the Nth sentence-ending punctuation mark. Sentence- enders inside
    the first `min_chars` are ignored so a quick "u." or "ok." doesn't chop the reply."""
    text = text.strip()
    if max_sentences <= 0:
        return text
    count = 0
    i = 0
    n = len(text)
    while i < n:
        if text[i] in ".!?":
            end = i + 1
            while end < n and text[end] in ".!?":  # swallow "?!" / "..."
                end += 1
            count += 1
            # Only truncate once we've hit the budget AND have enough text to be a
            # real reply — guards against chopping a short "u." into nothing.
            if count >= max_sentences and end >= min_chars:
                return text[:end].strip()
            i = end
            continue
        i += 1
    return text


async def call_ollama(system_prompt: str, history: list[dict], user_message: str,
                      *, num_predict: int = 50, max_sentences: int = 2,
                      model: str | None = None, lane: str = "default") -> str:
    """Call the local Ollama chat endpoint.

    num_predict/max_sentences let callers pick a length budget: generous for CHAT
    (the persona needs room to surface) and tight for ambient TICK. `model` overrides
    the configured model — used by the live A/B harness — without touching config.
    `lane` selects which concurrency semaphore to acquire: "heard" gets a dedicated
    lane so /heard replies never queue behind tick backlog on the default lane.
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    sem = _llm_heard_sem if lane in ("heard", "chat") else _llm_sem
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with sem:
            resp = await client.post(OLLAMA_URL, json={
                "model": pick_model(model, lane),
                "think": False,  # qwen3.x thinking mode eats the num_predict budget -> empty content
                "messages": messages,
                "stream": False,
                "options": build_llm_options(num_predict),
            })
            resp.raise_for_status()

    data = resp.json()
    raw = data["message"]["content"].strip()
    # Action tags are not sentences: trim the text only, then keep the tags (R9 P4).
    tags = _TAG_RE.findall(raw)
    text = truncate_sentences(_TAG_RE.sub(" ", raw).strip(), max_sentences)
    return "\n".join([text] + tags) if tags else text


def parse_response(raw: str, incoming_channel: str = "SAY") -> dict:
    text = raw.strip('"').strip("'")

    # Strip asterisk actions
    while text.startswith("*") and "*" in text[1:]:
        end = text.find("*", 1)
        text = text[end + 1:].strip()

    # Parse actions. [ACTION:type target] is the documented form; models also
    # improvise [EMOTE:wave]. Both are parsed AND scrubbed so no tag text leaks
    # into the visible message (a real bug seen in eval: "[EMOTE:wave]" in chat).
    actions = []
    for m in re.finditer(r"\[ACTION:([^\]]+)\]", text, re.IGNORECASE):
        parts = m.group(1).strip().split(None, 1)
        if parts:
            action = {"type": parts[0].lower()}
            if len(parts) > 1:
                action["target"] = parts[1]
            actions.append(action)
    for m in re.finditer(r"\[EMOTE:([^\]]+)\]", text, re.IGNORECASE):
        tgt = m.group(1).strip().split()
        if tgt:
            actions.append({"type": "emote", "target": tgt[0]})
    # Scrub all recognized tags from the visible text, collapse leftover spaces.
    text = re.sub(r"\[(?:ACTION|EMOTE):[^\]]*\]", "", text, flags=re.IGNORECASE)
    # A tag cut off by the token budget ("sure [ACTION:invite Gu") must not leak either.
    text = re.sub(r"\[(?:ACTION|EMOTE)?:?[^\]]*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text).strip()

    channel = incoming_channel.upper() if incoming_channel else "SAY"
    if text.upper() == text and len(text) > 10:
        channel = "YELL"

    return {"message": text, "channel": channel, "emote": None, "actions": actions}
