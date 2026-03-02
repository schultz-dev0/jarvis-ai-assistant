"""
skills/web.py
-------------
Web capabilities: weather (wttr.in), news (DuckDuckGo search), web search.
No API keys required. News is fully query-driven — no hardcoded sources.

News flow:
  User: "news on Russia Ukraine negotiations"
    → get_news(topic="Russia Ukraine negotiations")
    → DDGS.news("Russia Ukraine negotiations") → live results from any source
    → summarise titles + sources back to user

  User: "what's in the news?" (no topic)
    → get_news(topic=None)
    → DDGS.news("latest world news today") → general headlines
"""

from __future__ import annotations

import re
import httpx
from datetime import datetime, timezone

import config

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
    )
}
TIMEOUT = 20.0


# ── Weather ───────────────────────────────────────────────────────────────────

def get_weather(location: str | None = None, lang: str = "en") -> str:
    """
    Fetch weather from wttr.in (no API key).
    location: city name extracted from the user prompt.
    """
    loc = location or config.WEATHER_LOCATION or ""

    if not loc:
        if lang == "ru":
            return (
                "Укажите город — например, 'погода в Москве'. "
                "Или задайте WEATHER_LOCATION в ~/.config/jarvis/settings.env."
            )
        return (
            "Please specify a city — e.g. 'weather in London'. "
            "Or set WEATHER_LOCATION in ~/.config/jarvis/settings.env."
        )

    display_name = loc
    query_loc    = loc.split(",")[0].strip()   # strip county/country suffix
    loc_path     = query_loc.replace(" ", "+")

    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(f"https://wttr.in/{loc_path}?format=j1")
            resp.raise_for_status()
            data = resp.json()

        current   = data["current_condition"][0]
        temp_c    = current["temp_C"]
        feels_c   = current["FeelsLikeC"]
        desc      = current["weatherDesc"][0]["value"]
        humidity  = current["humidity"]
        wind_kmph = current["windspeedKmph"]

        if lang == "ru":
            return (
                f"Погода в {display_name}: {desc}, {temp_c}°C, "
                f"ощущается как {feels_c}°C. "
                f"Влажность {humidity}%, ветер {wind_kmph} км/ч."
            )
        return (
            f"Weather in {display_name}: {desc}, {temp_c}°C, "
            f"feels like {feels_c}°C. "
            f"Humidity {humidity}%, wind {wind_kmph} km/h."
        )

    except Exception:
        return _weather_simple(query_loc, display_name, lang)


def _weather_simple(query_loc: str, display_name: str, lang: str = "en") -> str:
    """Fallback: wttr.in one-line format."""
    try:
        with httpx.Client(timeout=12.0, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(f"https://wttr.in/{query_loc.replace(' ', '+')}?format=3")
            resp.raise_for_status()
        text = re.sub(r"^[^:]+:", display_name + ":", resp.text.strip())
        return f"Погода: {text}" if lang == "ru" else text
    except Exception as e:
        return (
            f"Weather unavailable for {display_name}: {e}"
            if lang == "en"
            else f"Погода для {display_name} недоступна: {e}"
        )


# ── News — fully dynamic, query-driven ───────────────────────────────────────

def _ddgs_news(query: str, max_results: int = 6) -> list[dict]:
    """
    Search for news articles via duckduckgo_search.
    Returns a list of dicts with keys: title, body, source, url, date.
    Falls back to an empty list on any failure.
    """
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.news(
                keywords=query,
                region="wt-wt",       # worldwide
                safesearch="moderate",
                max_results=max_results,
            ))
        return results
    except ImportError:
        return []
    except Exception:
        return []


def _format_age(date_str: str | None) -> str:
    """Return a human-readable age string like '2h ago' or '3 days ago'."""
    if not date_str:
        return ""
    try:
        # DDGS returns ISO-format strings
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        secs = int(diff.total_seconds())
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return ""


def get_news(topic: str | None = None, lang: str = "en", max_items: int = 5) -> str:
    """
    Fetch news articles for any topic via DuckDuckGo News search.

    topic = None  → general headlines ("latest world news today")
    topic = str   → search that exact topic across all sources

    No hardcoded sources. Results come from wherever DuckDuckGo finds them.
    """
    # Build the search query
    if topic:
        query = topic.strip()
    else:
        # Generic "give me the news" — use today's top headlines query
        query = "breaking world news today"

    results = _ddgs_news(query, max_results=max_items + 2)  # fetch a couple extra in case of dupes

    if not results:
        # Last-ditch fallback: DuckDuckGo instant answer for the same query
        fallback = search_web(query, lang=lang)
        if lang == "ru":
            return f"Поиск новостей по «{topic or 'последние новости'}»:\n{fallback}"
        return f"News search for '{topic or 'latest news'}':\n{fallback}"

    # Deduplicate by title
    seen: set[str] = set()
    unique: list[dict] = []
    for r in results:
        key = r.get("title", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(r)
        if len(unique) >= max_items:
            break

    # Format output
    if lang == "ru":
        header = f"Новости по теме «{topic}»:" if topic else "Последние новости:"
    else:
        header = f"News on '{topic}':" if topic else "Latest headlines:"

    lines = [header]
    for i, r in enumerate(unique, 1):
        title  = r.get("title", "No title").strip()
        source = r.get("source", "").strip()
        age    = _format_age(r.get("date"))

        meta_parts = [p for p in [source, age] if p]
        meta = f"  [{', '.join(meta_parts)}]" if meta_parts else ""

        lines.append(f"{i}. {title}{meta}")

    return "\n".join(lines)


# ── Web search ────────────────────────────────────────────────────────────────

def search_web(query: str, lang: str = "en") -> str:
    """
    Web search via two strategies:
      1. DuckDuckGo Instant Answer API (structured, no key)
      2. duckduckgo_search text search as fallback (richer results)
    """
    if not query:
        return "What would you like me to search for?" if lang == "en" \
               else "Что искать?"

    # ── Strategy 1: DDG Instant Answer ───────────────────────────────────────
    try:
        with httpx.Client(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            )
            resp.raise_for_status()
            data = resp.json()

        answer = (
            data.get("Answer") or data.get("AbstractText") or data.get("Definition") or ""
        ).strip()
        answer = re.sub(r"<[^>]+>", "", answer).strip()

        if len(answer) > 40:   # substantial answer
            return answer

    except Exception:
        pass

    # ── Strategy 2: duckduckgo_search text search ─────────────────────────────
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(
                keywords=query,
                region="wt-wt",
                safesearch="moderate",
                max_results=3,
            ))

        if results:
            best = results[0]
            title = best.get("title", "")
            body  = best.get("body", "").strip()
            # Trim to a reasonable spoken length
            if len(body) > 400:
                body = body[:397] + "…"
            if body:
                return f"{title}: {body}" if title else body

    except Exception:
        pass

    return (
        f"No results found for '{query}'."
        if lang == "en"
        else f"Ничего не найдено по запросу '{query}'."
    )


# ── Time & Date ───────────────────────────────────────────────────────────────

def get_datetime(lang: str = "en") -> str:
    now = datetime.now()
    if lang == "ru":
        months = [
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря",
        ]
        return (
            f"Сейчас {now.strftime('%H:%M')}, "
            f"{now.day} {months[now.month - 1]} {now.year} года."
        )
    return now.strftime("It's %H:%M on %A, %B %d, %Y.")
