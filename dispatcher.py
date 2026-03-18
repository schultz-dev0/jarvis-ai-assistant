"""Compatibility dispatcher for local in-process mode.

Authoritative hybrid dispatcher is server/dispatcher.py.
"""

from __future__ import annotations

from brain import JarvisIntent
from satellite_executor import execute_tool


def dispatch(intent: JarvisIntent, raw_input: str = "") -> str:
    lang = intent.language or "en"
    action = intent.action
    target = intent.target or ""
    value = intent.value or ""

    if action == "open_app":
        result = execute_tool("apps.open_app", {"target": target})
        return intent.reply or result
    if action == "close_app":
        result = execute_tool("apps.close_app", {"target": target})
        return intent.reply or result
    if action == "focus_app":
        result = execute_tool("apps.focus_app", {"target": target})
        return intent.reply or result

    if action == "open_file":
        result = execute_tool(
            "files.open_file",
            {"query": target or raw_input, "app_override": value or None, "lang": lang},
        )
        return intent.reply or result
    if action == "find_file":
        return execute_tool("files.find_file", {"query": target or raw_input, "lang": lang})
    if action == "list_directory":
        return execute_tool("files.list_directory", {"path": target or raw_input or "~", "lang": lang})

    if action == "set_volume":
        result = execute_tool("system.set_volume", {"value": value})
        return intent.reply or result
    if action == "set_brightness":
        result = execute_tool("system.set_brightness", {"value": value})
        return intent.reply or result
    if action == "toggle_wifi":
        result = execute_tool("system.toggle_wifi", {"value": value})
        return intent.reply or result
    if action == "screenshot":
        mode = "full" if "full" in (value + raw_input).lower() else "region"
        result = execute_tool("system.screenshot", {"mode": mode})
        return intent.reply or result

    if action == "get_weather":
        return execute_tool("web.get_weather", {"location": target or None, "lang": lang})
    if action == "get_news":
        return execute_tool("web.get_news", {"topic": target or None, "lang": lang})
    if action == "search_web":
        return execute_tool("web.search_web", {"query": value or target, "lang": lang})

    if action == "play_music":
        result = execute_tool("media.play_music", {})
        return intent.reply or result
    if action == "pause_music":
        result = execute_tool("media.pause_music", {"lang": lang})
        return intent.reply or result
    if action == "next_track":
        result = execute_tool("media.next_track", {"lang": lang})
        return intent.reply or result
    if action == "set_spotify_volume":
        result = execute_tool("media.set_spotify_volume", {"value": value, "lang": lang})
        return intent.reply or result

    if action == "phone_sms":
        return execute_tool("phone.send_sms", {"contact": target, "message": value})
    if action == "phone_ring":
        return execute_tool("phone.ring_phone", {})
    if action == "phone_battery":
        return execute_tool("phone.get_battery", {"lang": lang})
    if action == "phone_notify":
        return execute_tool("phone.get_notifications", {"lang": lang})

    if action == "get_datetime":
        return execute_tool("system.get_datetime", {"lang": lang})
    if action == "system_info":
        return execute_tool("system.get_info", {"lang": lang})
    if action == "remember_fact":
        return execute_tool("memory.store_fact", {"key": target, "value": value, "lang": lang})
    if action == "calculate":
        result = execute_tool("system.calculate", {"value": value, "lang": lang})
        return intent.reply or result
    if action == "previous_track":
        result = execute_tool("media.previous_track", {"lang": lang})
        return intent.reply or result
    if action == "toggle_bluetooth":
        result = execute_tool("system.toggle_bluetooth", {"value": value, "lang": lang})
        return intent.reply or result

    if action == "chat":
        return intent.reply or ("I'm not sure how to help with that." if lang == "en" else "Не знаю, как помочь.")   

    return intent.reply or ("Done." if lang == "en" else "Готово.")
