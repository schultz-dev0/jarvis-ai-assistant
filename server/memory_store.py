"""Server-side memory store for VPS-hosted Brain state."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


MEMORY_ENABLED = os.environ.get("JARVIS_MEMORY_ENABLED", "true").lower() == "true"
MEMORY_MAX_INTERACTIONS = int(os.environ.get("JARVIS_MEMORY_MAX_INTERACTIONS", "2000"))
MEMORY_RETENTION_DAYS = int(os.environ.get("JARVIS_MEMORY_RETENTION_DAYS", "3650"))
MEMORY_INJECT_CONTEXT = os.environ.get("JARVIS_MEMORY_INJECT_CONTEXT", "true").lower() == "true"
MEMORY_FILE = Path(os.environ.get("JARVIS_MEMORY_FILE", str(Path.home() / ".local" / "share" / "jarvis" / "memory.json")))


def _blank_memory() -> dict:
    return {
        "app_usage": {},
        "preferred_location": "",
        "location_counts": {},
        "facts": {},
        "facts_meta": {},
        "corrections": {},
        "interactions": [],
        "schema_version": 2,
    }


def _load() -> dict:
    if MEMORY_FILE.exists():
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            return _migrate_schema(data)
        except Exception:
            pass
    return _blank_memory()


def _migrate_schema(data: dict) -> dict:
    base = _blank_memory()
    base.update(data if isinstance(data, dict) else {})

    now_ts = time.time()
    if not isinstance(base.get("facts"), dict):
        base["facts"] = {}
    if not isinstance(base.get("facts_meta"), dict):
        base["facts_meta"] = {}

    if int(base.get("schema_version") or 1) < 2:
        for key, value in base["facts"].items():
            k = str(key).strip().lower()
            if not k:
                continue
            base["facts_meta"][k] = {
                "value": str(value),
                "created_at": now_ts,
                "updated_at": now_ts,
                "source": "migration",
            }
        base["schema_version"] = 2

    if not isinstance(base.get("interactions"), list):
        base["interactions"] = []
    return base


def _save(data: dict):
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def get_context_hint(lang: str = "en") -> str:
    if not MEMORY_ENABLED or not MEMORY_INJECT_CONTEXT:
        return ""

    data = _load()
    hints: list[str] = []

    if data.get("preferred_location"):
        hints.append(
            f"User's usual weather city: {data['preferred_location']}"
            if lang == "en"
            else f"Обычный город для погоды: {data['preferred_location']}"
        )

    app_usage = data.get("app_usage", {})
    if app_usage:
        top = sorted(app_usage.items(), key=lambda x: -x[1])[:4]
        hints.append(
            ("Frequently used apps: " if lang == "en" else "Часто используемые приложения: ")
            + ", ".join(a for a, _ in top)
        )

    facts_meta = data.get("facts_meta", {})
    if isinstance(facts_meta, dict):
        recent_facts = sorted(
            [
                (k, v)
                for k, v in facts_meta.items()
                if isinstance(v, dict) and "value" in v
            ],
            key=lambda item: float(item[1].get("updated_at", 0.0)),
            reverse=True,
        )[:8]
        for key, meta in recent_facts:
            ts = float(meta.get("updated_at", 0.0))
            hints.append(f"{key}: {meta.get('value','')} (updated {_iso(ts) if ts else 'unknown-date'})")

    if not hints:
        return ""

    header = "MEMORY CONTEXT (VPS)" if lang == "en" else "КОНТЕКСТ ПАМЯТИ (VPS)"
    return header + "\n" + "\n".join(f"- {h}" for h in hints)


def record_interaction(
    user_input: str,
    action: str,
    target: str | None,
    result: str,
    success: bool,
    lang: str,
):
    if not MEMORY_ENABLED:
        return

    data = _load()

    if action == "open_app" and target:
        key = target.lower().strip()
        data["app_usage"][key] = data["app_usage"].get(key, 0) + 1

    if action == "get_weather" and target:
        loc = target.strip()
        data["location_counts"][loc] = data["location_counts"].get(loc, 0) + 1
        data["preferred_location"] = max(
            data["location_counts"], key=lambda k: data["location_counts"][k]
        )

    data["interactions"].append(
        {
            "ts": time.time(),
            "input": user_input,
            "action": action,
            "target": target,
            "result": result,
            "lang": lang,
            "success": success,
        }
    )
    cutoff = time.time() - (MEMORY_RETENTION_DAYS * 86400)
    data["interactions"] = [
        r for r in data["interactions"]
        if isinstance(r, dict) and float(r.get("ts", 0.0)) >= cutoff
    ]
    data["interactions"] = data["interactions"][-MEMORY_MAX_INTERACTIONS:]
    _save(data)
