"""
skills/memory.py
----------------
Sasha learning and memory system.

Remembers:
  - App usage frequency (learns your most-used apps)
  - Preferred weather location (auto-fills blank weather queries)
  - Correction history (if you re-phrase a command, it learns the better phrasing)
  - Named facts ("my name is Alex", "I work at 9am")
  - Last N interactions for context

Memory is stored as JSON in ~/.local/share/jarvis/memory.json.
Context hints are injected into LLM system prompts automatically.
"""

from __future__ import annotations

import json
import time
import re
from datetime import datetime, timezone

import config

# ── Internal helpers ──────────────────────────────────────────────────────────

def _load() -> dict:
    if config.MEMORY_FILE.exists():
        try:
            data = json.loads(config.MEMORY_FILE.read_text(encoding="utf-8"))
            return _migrate_schema(data)
        except Exception:
            pass
    return _blank_memory()


def _blank_memory() -> dict:
    return {
        "app_usage":           {},   # app_name → count
        "preferred_location":  "",   # last / most-used weather city
        "location_counts":     {},   # city → count
        "facts":               {},   # arbitrary user facts
        "facts_meta":          {},   # fact_key -> {value, created_at, updated_at, source}
        "corrections":         {},   # original_text → corrected_text
        "interactions":        [],   # last N full interaction records
        "schema_version":      2,
    }


