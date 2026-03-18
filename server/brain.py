"""VPS-side NLP Brain for Hybrid Sasha assistant."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time

import httpx
from pydantic import BaseModel

import config
from identity import parse_invocation
from server.memory_store import get_context_hint


class SashaIntent(BaseModel):
    action: str
    target: str | None = None
    value: str | None = None
    language: str = "en"
    reply: str

# Backwards-compatible alias so existing imports of JarvisIntent keep working
JarvisIntent = SashaIntent


def detect_language(text: str) -> str:
    return "ru" if re.search(r"[а-яёА-ЯЁ]", text) else "en"


SYSTEM_PROMPT_EN = """
You are Sasha, a personal AI assistant running on the user's desktop.
Parse the user's request into a JSON intent object.

ACTIONS and when to use each:
- open_app         → open/launch/start an application. target = app name.
- close_app        → close/quit/kill an application. target = app name.
- focus_app        → switch to / bring up an app window. target = app name.
- open_file        → open a file, document, config, or script. target = descriptive keywords. value = app to use (optional, e.g. "code", "vlc").
- find_file        → search for / locate a file on disk. target = descriptive keywords.
- list_directory   → list files in a folder. target = folder name or path.
- set_volume       → adjust speaker volume. value = "up", "down", "mute", "unmute", or integer 0-150.
- set_brightness   → adjust screen brightness. value = "up", "down", or integer 0-100.
- toggle_wifi      → turn Wi-Fi on or off. value = "on", "off", or omit to toggle.
- toggle_bluetooth → turn Bluetooth on or off. value = "on", "off", or omit to toggle.
- screenshot       → capture the screen. value = "full" for fullscreen, or omit for region.
- get_weather      → get weather report. target = full city name (e.g. "London, England").
- get_news         → get news headlines. target = topic verbatim. Omit for general headlines.
- search_web       → search the internet. value = search query.
- get_datetime     → get current date and/or time.
- play_music       → start music playback.
- pause_music      → pause/stop media playback.
- previous_track   → go to previous song/track.
- next_track       → skip to next song/track.
- set_spotify_volume → set media player volume. value = integer 0-100.
- phone_sms        → send SMS. target = contact name. value = message text.
- phone_ring       → ring the phone to find it.
- phone_battery    → check phone battery percentage.
- phone_notify     → read phone notifications.
- remember_fact    → store a fact in memory. target = short label (2-4 words). value = what to store.
- calculate        → evaluate a math expression or conversion. value = the expression exactly.
- system_info      → get system status (CPU load, RAM, disk space).
- chat             → general question, knowledge lookup, or anything not covered above.

STRICT RULES:
- Respond ONLY with raw JSON. No markdown, no code blocks, no text outside the JSON.
- "reply" must be a short, natural, helpful English response (1-3 sentences).
  For chat questions, answer directly and correctly in "reply" — do NOT deflect.
- Do NOT say "I cannot" or "I don't have access" — answer knowledge questions in "reply".
- For open_file/find_file: put ALL descriptive keywords verbatim in target.
- For remember_fact: target = short key (e.g. "favourite editor"), value = what to store.
- For calculate: put the exact user expression in value (e.g. "15% of 240").
- "language" is always "en" in this prompt.

OUTPUT FORMAT (exact schema):
{"action":"string","target":"string or null","value":"string or null","language":"en","reply":"string"}

EXAMPLES:
User: "open firefox"
{"action":"open_app","target":"firefox","value":null,"language":"en","reply":"Opening Firefox."}

User: "what time is it"
{"action":"get_datetime","target":null,"value":null,"language":"en","reply":"Checking the time."}

User: "what's 15% of 240"
{"action":"calculate","target":null,"value":"15% of 240","language":"en","reply":"Calculating that for you."}

User: "remember my favourite editor is neovim"
{"action":"remember_fact","target":"favourite editor","value":"neovim","language":"en","reply":"Got it, I'll remember that."}

User: "weather in Basildon, Essex"
{"action":"get_weather","target":"Basildon, Essex","value":null,"language":"en","reply":"Fetching weather for Basildon, Essex."}

User: "news on Russia Ukraine ceasefire"
{"action":"get_news","target":"Russia Ukraine ceasefire","value":null,"language":"en","reply":"Searching for the latest."}

User: "volume up"
{"action":"set_volume","target":null,"value":"up","language":"en","reply":"Increasing volume."}

