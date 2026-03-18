"""Local Satellite agent that dials out to the VPS Brain over WebSocket."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import websockets

from satellite_executor import execute_tool, list_tools
from server.protocol import Envelope, make_action_result, new_id
import config


SATELLITE_ID = os.environ.get("JARVIS_SATELLITE_ID", "basildon-main")
DEFAULT_BRIDGE = f"ws://127.0.0.1:8765/ws/satellite/{SATELLITE_ID}"
BRIDGE_URL = os.environ.get("JARVIS_BRIDGE_URL", DEFAULT_BRIDGE)
_bridge_token = config.SASHA_BRIDGE_TOKEN
if _bridge_token:
    _sep = "&" if "?" in BRIDGE_URL else "?"
    BRIDGE_URL = f"{BRIDGE_URL}{_sep}token={_bridge_token}"
RECONNECT_DELAY = float(os.environ.get("JARVIS_RECONNECT_DELAY", "3"))


def _status_payload() -> dict:
    return {
        "satellite_id": SATELLITE_ID,
        "hostname": os.uname().nodename,
        "cwd": str(Path.cwd()),
        "capabilities": {
            "tools": list_tools(),
            "audio_input": True,
            "audio_output": True,
            "ui": True,
        },
    }


async def _send_json(ws, message: dict):
    await ws.send(json.dumps(message))


async def _send_hello(ws):
    hello = Envelope(type="satellite.hello", payload=_status_payload()).to_dict()
    await _send_json(ws, hello)


async def _handle_execute_action(ws, message: dict):
    payload = message.get("payload") or {}
    request_id = message.get("id") or new_id()
    tool = payload.get("tool")
    args = payload.get("arguments") or {}
    try:
        result = execute_tool(str(tool), args)
        response = make_action_result(request_id=request_id, ok=True, result=result)
    except Exception as exc:
        response = make_action_result(request_id=request_id, ok=False, result="", error=str(exc))
    await _send_json(ws, response)


async def _handle_message(ws, raw: str):
    msg = json.loads(raw)
    msg_type = msg.get("type")

    if msg_type == "brain.execute_action":
        await _handle_execute_action(ws, msg)
        return

    if msg_type == "brain.speak_text":
        payload = msg.get("payload") or {}
        text = str(payload.get("text") or "")
        if text:
            try:
                import tts

                tts.speak(text)
            except Exception:
                pass
            print(f"[satellite:speak] {text}")
        return

    if msg_type == "brain.ui_update":
        payload = msg.get("payload") or {}
        print(f"[satellite:ui] {payload.get('text', '')}")
        return

    if msg_type == "brain.ping":
        pong = Envelope(type="satellite.status", payload=_status_payload()).to_dict()
        await _send_json(ws, pong)


async def run_satellite_forever():
    while True:
        try:
            async with websockets.connect(BRIDGE_URL, ping_interval=20, ping_timeout=20) as ws:
                print(f"[satellite] connected -> {BRIDGE_URL}")
                await _send_hello(ws)
                async for raw in ws:
                    await _handle_message(ws, raw)
        except Exception as exc:
            print(f"[satellite] disconnected: {exc}")
            await asyncio.sleep(RECONNECT_DELAY)


def main():
    asyncio.run(run_satellite_forever())


if __name__ == "__main__":
    main()
