"""Assistant identity and invocation alias handling."""

from __future__ import annotations

from dataclasses import dataclass
import re

import config


_WORD_TRIM_RE = re.compile(r"(^[^\wа-яёА-ЯЁ]+)|([^\wа-яёА-ЯЁ]+$)")
_CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")


@dataclass(slots=True)
class Invocation:
    matched_alias: str | None
    remainder: str
    is_ping: bool


def detect_language(text: str) -> str:
    return "ru" if _CYRILLIC_RE.search(text) else "en"


def _normalize_word(word: str) -> str:
    return _WORD_TRIM_RE.sub("", word).casefold()


def _all_aliases() -> set[str]:
    return {
        *[a.casefold() for a in config.ASSISTANT_ALIASES_EN],
        *[a.casefold() for a in config.ASSISTANT_ALIASES_RU],
    }


def parse_invocation(text: str) -> Invocation:
    stripped = text.strip()
    if not stripped:
        return Invocation(matched_alias=None, remainder="", is_ping=False)

    parts = stripped.split(maxsplit=1)
    first_raw = parts[0]
    first = _normalize_word(first_raw)
    aliases = _all_aliases()

    if first and first in aliases:
        remainder = parts[1] if len(parts) > 1 else ""
        remainder = remainder.lstrip(" ,.:;!?-\t")
        return Invocation(matched_alias=first, remainder=remainder, is_ping=(remainder == ""))

    # Also support exact alias with trailing punctuation only, e.g. "Sasha?"
    norm_full = _normalize_word(stripped)
    if norm_full and norm_full in aliases:
        return Invocation(matched_alias=norm_full, remainder="", is_ping=True)

    return Invocation(matched_alias=None, remainder=stripped, is_ping=False)
