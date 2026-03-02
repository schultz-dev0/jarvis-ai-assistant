"""
skills/proactive.py
-------------------
Jarvis proactive awareness — runs in a background thread and pushes
notifications to both the desktop UI and connected mobile clients
without the user having to ask.

Checks:
  1. Phone battery (KDE Connect) — warns if < 20%
  2. Watched news topics (from memory) — checks for new headlines
  3. Calendar events (if ~/.local/share/jarvis/watched_events.json exists)
     or any .ics / vCard files detected in ~/

Usage:
  from skills.proactive import start_proactive_loop
  start_proactive_loop(push_fn)   # push_fn(text, lang) displays in UI

The push_fn should be thread-safe (use GLib.idle_add on GTK side).
"""

from __future__ import annotations

import threading
import time
import json
from pathlib import Path
from typing import Callable
from datetime import datetime

import config

# How often to run each check (seconds)
BATTERY_INTERVAL      = 300    # 5 min
NEWS_WATCH_INTERVAL   = 1800   # 30 min
CALENDAR_INTERVAL     = 600    # 10 min

# Battery threshold to warn at
BATTERY_WARN_THRESHOLD = 20    # percent

# File that stores news topics to watch (auto-managed via memory)
WATCHED_TOPICS_FILE = config.JARVIS_DATA_DIR / "watched_topics.json"


# ── State tracking (avoid duplicate notifications) ───────────────────────────

_last_battery_warned:  float = 0.0
_last_news_headlines:  dict[str, set[str]] = {}   # topic → set of seen titles
_last_calendar_events: set[str] = set()
_push_fn: Callable[[str, str], None] | None = None


def _push(text: str, lang: str = "en"):
    if _push_fn:
        try:
            _push_fn(text, lang)
        except Exception as e:
            print(f"[proactive] push error: {e}")

    # Also broadcast to mobile
    try:
        from mobile_server import broadcast_message
        broadcast_message(f"📬 {text}")
    except Exception:
        pass


# ── Battery check ─────────────────────────────────────────────────────────────

