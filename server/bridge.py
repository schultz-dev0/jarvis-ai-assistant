"""WebSocket bridge where Satellites dial out to the VPS Brain."""

from __future__ import annotations

import asyncio
from collections import defaultdict
import json
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect

from server import brain
from server.dispatcher import dispatch_intent
from server.memory_store import record_interaction
from server.protocol import make_speak_text, make_ui_update, new_id
import config


class SatelliteBridge:
    def __init__(self):
        self._sockets: dict[str, WebSocket] = {}
        self._pending: dict[str, asyncio.Future] = {}
        self._history: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def register(self, satellite_id: str, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._sockets[satellite_id] = ws

    async def unregister(self, satellite_id: str):
        async with self._lock:
            self._sockets.pop(satellite_id, None)

    async def send(self, satellite_id: str, message: dict[str, Any]):
        ws = self._sockets.get(satellite_id)
        if ws is None:
            raise RuntimeError(f"Satellite '{satellite_id}' is not connected")
        await ws.send_text(json.dumps(message))

    async def request_action(
        self,
        satellite_id: str,
        message: dict[str, Any],
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        request_id = message["id"]
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future
        await self.send(satellite_id, message)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    async def on_message(self, satellite_id: str, message: dict[str, Any]):
        msg_type = message.get("type")
        payload = message.get("payload") or {}

        if msg_type == "satellite.action_result":
            request_id = payload.get("request_id")
            if request_id and request_id in self._pending and not self._pending[request_id].done():
                self._pending[request_id].set_result(message)
            return

        if msg_type == "satellite.input_text":
            text = str(payload.get("text") or "").strip()
            if not text:
                return
            result_text = await self._process_input_text(satellite_id, text)
            await self.send(satellite_id, make_speak_text(result_text, payload.get("language") or "en"))
            await self.send(satellite_id, make_ui_update(result_text, level="assistant"))
            return

    async def _process_input_text(self, satellite_id: str, text: str) -> str:
        hist = self._history[satellite_id]
        hist.append(("user", text))
        hist[:] = hist[-12:]

        intent = brain.parse_intent(text, history=hist[:-1])
        result = await dispatch_intent(intent, self, satellite_id, raw_input=text)

        hist.append(("assistant", result))
        hist[:] = hist[-12:]

        record_interaction(
            user_input=text,
            action=intent.action,
            target=intent.target,
            result=result,
            success=True,
            lang=intent.language,
        )
        return result


bridge = SatelliteBridge()
app = FastAPI(title="Sasha Brain Bridge", version="1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "connected_satellites": list(bridge._sockets.keys()),
        "backend": brain.get_active_backend(),
    }


@app.post("/ingest/text/{satellite_id}")
async def ingest_text(satellite_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if satellite_id not in bridge._sockets:
        raise HTTPException(status_code=404, detail="Satellite not connected")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing text")
    result = await bridge._process_input_text(satellite_id, text)
    return {"ok": True, "result": result}


@app.websocket("/ws/satellite/{satellite_id}")
async def ws_satellite(ws: WebSocket, satellite_id: str, token: str = Query(default="")):
    expected = config.SASHA_BRIDGE_TOKEN
    if expected and token != expected:
        await ws.accept()
        await ws.close(code=4003)
        return
    await bridge.register(satellite_id, ws)
    await bridge.send(
        satellite_id,
        {
            "id": new_id(),
            "type": "brain.ui_update",
            "payload": {"text": "Connected to VPS Brain", "level": "system"},
        },
    )
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            await bridge.on_message(satellite_id, msg)
    except WebSocketDisconnect:
        await bridge.unregister(satellite_id)