User: "find my hyprland config"
{"action":"find_file","target":"hyprland config","value":null,"language":"en","reply":"Searching for your Hyprland config."}

User: "open the readme in my jarvis project with vscode"
{"action":"open_file","target":"readme jarvis","value":"code","language":"en","reply":"Opening the README in VS Code."}

User: "what's the capital of France"
{"action":"chat","target":null,"value":null,"language":"en","reply":"The capital of France is Paris."}

User: "turn bluetooth off"
{"action":"toggle_bluetooth","target":null,"value":"off","language":"en","reply":"Turning Bluetooth off."}

User: "previous track"
{"action":"previous_track","target":null,"value":null,"language":"en","reply":"Going to the previous track."}

User: "how much RAM am I using"
{"action":"system_info","target":null,"value":null,"language":"en","reply":"Checking your system status."}
"""

SYSTEM_PROMPT_RU = """
Ты Саша, персональный ИИ-ассистент, работающий на компьютере пользователя.
Преобразуй запрос пользователя в JSON-объект намерения.

ДЕЙСТВИЯ и когда их применять:
- open_app         → открыть/запустить приложение. target = название.
- close_app        → закрыть приложение. target = название.
- focus_app        → переключиться на окно. target = название.
- open_file        → открыть файл. target = ключевые слова. value = приложение (опционально).
- find_file        → найти файл. target = ключевые слова.
- list_directory   → показать содержимое папки. target = путь/название.
- set_volume       → громкость. value = "up", "down", "mute", "unmute" или число 0-150.
- set_brightness   → яркость. value = "up", "down" или число 0-100.
- toggle_wifi      → Wi-Fi. value = "on", "off" или пусто.
- toggle_bluetooth → Bluetooth. value = "on", "off" или пусто.
- screenshot       → скриншот. value = "full" или пусто.
- get_weather      → погода. target = название города.
- get_news         → новости. target = тема (дословно). Пусто — общие новости.
- search_web       → поиск в интернете. value = запрос.
- get_datetime     → текущие дата и/или время.
- play_music       → воспроизведение музыки.
- pause_music      → пауза.
- previous_track   → предыдущий трек.
- next_track       → следующий трек.
- set_spotify_volume → громкость плеера. value = число 0-100.
- phone_sms        → отправить SMS. target = контакт. value = текст.
- phone_ring       → позвонить чтобы найти телефон.
- phone_battery    → заряд телефона.
- phone_notify     → уведомления телефона.
- remember_fact    → запомнить факт. target = метка (2-4 слова). value = что запомнить.
- calculate        → вычисление. value = выражение точно как сказал пользователь.
- system_info      → состояние системы (CPU, RAM, диск).
- chat             → общий вопрос, разговор или что-то другое.

СТРОГИЕ ПРАВИЛА:
- Отвечай ТОЛЬКО сырым JSON. Без markdown, без блоков кода, без пояснений.
- "reply" — краткий естественный ответ на русском. На вопросы отвечай прямо и точно.
- Не пиши "не могу" — отвечай на общие вопросы в "reply".
- "language" всегда "ru" в этом промпте.

ФОРМАТ (строго):
{"action":"string","target":"string or null","value":"string or null","language":"ru","reply":"string"}

ПРИМЕРЫ:
Пользователь: "открой firefox"
{"action":"open_app","target":"firefox","value":null,"language":"ru","reply":"Открываю Firefox."}

Пользователь: "который час"
{"action":"get_datetime","target":null,"value":null,"language":"ru","reply":"Проверяю время."}

Пользователь: "сколько 15% от 240"
{"action":"calculate","target":null,"value":"15% от 240","language":"ru","reply":"Считаю."}

Пользователь: "запомни, мой любимый редактор — neovim"
{"action":"remember_fact","target":"любимый редактор","value":"neovim","language":"ru","reply":"Запомнила."}

Пользователь: "погода в Москве"
{"action":"get_weather","target":"Москва","value":null,"language":"ru","reply":"Получаю погоду для Москвы."}

Пользователь: "какая столица Франции"
{"action":"chat","target":null,"value":null,"language":"ru","reply":"Столица Франции — Париж."}

Пользователь: "предыдущий трек"
{"action":"previous_track","target":null,"value":null,"language":"ru","reply":"Переключаю на предыдущий трек."}

