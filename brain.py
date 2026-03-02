"""
brain.py
--------
Converts a natural language command (English or Russian) into a structured
JarvisIntent via the local Ollama LLM, with automatic Groq cloud fallback.

Priority chain:
  1. Ollama (local, private, no internet needed)
  2. Groq  (cloud, free tier, fast — kicks in if Ollama is down/slow)
  3. Rule-based fallback (offline, covers the basics)
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
import httpx
from pydantic import BaseModel, Field

import config

# ── Intent schema ─────────────────────────────────────────────────────────────

class JarvisIntent(BaseModel):
    action:   str
    target:   str | None = None
    value:    str | None = None
    language: str = "en"
    reply:    str


# ── Language detection (Python-side, reliable) ────────────────────────────────

def detect_language(text: str) -> str:
    """Detect language from script — Cyrillic = Russian, else English."""
    return "ru" if re.search(r"[а-яёА-ЯЁ]", text) else "en"


# ── System prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT_EN = """
You are JARVIS, an AI personal assistant. Parse the user command into JSON.

ACTIONS: open_app, close_app, focus_app, set_volume, set_brightness,
toggle_wifi, screenshot, get_weather, get_news, search_web,
play_music, pause_music, next_track, set_spotify_volume,
phone_sms, phone_ring, phone_battery, phone_notify,
open_file, find_file, list_directory,
chat

RULES:
- Respond ONLY in JSON, no markdown, no explanation.
- The "reply" field MUST be in English only.
- Keep reply to 1-2 sentences, Jarvis-style: capable and dry.
- "language" is always "en" for this prompt.
- For weather: extract the FULL location. "weather in basildon essex" -> target: "Basildon, Essex".
- For get_news: copy the user topic VERBATIM as target.
- For open_file/find_file: put ALL descriptive keywords verbatim into target.
  "vscode matugen template" -> target: "vscode matugen template".
  If user says "open with X", put app name in value.
- For list_directory: put directory name/path in target.

OUTPUT FORMAT:
{"action": "string", "target": "string or null", "value": "string or null", "language": "en", "reply": "string"}

EXAMPLES:
User: "open firefox"
{"action": "open_app", "target": "firefox", "value": null, "language": "en", "reply": "Opening Firefox."}

User: "open the vscode matugen template"
{"action": "open_file", "target": "vscode matugen template", "value": null, "language": "en", "reply": "Searching for that file."}

User: "find my hyprland config"
{"action": "find_file", "target": "hyprland config", "value": null, "language": "en", "reply": "Looking for your Hyprland config."}

User: "open the jarvis notes in obsidian"
{"action": "open_file", "target": "jarvis notes", "value": "obsidian", "language": "en", "reply": "Opening that in Obsidian."}

User: "show me my Downloads"
{"action": "list_directory", "target": "Downloads", "value": null, "language": "en", "reply": "Listing your Downloads folder."}

User: "what files are in my projects folder"
{"action": "list_directory", "target": "projects", "value": null, "language": "en", "reply": "Here's what's in your projects folder."}

User: "open the readme in my jarvis project"
{"action": "open_file", "target": "readme jarvis", "value": null, "language": "en", "reply": "Opening the README."}

User: "what's the weather"
{"action": "get_weather", "target": null, "value": null, "language": "en", "reply": "Fetching current weather."}

User: "weather in basildon essex"
{"action": "get_weather", "target": "Basildon, Essex", "value": null, "language": "en", "reply": "Getting the weather for Basildon, Essex."}

User: "what's the news on Russia Ukraine ceasefire talks"
{"action": "get_news", "target": "Russia Ukraine ceasefire talks", "value": null, "language": "en", "reply": "Searching for the latest on Russia Ukraine ceasefire talks."}

User: "volume up"
{"action": "set_volume", "target": null, "value": "up", "language": "en", "reply": "Increasing volume."}

User: "hi jarvis, what can you do?"
{"action": "chat", "target": null, "value": null, "language": "en", "reply": "I can open apps and files, check weather, search news, control your phone, take screenshots, and more."}
"""

SYSTEM_PROMPT_RU = """
Ты ДЖАРВИС, ИИ-ассистент. Разбери команду пользователя в JSON.

