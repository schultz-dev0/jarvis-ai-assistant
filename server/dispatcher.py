"""Server-side dispatcher that sends action requests to a connected Satellite."""

from __future__ import annotations

from typing import Any

from server.brain import SashaIntent as SashaIntent  # noqa: F401
# Backwards-compat alias kept so existing code using JarvisIntent still imports cleanly
JarvisIntent = SashaIntent
from server.protocol import make_execute_action


class DispatcherError(RuntimeError):
    pass


async def _call_tool(
    bridge,
    satellite_id: str,
    intent: SashaIntent,
    tool: str,
    arguments: dict[str, Any],
) -> str:
    request = make_execute_action(
        tool=tool,
        arguments=arguments,
        intent_action=intent.action,
    )
    response = await bridge.request_action(satellite_id, request)
    payload = response.get("payload") or {}
    if not payload.get("ok", False):
        raise DispatcherError(payload.get("error") or "Satellite execution failed")
    return str(payload.get("result") or "")


async def dispatch_intent(
    intent: SashaIntent,
    bridge,
    satellite_id: str,
    raw_input: str = "",
) -> str:
    action = intent.action
    lang = intent.language or "en"
    target = intent.target or ""
    value = intent.value or ""

    if action == "open_app":
        result = await _call_tool(bridge, satellite_id, intent, "apps.open_app", {"target": target})
        return intent.reply or result
    if action == "close_app":
        result = await _call_tool(bridge, satellite_id, intent, "apps.close_app", {"target": target})
        return intent.reply or result
    if action == "focus_app":
        result = await _call_tool(bridge, satellite_id, intent, "apps.focus_app", {"target": target})
        return intent.reply or result

    if action == "open_file":
        result = await _call_tool(
            bridge,
            satellite_id,
            intent,
            "files.open_file",
            {"query": target or raw_input, "app_override": value or None, "lang": lang},
        )
        return intent.reply or result
    if action == "find_file":
        result = await _call_tool(
            bridge,
            satellite_id,
            intent,
            "files.find_file",
            {"query": target or raw_input, "lang": lang},
        )
        return result
    if action == "list_directory":
        result = await _call_tool(
            bridge,
            satellite_id,
            intent,
            "files.list_directory",
            {"path": target or raw_input or "~", "lang": lang},
        )
        return result

    if action == "set_volume":
        result = await _call_tool(bridge, satellite_id, intent, "system.set_volume", {"value": value})
        return intent.reply or result
    if action == "set_brightness":
        result = await _call_tool(bridge, satellite_id, intent, "system.set_brightness", {"value": value})
        return intent.reply or result
    if action == "toggle_wifi":
        result = await _call_tool(bridge, satellite_id, intent, "system.toggle_wifi", {"value": value})
        return intent.reply or result
    if action == "screenshot":
        mode = "full" if "full" in (value + raw_input).lower() else "region"
        result = await _call_tool(bridge, satellite_id, intent, "system.screenshot", {"mode": mode})
        return intent.reply or result

    if action == "get_weather":
        return await _call_tool(bridge, satellite_id, intent, "web.get_weather", {"location": target or None, "lang": lang})
    if action == "get_news":
        return await _call_tool(bridge, satellite_id, intent, "web.get_news", {"topic": target or None, "lang": lang})
    if action == "search_web":
        return await _call_tool(bridge, satellite_id, intent, "web.search_web", {"query": value or target, "lang": lang})

    if action == "play_music":
        result = await _call_tool(bridge, satellite_id, intent, "media.play_music", {})
        return intent.reply or result
    if action == "pause_music":
        result = await _call_tool(bridge, satellite_id, intent, "media.pause_music", {"lang": lang})
        return intent.reply or result
    if action == "next_track":
        result = await _call_tool(bridge, satellite_id, intent, "media.next_track", {"lang": lang})
        return intent.reply or result
    if action == "set_spotify_volume":
        result = await _call_tool(bridge, satellite_id, intent, "media.set_spotify_volume", {"value": value, "lang": lang})
        return intent.reply or result

    if action == "phone_sms":
        return await _call_tool(bridge, satellite_id, intent, "phone.send_sms", {"contact": target, "message": value})
    if action == "phone_ring":
        return await _call_tool(bridge, satellite_id, intent, "phone.ring_phone", {})
    if action == "phone_battery":
        return await _call_tool(bridge, satellite_id, intent, "phone.get_battery", {"lang": lang})
    if action == "phone_notify":
        return await _call_tool(bridge, satellite_id, intent, "phone.get_notifications", {"lang": lang})

    if action == "get_datetime":
        return await _call_tool(bridge, satellite_id, intent, "system.get_datetime", {"lang": lang})
    if action == "system_info":
        return await _call_tool(bridge, satellite_id, intent, "system.get_info", {"lang": lang})
    if action == "remember_fact":
        return await _call_tool(bridge, satellite_id, intent, "memory.store_fact", {"key": target, "value": value, "lang": lang})
    if action == "calculate":
        result = await _call_tool(bridge, satellite_id, intent, "system.calculate", {"value": value, "lang": lang})
        return intent.reply or result
    if action == "previous_track":
        result = await _call_tool(bridge, satellite_id, intent, "media.previous_track", {"lang": lang})
        return intent.reply or result
    if action == "toggle_bluetooth":
        result = await _call_tool(bridge, satellite_id, intent, "system.toggle_bluetooth", {"value": value, "lang": lang})
        return intent.reply or result

    if action == "chat":
        return intent.reply or ("I'm not sure how to help with that." if lang == "en" else "Не знаю, как помочь.")

    return intent.reply or ("Done." if lang == "en" else "Готово.")