def _migrate_schema(data: dict) -> dict:
    base = _blank_memory()
    base.update(data if isinstance(data, dict) else {})

    schema = int(base.get("schema_version") or 1)
    now_ts = time.time()

    if not isinstance(base.get("facts"), dict):
        base["facts"] = {}
    if not isinstance(base.get("facts_meta"), dict):
        base["facts_meta"] = {}

    if schema < 2:
        # Backfill metadata for existing facts so freshest memory can be ranked.
        for key, value in base["facts"].items():
            norm_key = str(key).strip().lower()
            if not norm_key:
                continue
            base["facts_meta"][norm_key] = {
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
    config.MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.MEMORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _upsert_fact(data: dict, key: str, value: str, source: str = "manual"):
    now_ts = time.time()
    norm_key = key.strip().lower()
    if not norm_key:
        return

    data["facts"][norm_key] = value.strip()

    facts_meta = data.setdefault("facts_meta", {})
    prev = facts_meta.get(norm_key)
    created_at = prev.get("created_at", now_ts) if isinstance(prev, dict) else now_ts
    facts_meta[norm_key] = {
        "value": value.strip(),
        "created_at": created_at,
        "updated_at": now_ts,
        "source": source,
    }


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


# ── Public API ────────────────────────────────────────────────────────────────

def record_interaction(
    user_input: str,
    action:     str,
    target:     str | None,
    result:     str,
    success:    bool = True,
    lang:       str  = "en",
):
    """
    Call this after every dispatched command so Jarvis can learn from it.
    Automatically updates usage counters, preferred locations, etc.
    """
    if not config.MEMORY_ENABLED:
        return

    data = _load()

    # ── App usage ─────────────────────────────────────────────────────────────
    if action == "open_app" and target:
        key = target.lower().strip()
        data["app_usage"][key] = data["app_usage"].get(key, 0) + 1

    # ── Preferred weather location ─────────────────────────────────────────────
    if action == "get_weather" and target:
        loc = target.strip()
        data["location_counts"][loc] = data["location_counts"].get(loc, 0) + 1
        # Most-used location becomes the preferred default
        data["preferred_location"] = max(
            data["location_counts"], key=lambda k: data["location_counts"][k]
        )

    # ── Interaction log ────────────────────────────────────────────────────────
    record = {
        "ts":      time.time(),
        "input":   user_input,
        "action":  action,
        "target":  target,
        "result":  result,
        "lang":    lang,
        "success": success,
    }
    data["interactions"].append(record)

    # Trim by retention window first, then by count cap.
    cutoff = time.time() - (config.MEMORY_RETENTION_DAYS * 86400)
    data["interactions"] = [
        r for r in data["interactions"]
        if isinstance(r, dict) and float(r.get("ts", 0.0)) >= cutoff
    ]

    # Trim to max rolling limit
    data["interactions"] = data["interactions"][-config.MEMORY_MAX_INTERACTIONS:]

    _save(data)


def store_fact(key: str, value: str):
    """
    Store an arbitrary user fact.
    e.g. store_fact("user_name", "Alex")
         store_fact("work_start", "9am")
    These are injected into LLM context hints.
    """
    data = _load()
    _upsert_fact(data, key, value, source="manual")
    _save(data)


def store_correction(original: str, corrected: str):
    """
    Record when the user re-phrases a failed command.
    Helps the LLM get it right next time via context injection.
    """
    data = _load()
    data["corrections"][original.lower().strip()] = corrected.strip()
    _save(data)


def get_context_hint(lang: str = "en") -> str:
    """
    Build a short memory context string to prepend to LLM system prompts.
    Stays concise — only the most useful facts.
    """
    if not config.MEMORY_INJECT_CONTEXT:
        return ""

    data = _load()
    hints: list[str] = []

    # Preferred weather location
    if data.get("preferred_location"):
        if lang == "ru":
            hints.append(f"Обычный город для погоды: {data['preferred_location']}")
        else:
            hints.append(f"User's usual weather city: {data['preferred_location']}")

    # Top apps
    app_usage = data.get("app_usage", {})
    if app_usage:
        top = sorted(app_usage.items(), key=lambda x: -x[1])[:4]
        app_str = ", ".join(a for a, _ in top)
        if lang == "ru":
            hints.append(f"Часто используемые приложения: {app_str}")
        else:
            hints.append(f"Frequently used apps: {app_str}")

    # Most recently updated facts with date stamps.
    facts_meta = data.get("facts_meta", {})
    if isinstance(facts_meta, dict) and facts_meta:
        recent_facts = sorted(
            [
                (k, v)
                for k, v in facts_meta.items()
                if isinstance(v, dict) and "value" in v
            ],
            key=lambda item: float(item[1].get("updated_at", 0.0)),
            reverse=True,
        )[:config.MEMORY_RECENT_FACTS_LIMIT]
        for key, meta in recent_facts:
            ts = float(meta.get("updated_at", 0.0))
            stamp = _iso(ts) if ts > 0 else "unknown-date"
            hints.append(f"{key}: {meta.get('value','')} (updated {stamp})")

    if not hints:
        return ""

    header = "MEMORY CONTEXT (use this to personalise replies):" if lang == "en" \
             else "КОНТЕКСТ ПАМЯТИ (используй для персонализации):"
    return header + "\n" + "\n".join(f"- {h}" for h in hints)


def get_top_apps(n: int = 5) -> list[str]:
    """Return the n most-used app names."""
    data = _load()
    sorted_apps = sorted(data.get("app_usage", {}).items(), key=lambda x: -x[1])
    return [a for a, _ in sorted_apps[:n]]


def get_recent_facts(n: int = 8) -> list[tuple[str, str, float]]:
    """Return freshest facts as (key, value, updated_ts), newest first."""
    data = _load()
    facts_meta = data.get("facts_meta", {})
    if not isinstance(facts_meta, dict):
        return []

    recent = sorted(
        [
            (k, v)
            for k, v in facts_meta.items()
            if isinstance(v, dict) and "value" in v
        ],
        key=lambda item: float(item[1].get("updated_at", 0.0)),
        reverse=True,
    )[:n]
    return [
        (key, str(meta.get("value", "")), float(meta.get("updated_at", 0.0)))
        for key, meta in recent
    ]


def get_preferred_location() -> str:
    """Return the user's most-used weather location, or empty string."""
    return _load().get("preferred_location", "")


def extract_and_store_facts(user_input: str, lang: str = "en"):
    """
    Detect self-disclosure patterns in natural language and auto-store them.
    e.g. "my name is Alex" → store_fact("user_name", "Alex")
         "I live in Manchester" → store_fact("user_city", "Manchester")
    """
    text = user_input.strip()

    patterns_en = [
        (r"my name is ([A-Z][a-z]+)", "user_name"),
        (r"i(?:'m| am) called ([A-Z][a-z]+)", "user_name"),
        (r"i live in ([A-Za-z ]+?)(?:\.|,|$)", "user_city"),
        (r"i(?:'m| am) from ([A-Za-z ]+?)(?:\.|,|$)", "user_city"),
        (r"i work (?:at|for) ([A-Za-z ]+?)(?:\.|,|$)", "user_employer"),
        (r"i wake up at ([\d:apm ]+)", "wake_time"),
        (r"i go to (?:bed|sleep) at ([\d:apm ]+)", "sleep_time"),
    ]

    patterns_ru = [
        (r"меня зовут ([А-ЯЁ][а-яё]+)", "user_name"),
        (r"я живу в ([А-ЯЁ][а-яё ]+?)(?:\.|,|$)", "user_city"),
        (r"я из ([А-ЯЁ][а-яё ]+?)(?:\.|,|$)", "user_city"),
    ]

    patterns = patterns_ru if lang == "ru" else patterns_en
    for pattern, fact_key in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            data = _load()
            _upsert_fact(data, fact_key, m.group(1).strip(), source="auto-extract")
            _save(data)


def get_recent_summary(n: int = 5, lang: str = "en") -> str:
    """Return a readable summary of the last n interactions."""
    data = _load()
    recent = data.get("interactions", [])[-n:]
    if not recent:
        return "No recent interactions." if lang == "en" else "Нет недавних взаимодействий."

    lines = []
    for r in reversed(recent):
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["ts"]))
        lines.append(f"  {ts}  {r['action']}({r.get('target','')})  ← \"{r['input'][:40]}\"")

    header = "Recent history:" if lang == "en" else "Недавние команды:"
    return header + "\n" + "\n".join(lines)


def wipe_memory():
    """Reset all memory. Irreversible."""
    _save(_blank_memory())