ДЕЙСТВИЯ: open_app, close_app, focus_app, set_volume, set_brightness,
toggle_wifi, screenshot, get_weather, get_news, search_web,
play_music, pause_music, next_track, set_spotify_volume,
phone_sms, phone_ring, phone_battery, phone_notify,
open_file, find_file, list_directory,
chat

ПРАВИЛА:
- Отвечай ТОЛЬКО JSON, без markdown и объяснений.
- Поле "reply" ТОЛЬКО на русском языке.
- Ответ 1-2 коротких предложения, стиль Джарвиса: чётко и по делу.
- "language" всегда "ru" в этом промпте.
- Для погоды: извлекай ПОЛНОЕ название места.
- Для get_news: копируй тему пользователя ДОСЛОВНО в target.
- Для open_file/find_file: помести ВСЕ ключевые слова описания в target дословно.
  "конфиг hyprland" -> target: "конфиг hyprland".
  Если сказано "открой в X", имя приложения помести в value.
- Для list_directory: имя папки или путь в target.

ФОРМАТ:
{"action": "строка", "target": "строка или null", "value": "строка или null", "language": "ru", "reply": "строка"}

ПРИМЕРЫ:
Пользователь: "открой firefox"
{"action": "open_app", "target": "firefox", "value": null, "language": "ru", "reply": "Открываю Firefox."}

Пользователь: "открой шаблон vscode для matugen"
{"action": "open_file", "target": "vscode matugen шаблон", "value": null, "language": "ru", "reply": "Ищу этот файл."}

Пользователь: "найди конфиг hyprland"
{"action": "find_file", "target": "hyprland config", "value": null, "language": "ru", "reply": "Ищу конфиг Hyprland."}

Пользователь: "покажи папку Загрузки"
{"action": "list_directory", "target": "Downloads", "value": null, "language": "ru", "reply": "Показываю содержимое папки Загрузки."}

Пользователь: "какая погода"
{"action": "get_weather", "target": null, "value": null, "language": "ru", "reply": "Получаю данные о погоде."}