def _check_battery():
    global _last_battery_warned
    try:
        from skills.phone import get_battery, _check_available
        ok, device = _check_available()
        if not ok:
            return

        import subprocess
        result = subprocess.run(
            ["kdeconnect-cli", "--device", device, "--battery"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip()
        # Parse percentage from output like "Battery: 15%"
        import re
        m = re.search(r"(\d+)\s*%", output)
        if m:
            pct = int(m.group(1))
            now = time.time()
            if pct < BATTERY_WARN_THRESHOLD and (now - _last_battery_warned) > 3600:
                _last_battery_warned = now
                _push(
                    f"⚡ Phone battery is low: {pct}%. Consider charging."
                )

    except Exception as e:
        print(f"[proactive] battery check error: {e}")


# ── News watch ────────────────────────────────────────────────────────────────

def _load_watched_topics() -> list[str]:
    """Load news topics to watch from memory and/or watched_topics.json."""
    topics: list[str] = []

    # From watched_topics.json (manually curated or added via "watch X" command)
    if WATCHED_TOPICS_FILE.exists():
        try:
            data = json.loads(WATCHED_TOPICS_FILE.read_text(encoding="utf-8"))
            topics.extend(data.get("topics", []))
        except Exception:
            pass

    # From memory — any topics the user has asked about recently
    try:
        from skills.memory import _load as load_memory
        mem = load_memory()
        recent = mem.get("interactions", [])
        for r in reversed(recent[-20:]):
            if r.get("action") == "get_news" and r.get("target"):
                t = r["target"]
                if t and t not in topics:
                    topics.append(t)
                if len(topics) >= 5:
                    break
    except Exception:
        pass

    return topics[:5]   # cap at 5 watched topics


def add_watched_topic(topic: str):
    """Add a topic to the watch list (persisted)."""
    WATCHED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {"topics": []}
    if WATCHED_TOPICS_FILE.exists():
        try:
            data = json.loads(WATCHED_TOPICS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    if topic not in data["topics"]:
        data["topics"].append(topic)
        data["topics"] = data["topics"][-10:]
    WATCHED_TOPICS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _check_news():
    global _last_news_headlines
    topics = _load_watched_topics()
    if not topics:
        return

    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return

    for topic in topics:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.news(
                    keywords=topic,
                    region="wt-wt",
                    max_results=3,
                ))

            if not results:
                continue

            seen = _last_news_headlines.get(topic, set())
            new_items = [
                r for r in results
                if r.get("title", "").lower().strip() not in seen
            ]

            if not new_items:
                continue

            # Update seen set
            _last_news_headlines[topic] = seen | {
                r.get("title", "").lower().strip() for r in results
            }

            # Only push if we have genuinely new headlines
            # (skip on first run to avoid spamming on startup)
            if seen:
                lines = [f"📰 New on '{topic}':"]
                for r in new_items[:2]:
                    title  = r.get("title", "")
                    source = r.get("source", "")
                    lines.append(f"  • {title}  [{source}]" if source else f"  • {title}")
                _push("\n".join(lines))

            time.sleep(2)   # be polite to DDG

        except Exception as e:
            print(f"[proactive] news watch error for '{topic}': {e}")


# ── Calendar check ────────────────────────────────────────────────────────────

def _check_calendar():
    """
    Scan for .ics files in ~/  and emit reminders for events happening today
    or within the next hour that haven't been announced yet.
    """
    global _last_calendar_events
    ics_files: list[Path] = []

    # Check common locations
    for candidate in [
        Path.home() / "calendar.ics",
        Path.home() / "Calendar",
        Path.home() / "Documents",
        Path.home() / ".local" / "share" / "gnome-calendar",
        Path.home() / ".local" / "share" / "evolution" / "calendar",
    ]:
        if candidate.is_file() and candidate.suffix == ".ics":
            ics_files.append(candidate)
        elif candidate.is_dir():
            ics_files.extend(candidate.rglob("*.ics"))

    if not ics_files:
        return

    try:
        # Try python-icalendar if available
        import icalendar
        from datetime import timezone, timedelta
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(hours=1)

        for ics_path in ics_files[:3]:
            try:
                cal = icalendar.Calendar.from_ical(ics_path.read_bytes())
                for component in cal.walk():
                    if component.name != "VEVENT":
                        continue
                    summary = str(component.get("SUMMARY", ""))
                    dtstart = component.get("DTSTART")
                    if not dtstart:
                        continue
                    dt = dtstart.dt
                    # Make timezone-aware if naive
                    if not hasattr(dt, "tzinfo") or dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    # Make datetime from date
                    if not isinstance(dt, datetime):
                        from datetime import datetime as _dt
                        dt = _dt.combine(dt, _dt.min.time(), tzinfo=timezone.utc)

                    event_key = f"{summary}|{dt.isoformat()}"
                    if now <= dt <= window_end and event_key not in _last_calendar_events:
                        _last_calendar_events.add(event_key)
                        mins = int((dt - now).total_seconds() / 60)
                        if mins <= 5:
                            _push(f"📅 Upcoming now: {summary}")
                        else:
                            _push(f"📅 In {mins} min: {summary}")
            except Exception:
                pass

    except ImportError:
        pass   # icalendar not installed — silently skip


# ── Conversation history awareness ────────────────────────────────────────────

def _check_reminders():
    """
    Check if the user stored any time-based reminders in memory.
    e.g. after "remind me to call Alice at 3pm"
    """
    try:
        from skills.memory import _load as load_memory
        mem = load_memory()
        facts = mem.get("facts", {})
        now = datetime.now()

        for key, value in facts.items():
            if not key.startswith("reminder_"):
                continue
            # Value format: "YYYY-MM-DD HH:MM|message"
            parts = value.split("|", 1)
            if len(parts) != 2:
                continue
            try:
                remind_time = datetime.strptime(parts[0].strip(), "%Y-%m-%d %H:%M")
                message     = parts[1].strip()
                diff = (remind_time - now).total_seconds()
                if -60 <= diff <= 300:   # within -1 to +5 minutes
                    _push(f"⏰ Reminder: {message}")
            except Exception:
                pass
    except Exception:
        pass


# ── Main loop ─────────────────────────────────────────────────────────────────

def _proactive_loop():
    """Background thread that runs checks on staggered intervals."""
    # Stagger startup so we don't hammer everything at once
    time.sleep(30)

    last_battery  = 0.0
    last_news     = 0.0
    last_calendar = 0.0
    last_reminder = 0.0

    print("[proactive] Background awareness loop started")

    while True:
        now = time.time()

        try:
            if now - last_battery >= BATTERY_INTERVAL:
                _check_battery()
                last_battery = now

            if now - last_news >= NEWS_WATCH_INTERVAL:
                _check_news()
                last_news = now

            if now - last_calendar >= CALENDAR_INTERVAL:
                _check_calendar()
                last_calendar = now

            if now - last_reminder >= 60:
                _check_reminders()
                last_reminder = now

        except Exception as e:
            print(f"[proactive] loop error: {e}")

        time.sleep(30)


def start_proactive_loop(push_fn: Callable[[str, str], None]):
    """
    Start the proactive background thread.
    push_fn(text, lang) will be called when Jarvis has something to say.
    """
    global _push_fn
    _push_fn = push_fn

    t = threading.Thread(target=_proactive_loop, daemon=True, name="jarvis-proactive")
    t.start()
