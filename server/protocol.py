"""Protocol primitives for Brain <-> Satellite JSON messaging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Any

PROTOCOL_VERSION = "1.0"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass(slots=True)
class Envelope:
    type: str
    payload: dict[str, Any]
    id: str | None = None
    ts: str | None = None
    protocol: str = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "id": self.id or new_id(),
            "ts": self.ts or iso_now(),
            "type": self.type,
            "payload": self.payload,
        }


def make_execute_action(
    tool: str,
    arguments: dict[str, Any],
    *,
    request_id: str | None = None,
    intent_action: str | None = None,
) -> dict[str, Any]:
    payload = {
        "tool": tool,
        "arguments": arguments,
    }
    if intent_action:
        payload["intent_action"] = intent_action
    return Envelope(
        type="brain.execute_action",
        payload=payload,
        id=request_id,
    ).to_dict()


def make_speak_text(text: str, lang: str = "en") -> dict[str, Any]:
    return Envelope(
        type="brain.speak_text",
        payload={"text": text, "language": lang},
    ).to_dict()


def make_ui_update(text: str, level: str = "info") -> dict[str, Any]:
    return Envelope(
        type="brain.ui_update",
        payload={"text": text, "level": level},
    ).to_dict()


def make_action_result(
    request_id: str,
    ok: bool,
    result: str,
    error: str | None = None,
) -> dict[str, Any]:
    payload = {"request_id": request_id, "ok": ok, "result": result}
    if error:
        payload["error"] = error
    return Envelope(type="satellite.action_result", payload=payload).to_dict()