Пользователь: "увеличь громкость"
{"action": "set_volume", "target": null, "value": "up", "language": "ru", "reply": "Увеличиваю громкость."}
"""


def _build_system_prompt(lang: str, memory_context: str = "") -> str:
    """Build the system prompt, optionally injecting memory context."""
    base = SYSTEM_PROMPT_RU if lang == "ru" else SYSTEM_PROMPT_EN
    if memory_context:
        return base.strip() + f"\n\n{memory_context}\n"
    return base


def _history_to_messages(history: list[tuple[str, str]]) -> list[dict]:
    """
    Convert conversation history tuples (role, text) to LLM message dicts.
    role is "user" or "assistant". We pass raw text, not JSON intents, so
    the LLM has natural language context for pronoun resolution etc.
    e.g. "open spotify" then "pause it" → LLM knows "it" = spotify.
    """
    msgs = []
    for role, text in history[-6:]:    # last 3 exchanges (6 messages)
        msgs.append({"role": role, "content": text})
    return msgs


# ── Ollama call ───────────────────────────────────────────────────────────────

def _call_ollama(
    user_input: str,
    lang: str,
    memory_context: str = "",
    history: list[tuple[str, str]] | None = None,
) -> JarvisIntent | None:
    system = _build_system_prompt(lang, memory_context)
    history_msgs = _history_to_messages(history or [])
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model":  config.OLLAMA_MODEL,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2},
                    "messages": [
                        {"role": "system", "content": system},
                        *history_msgs,
                        {"role": "user",   "content": user_input},
                    ],
                },
            )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        data = json.loads(content)
        data["language"] = lang
        intent = JarvisIntent(**data)
        print(f"[brain] ollama:{config.OLLAMA_MODEL} → {intent.action} | target={intent.target}")
        return intent

    except Exception as e:
        print(f"[brain] Ollama error: {e}")
        return None


# ── Groq cloud fallback ───────────────────────────────────────────────────────

def _call_groq(
    user_input: str,
    lang: str,
    memory_context: str = "",
    history: list[tuple[str, str]] | None = None,
) -> JarvisIntent | None:
    """
    Call Groq's OpenAI-compatible API as a cloud fallback.
    Free tier: https://console.groq.com — no credit card required.
    """
    if not config.GROQ_API_KEY:
        print("[brain] Groq skipped — GROQ_API_KEY not set")
        return None

    system = _build_system_prompt(lang, memory_context)
    history_msgs = _history_to_messages(history or [])

    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.post(
                f"{config.GROQ_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.GROQ_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       config.GROQ_MODEL,
                    "temperature": 0.2,
                    "max_tokens":  300,
                    "messages": [
                        {"role": "system", "content": system},
                        *history_msgs,
                        {"role": "user",   "content": user_input},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        data["language"] = lang
        intent = JarvisIntent(**data)
        print(f"[brain] groq:{config.GROQ_MODEL} → {intent.action} | target={intent.target}")
        return intent

    except Exception as e:
        print(f"[brain] Groq error: {e}")
        return None


# ── Fallback ──────────────────────────────────────────────────────────────────

def _fallback_intent(user_input: str, lang: str) -> JarvisIntent:
    low = user_input.lower()

    if any(w in low for w in ["open", "launch", "start", "открой", "запусти"]):
        words = low.split()
        target = words[-1] if len(words) > 1 else None
        reply = f"Opening {target}." if lang == "en" else f"Открываю {target}."
        return JarvisIntent(action="open_app", target=target, language=lang, reply=reply)

    if any(w in low for w in ["weather", "погода", "погоду"]):
        reply = "Fetching weather." if lang == "en" else "Получаю погоду."
        return JarvisIntent(action="get_weather", language=lang, reply=reply)

    if any(w in low for w in ["volume", "громкость"]):
        val = "up"   if any(w in low for w in ["up", "louder", "громче"]) else \
              "down" if any(w in low for w in ["down", "quiet", "тише"])  else "mute"
        reply = "Adjusting volume." if lang == "en" else "Регулирую громкость."
        return JarvisIntent(action="set_volume", value=val, language=lang, reply=reply)

    reply = ("Both local and cloud AI are unreachable. Check your connections."
             if lang == "en" else
             "Ни локальный, ни облачный ИИ недоступны. Проверьте соединение.")
    return JarvisIntent(action="chat", language=lang, reply=reply)


# ── Public API ────────────────────────────────────────────────────────────────

def parse_intent(
    user_input: str,
    history: list[tuple[str, str]] | None = None,
) -> JarvisIntent:
    """
    Parse a natural language command into a JarvisIntent.

    history: list of (role, text) tuples for multi-turn context.
             role is "user" or "assistant".
             Pass the last few exchanges so "pause it" works after "open spotify".

    Priority:
      1. Ollama (local)
      2. Groq  (cloud fallback, free tier)
      3. Rule-based fallback
    """
    lang = detect_language(user_input)

    # Inject memory context if available
    memory_context = ""
    if config.MEMORY_ENABLED:
        try:
            from skills.memory import get_context_hint
            memory_context = get_context_hint(lang)
        except Exception:
            pass

    # 1. Try Ollama
    result = _call_ollama(user_input, lang, memory_context, history)
    if result:
        return result

    # 2. Try Groq (cloud)
    print("[brain] Ollama unavailable — trying Groq cloud fallback...")
    result = _call_groq(user_input, lang, memory_context, history)
    if result:
        return result

    # 3. Rule-based fallback
    print("[brain] All LLMs unavailable — using rule-based fallback")
    return _fallback_intent(user_input, lang)


def check_ollama_alive() -> bool:
    try:
        with httpx.Client(timeout=3.0) as c:
            r = c.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def check_groq_alive() -> bool:
    """Returns True if Groq API key is set and reachable."""
    if not config.GROQ_API_KEY:
        return False
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(
                f"{config.GROQ_BASE_URL}/models",
                headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
            )
            return r.status_code == 200
    except Exception:
        return False


def get_active_backend() -> str:
    """Return the name of whichever LLM backend is currently available."""
    if check_ollama_alive():
        return f"ollama:{config.OLLAMA_MODEL}"
    if config.GROQ_API_KEY and check_groq_alive():
        return f"groq:{config.GROQ_MODEL}"
    return "fallback"