Пользователь: "сколько RAM используется"
{"action":"system_info","target":null,"value":null,"language":"ru","reply":"Проверяю состояние системы."}
"""


def _history_to_messages(history: list[tuple[str, str]]) -> list[dict]:
    return [{"role": role, "content": text} for role, text in history[-6:]]


def _extract_json(text: str) -> str:
    """Extract a JSON object from text that may contain markdown wrapping or prose."""
    text = text.strip()
    if text.startswith("{"):
        return text
    # Markdown code block: ```json { ... } ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # First bare JSON object anywhere in the text
    m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text


def _chat_freeform(
    user_input: str,
    lang: str,
    history: list[tuple[str, str]] | None,
) -> str | None:
    """Free-form conversational LLM call — no JSON constraint, higher temperature.
    Used to generate rich answers when action=='chat'.
    """
    sys_prompt = (
        "You are Sasha, a helpful personal AI assistant running on the user's desktop. "
        "Answer the user's question directly, helpfully, and concisely. "
        "For factual questions give a clear accurate answer. "
        "For conversational messages respond naturally. "
        "Keep responses under 4 sentences unless the question genuinely needs more detail. "
        + ("Respond in Russian." if lang == "ru" else "Respond in English.")
    )
    msgs: list[dict] = [{"role": "system", "content": sys_prompt}]
    for role, text in (history or [])[-6:]:
        msgs.append({"role": role, "content": text})
    msgs.append({"role": "user", "content": user_input})

    # Try Ollama first
    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": config.OLLAMA_MODEL,
                    "stream": False,
                    "options": {"temperature": 0.7},
                    "messages": msgs,
                },
            )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
    except Exception:
        pass

    # Groq fallback for freeform chat
    if config.GROQ_API_KEY:
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{config.GROQ_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": config.GROQ_MODEL,
                        "temperature": 0.7,
                        "max_tokens": 400,
                        "messages": msgs,
                    },
                )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

    return None


def _build_prompt(lang: str) -> str:
    base = SYSTEM_PROMPT_RU if lang == "ru" else SYSTEM_PROMPT_EN
    memory = get_context_hint(lang)
    extension = _load_system_prompt_extension(lang)

    parts = [base.strip()]
    if memory:
        parts.append(memory)
    if extension:
        parts.append("SYSTEM PROMPT SETTINGS:\n" + extension)
    return "\n\n".join(parts) + "\n"


def _load_system_prompt_extension(lang: str) -> str:
    parts: list[str] = []

    # Global extension from env
    if config.SYSTEM_PROMPT_GLOBAL:
        parts.append(config.SYSTEM_PROMPT_GLOBAL)

    # Language-specific extension from env
    lang_ext = config.SYSTEM_PROMPT_RU if lang == "ru" else config.SYSTEM_PROMPT_EN
    if lang_ext:
        parts.append(lang_ext)

    # Optional prompt file from ~/.config/jarvis/system_prompt.txt
    try:
        if config.SYSTEM_PROMPT_FILE.exists():
            text = config.SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
    except Exception:
        pass

    return "\n\n".join(p.strip() for p in parts if p.strip())


def ollama_has_model(model_name: str) -> bool:
    try:
        with httpx.Client(timeout=6.0) as c:
            r = c.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            r.raise_for_status()
            models = r.json().get("models", [])
            names = {m.get("name") for m in models if isinstance(m, dict)}
            return model_name in names
    except Exception:
        return False


def _try_start_ollama_server() -> bool:
    if not shutil.which("ollama"):
        return False
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        return False

    for _ in range(20):
        if check_ollama_alive():
            return True
        time.sleep(0.5)
    return False


def ensure_ollama_model_available(
    auto_start: bool = True,
    auto_pull: bool = True,
) -> tuple[bool, str]:
    """Ensure Ollama is reachable and the configured model is present."""
    if not check_ollama_alive():
        if auto_start:
            started = _try_start_ollama_server()
            if not started:
                return False, "Ollama is offline and could not be auto-started."
        else:
            return False, "Ollama is offline."

    if ollama_has_model(config.OLLAMA_MODEL):
        return True, f"Model '{config.OLLAMA_MODEL}' is ready."

    if not auto_pull:
        return False, f"Model '{config.OLLAMA_MODEL}' is not installed."

    try:
        with httpx.Client(timeout=600.0) as c:
            r = c.post(
                f"{config.OLLAMA_BASE_URL}/api/pull",
                json={"model": config.OLLAMA_MODEL, "stream": False},
            )
            r.raise_for_status()
    except Exception as e:
        return False, f"Failed to pull model '{config.OLLAMA_MODEL}': {e}"

    if ollama_has_model(config.OLLAMA_MODEL):
        return True, f"Model '{config.OLLAMA_MODEL}' was pulled and is ready."
    return False, f"Model '{config.OLLAMA_MODEL}' still unavailable after pull."


def _call_ollama(user_input: str, lang: str, history: list[tuple[str, str]] | None) -> SashaIntent | None:
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": config.OLLAMA_MODEL,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2},
                    "messages": [
                        {"role": "system", "content": _build_prompt(lang)},
                        *_history_to_messages(history or []),
                        {"role": "user", "content": user_input},
                    ],
                },
            )
        resp.raise_for_status()
        data = json.loads(_extract_json(resp.json()["message"]["content"]))
        data["language"] = lang
        return SashaIntent(**data)
    except Exception:
        return None


def _call_groq(user_input: str, lang: str, history: list[tuple[str, str]] | None) -> SashaIntent | None:
    if not config.GROQ_API_KEY:
        return None
    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.post(
                f"{config.GROQ_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.GROQ_MODEL,
                    "temperature": 0.2,
                    "max_tokens": 300,
                    "messages": [
                        {"role": "system", "content": _build_prompt(lang)},
                        *_history_to_messages(history or []),
                        {"role": "user", "content": user_input},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
        resp.raise_for_status()
        data = json.loads(_extract_json(resp.json()["choices"][0]["message"]["content"]))
        data["language"] = lang
        return SashaIntent(**data)
    except Exception:
        return None


def _fallback_intent(user_input: str, lang: str) -> SashaIntent:
    low = user_input.lower()
    if any(w in low for w in ["open", "launch", "start", "открой", "запусти"]):
        target = low.split()[-1] if len(low.split()) > 1 else None
        reply = f"Opening {target}." if lang == "en" else f"Открываю {target}."
        return SashaIntent(action="open_app", target=target, language=lang, reply=reply)
    if any(w in low for w in ["weather", "погода", "погоду"]):
        reply = "Fetching weather." if lang == "en" else "Получаю погоду."
        return SashaIntent(action="get_weather", language=lang, reply=reply)
    if any(w in low for w in ["volume", "громкость"]):
        val = "up" if any(w in low for w in ["up", "больше", "громче"]) else "down"
        reply = "Adjusting volume." if lang == "en" else "Регулирую громкость."
        return SashaIntent(action="set_volume", target=None, value=val, language=lang, reply=reply)
    if any(w in low for w in ["screenshot", "скриншот"]):
        return SashaIntent(action="screenshot", language=lang,
                           reply="Taking a screenshot." if lang == "en" else "Делаю скриншот.")
    if any(w in low for w in ["time", "date", "clock", "час", "время", "дата"]):
        return SashaIntent(action="get_datetime", language=lang,
                           reply="Checking the time." if lang == "en" else "Проверяю время.")
    return SashaIntent(
        action="chat",
        language=lang,
        reply=(
            "Both local and cloud AI are unreachable. Check that Ollama is running."
            if lang == "en"
            else "Ни локальный, ни облачный ИИ недоступны. Проверьте соединение."
        ),
    )


def parse_intent(user_input: str, history: list[tuple[str, str]] | None = None) -> SashaIntent:
    inv = parse_invocation(user_input)
    effective_input = inv.remainder if inv.matched_alias and inv.remainder else user_input
    lang = detect_language(effective_input)

    # Alias-only invocations act as a direct ping.
    if inv.is_ping:
        return SashaIntent(
            action="chat",
            language=lang,
            reply=("Yes, I'm here." if lang == "en" else "Да, я на связи."),
        )

    result = _call_ollama(effective_input, lang, history)
    if result:
        if result.action == "chat":
            freeform = _chat_freeform(effective_input, lang, history)
            if freeform:
                result.reply = freeform
        return result

    result = _call_groq(effective_input, lang, history)
    if result:
        if result.action == "chat":
            freeform = _chat_freeform(effective_input, lang, history)
            if freeform:
                result.reply = freeform
        return result

    return _fallback_intent(effective_input, lang)


def check_ollama_alive() -> bool:
    try:
        with httpx.Client(timeout=3.0) as c:
            r = c.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def check_groq_alive() -> bool:
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
    if check_ollama_alive():
        return f"ollama:{config.OLLAMA_MODEL}"
    if check_groq_alive():
        return f"groq:{config.GROQ_MODEL}"
    return "fallback"
