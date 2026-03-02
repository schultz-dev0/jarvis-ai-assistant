"""
dispatcher.py
-------------
Routes a JarvisIntent to the appropriate skill and returns a text result.
The result is used by TTS and displayed in the UI.
"""

from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain import JarvisIntent

import skills.apps   as apps
import skills.system as system
import skills.web    as web
import skills.phone  as phone


def dispatch(intent: JarvisIntent, raw_input: str = "") -> str:
    """
    Execute the intent and return a final spoken/displayed response string.
    """
    lang   = intent.language or "en"
    action = intent.action
    target = intent.target or ""
    value  = intent.value  or ""

    # ── App control ───────────────────────────────────────────────────────────
    if action == "open_app":
        result = apps.open_app(target)
        return intent.reply or result

    elif action == "close_app":
        result = apps.close_app(target)
        return intent.reply or result

    elif action == "focus_app":
        result = apps.focus_app(target)
        return intent.reply or result

    # ── File system ───────────────────────────────────────────────────────────
    elif action in ("open_file", "find_file"):
        # For open_file we search AND open the best match.
        # For find_file we search and report — user decides whether to open.
        from skills.files import find_and_open, find_files, search_files_by_name
        import re

        query = target or raw_input

        if action == "find_file":
            # Just report matches, don't auto-open
            results = find_files(query, max_results=5)
            if not results:
                return (
                    f"No files found matching '{query}'."
                    if lang == "en"
                    else f"Файлов по запросу «{query}» не найдено."
                )
            from pathlib import Path
            home = Path.home()
            lines = [(f"Files matching '{query}':" if lang == "en"
                      else f"Файлы по запросу «{query}»:")]
            for r in results:
                try:
                    rel = r.path.relative_to(home)
                    lines.append(f"  ~/{rel}  (score: {r.score:.2f})")
                except ValueError:
                    lines.append(f"  {r.path}")
            return "\n".join(lines)

        else:
            # open_file: search and open
            # If value specifies an app override, honour it
            app_override = value if value else None
            if app_override:
                from skills.files import find_files, open_path
                results = find_files(query)
                if results:
                    from pathlib import Path
                    import shutil
                    exe = app_override.lower().strip()
                    if not shutil.which(exe):
                        # Try common aliases
                        _aliases = {"vscode": "code", "obsidian": "obsidian",
                                    "nautilus": "nautilus", "vlc": "vlc"}
                        exe = _aliases.get(exe, exe)
                    result = open_path(results[0].path, exe if shutil.which(exe) else None)
                    return result
            return find_and_open(query, lang=lang)

    elif action == "list_directory":
        from skills.files import list_directory
        path_str = target or raw_input or "~"
        return list_directory(path_str, lang=lang)

    # ── System ────────────────────────────────────────────────────────────────
    elif action == "set_volume":
        result = system.set_volume(value)
        return intent.reply or result

    elif action == "set_brightness":
        result = system.set_brightness(value)
        return intent.reply or result

    elif action == "toggle_wifi":
        result = system.toggle_wifi(value)
        return intent.reply or result

    elif action == "screenshot":
        mode = "full" if "full" in (value + raw_input).lower() else "region"
        result = system.screenshot(mode)
        return intent.reply or result

    # ── Web / Information ─────────────────────────────────────────────────────
    elif action == "get_weather":
        return web.get_weather(location=target or None, lang=lang)

    elif action == "get_news":
        return web.get_news(topic=target or None, lang=lang)

    elif action == "search_web":
        return web.search_web(query=value or target, lang=lang)

    elif action in ("get_time", "get_date", "what_time"):
        return web.get_datetime(lang=lang)

    # ── Music ─────────────────────────────────────────────────────────────────
    elif action == "play_music":
        apps.open_app("spotify")
        return intent.reply or ("Playing music." if lang == "en" else "Играю музыку.")

    elif action == "pause_music":
        import subprocess
        subprocess.run(["playerctl", "pause"])
        return intent.reply or ("Paused." if lang == "en" else "Пауза.")

    elif action == "next_track":
        import subprocess
        subprocess.run(["playerctl", "next"])
        return intent.reply or ("Next track." if lang == "en" else "Следующий трек.")

    elif action == "set_spotify_volume":
        import subprocess
        try:
            vol = int(value)
            subprocess.run(["playerctl", "volume", str(vol / 100)])
            return intent.reply or f"Volume set to {vol}%."
        except Exception:
            return "Couldn't set volume."

    # ── Phone ─────────────────────────────────────────────────────────────────
    elif action == "phone_sms":
        return phone.send_sms(contact=target, message=value)

    elif action == "phone_ring":
        return phone.ring_phone()

    elif action == "phone_battery":
        return phone.get_battery(lang=lang)

    elif action == "phone_notify":
        return phone.get_notifications(lang=lang)

    # ── General chat ──────────────────────────────────────────────────────────
    elif action == "chat":
        return intent.reply or _chat_fallback(raw_input, lang)

    elif action == "unknown":
        if lang == "ru":
            return "Не понял команду. Попробуйте ещё раз."
        return "I didn't catch that. Could you rephrase?"

    else:
        return intent.reply or (
            "Done." if lang == "en" else "Готово."
        )


def _chat_fallback(text: str, lang: str) -> str:
    if lang == "ru":
        return "Я пока не могу ответить на этот вопрос без подключения к мозгу."
    return "I'm having trouble thinking right now. Check that Ollama is running."