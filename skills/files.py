"""
skills/files.py
---------------
Filesystem awareness for Jarvis.

Lets you say:
  "open the vscode matugen template"
  "find my hyprland config"
  "open the project notes in obsidian"
  "show me files in my Downloads"
  "open ~/projects/jarvis"

How it works:
  1. The LLM extracts keywords and an optional app hint from your phrase
     e.g. "vscode matugen template" → keywords=["vscode","matugen","template"]
  2. We walk the filesystem index and score every file on how many
     keywords appear in its path components (directory names + filename)
  3. The best match is opened with xdg-open (respects your default apps)
     or with the specific app if one was mentioned

Search scope:
  - Home directory (~/), configurable depth
  - ~/.config always searched (shallow — 1 extra level)
  - ~/.local/share (shallow)
  - Common project roots: ~/projects, ~/dev, ~/code, ~/work, ~/src
  Heavy dirs are excluded to keep searches fast (see EXCLUDED_DIRS).

Performance:
  - Index is built lazily on first use, then cached for the session
  - Re-index is triggered if the index is older than INDEX_TTL seconds
"""

from __future__ import annotations

import os
import re
import time
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

import config

# ── Constants ─────────────────────────────────────────────────────────────────

HOME = Path.home()

# Dirs to skip entirely — they're huge and never contain useful files
EXCLUDED_DIRS: set[str] = {
    ".git", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".cache", ".cargo", ".rustup",
    ".npm", ".gradle", ".m2", "target", "vendor", ".wine",
    ".local/lib", ".local/share/Steam", ".steam",
    "snap", "flatpak",
}

# How deep to walk from HOME (deeper = slower but finds more)
HOME_MAX_DEPTH   = 5
CONFIG_MAX_DEPTH = 4   # ~/.config gets a little deeper

# Re-build the index if it's older than this (seconds)
INDEX_TTL = 120

# Extensions that are "openable" user files (skip binaries, object files etc.)
OPENABLE_EXTENSIONS: set[str] = {
    # Text / code
    ".txt", ".md", ".rst", ".org", ".log",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".sh", ".bash", ".zsh", ".fish",
    ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".java", ".rb",
    ".yaml", ".yml", ".toml", ".json", ".jsonc", ".ini", ".cfg",
    ".conf", ".config", ".env",
    # Documents
    ".pdf", ".docx", ".odt", ".xlsx", ".ods", ".pptx", ".odp",
    ".tex", ".bib",
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico",
    # Media
    ".mp3", ".flac", ".wav", ".ogg", ".mp4", ".mkv", ".webm", ".avi",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    # Misc
    ".onnx",   # AI models — useful to reference
    ".desktop", ".service",
}

# Extra search roots beyond HOME
EXTRA_ROOTS: list[Path] = [
    HOME / "projects",  HOME / "dev",     HOME / "code",
    HOME / "work",      HOME / "src",     HOME / "repos",
    HOME / ".config",   HOME / ".local" / "share",
]


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class FileEntry:
    path:   Path
    name:   str                     # filename without extension
    ext:    str                     # lowercase extension incl. dot
    parts:  list[str]               # all path components, lowercase
    score:  float = 0.0


# ── Index (module-level cache) ────────────────────────────────────────────────

_index:      list[FileEntry] = []
_index_time: float = 0.0


def _should_skip(p: Path) -> bool:
    """Return True if this path should be excluded from the index."""
    for part in p.parts:
        if part in EXCLUDED_DIRS:
            return True
        if part.startswith(".") and part not in (".config", ".local"):
            return True
    return False


def _walk_limited(root: Path, max_depth: int):
    """Yield files under root up to max_depth levels deep."""
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        depth = len(current.parts) - root_depth

        # Prune excluded dirs in-place so os.walk doesn't recurse into them
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDED_DIRS
            and not (d.startswith(".") and d not in (".config", ".local"))
        ]

        if depth >= max_depth:
            dirnames.clear()
            continue

        for fname in filenames:
            fpath = current / fname
            if not _should_skip(fpath):
                yield fpath


def build_index() -> list[FileEntry]:
    """Walk the filesystem and return a fresh index."""
    entries: list[FileEntry] = []
    seen: set[Path] = set()

    def _add_root(root: Path, depth: int):
        if not root.exists():
            return
        for fpath in _walk_limited(root, depth):
            if fpath in seen:
                continue
            seen.add(fpath)
            ext = fpath.suffix.lower()
            if ext not in OPENABLE_EXTENSIONS and ext != "":
                # Still index extensionless files (Makefile, Dockerfile, etc.)
                if "." in fpath.name:
                    continue
            parts = [p.lower() for p in fpath.parts]
            entries.append(FileEntry(
                path=fpath,
                name=fpath.stem.lower(),
                ext=ext,
                parts=parts,
            ))

    _add_root(HOME, HOME_MAX_DEPTH)
    for root in EXTRA_ROOTS:
        depth = CONFIG_MAX_DEPTH if ".config" in str(root) else HOME_MAX_DEPTH
        _add_root(root, depth)

    return entries


def get_index() -> list[FileEntry]:
    """Return cached index, rebuilding if stale."""
    global _index, _index_time
    now = time.time()
    if not _index or (now - _index_time) > INDEX_TTL:
        print("[files] Building filesystem index...")
        t = time.time()
        _index = build_index()
        _index_time = time.time()
        print(f"[files] Index built: {len(_index)} files in {time.time()-t:.1f}s")
    return _index


# ── Scoring ───────────────────────────────────────────────────────────────────

def _token_score(keyword: str, entry: FileEntry) -> float:
    """Score how well a single keyword matches this entry."""
    kw = keyword.lower().strip()
    best = 0.0

    # Exact substring in filename — highest value
    if kw in entry.name:
        best = max(best, 1.0 if kw == entry.name else 0.85)

    # Fuzzy match against filename
    ratio = SequenceMatcher(None, kw, entry.name).ratio()
    best = max(best, ratio * 0.8)

    # Substring in any path component
    for part in entry.parts:
        if kw in part:
            best = max(best, 0.7)
        ratio = SequenceMatcher(None, kw, part).ratio()
        best = max(best, ratio * 0.55)

    return best


def score_entry(keywords: list[str], entry: FileEntry) -> float:
    """
    Aggregate score across all keywords.
    All keywords must contribute something (AND logic) — missing a keyword
    hurts more than a partial match on another.
    """
    if not keywords:
        return 0.0

    scores = [_token_score(kw, entry) for kw in keywords]

    # Penalise heavily if any keyword scores zero — likely a wrong file
    if any(s < 0.15 for s in scores):
        return sum(scores) / len(scores) * 0.3

    # Bonus if multiple keywords all match well (tight cluster)
    mean = sum(scores) / len(scores)
    min_s = min(scores)
    return mean * 0.7 + min_s * 0.3


# ── Keyword extraction ────────────────────────────────────────────────────────

# Words to strip from file queries before scoring
_STOP_WORDS = {
    "open", "find", "show", "launch", "load", "get", "me", "my", "the",
    "a", "an", "file", "folder", "dir", "directory", "project", "config",
    "configuration", "template", "document", "doc", "script", "code",
    "in", "at", "of", "for", "with", "that", "this", "is", "are",
    # Russian
    "открой", "найди", "покажи", "запусти", "файл", "папку", "папка",
    "проект", "конфигурацию", "шаблон", "документ",
}


def extract_keywords(query: str) -> list[str]:
    """
    Extract meaningful search keywords from a natural language query.
    e.g. "open the vscode matugen template" → ["vscode", "matugen", "template"]
    """
    # Normalise separators
    tokens = re.split(r"[\s\-_/\.]+", query.lower())
    keywords = [t for t in tokens if t and t not in _STOP_WORDS and len(t) > 1]
    return keywords


def _detect_app_hint(query: str) -> Optional[str]:
    """
    If the user mentions an app, use it to open the file.
    e.g. "open in vscode" → "code"
         "edit in vim"    → "vim"
    """
    q = query.lower()
    hints = {
        "vscode": "code",   "code": "code",
        "vim":    "vim",    "nvim": "nvim",    "neovim": "nvim",
        "nano":   "nano",
        "kate":   "kate",   "gedit": "gedit",
        "obs":    "obsidian", "obsidian": "obsidian",
        "thunar": "thunar",   "dolphin": "dolphin", "nautilus": "nautilus",
        "vlc":    "vlc",
        "gimp":   "gimp",
        "inkscape": "inkscape",
    }
    # Check for "open with X" or "in X" pattern
    m = re.search(r"\b(?:in|with|using)\s+(\w+)", q)
    if m:
        word = m.group(1)
        if word in hints:
            return hints[word]

    # Also check if any hint word appears standalone in the query
    for word, exe in hints.items():
        if re.search(rf"\b{word}\b", q):
            return exe

    return None


# ── Search ────────────────────────────────────────────────────────────────────

def find_files(query: str, max_results: int = 5) -> list[FileEntry]:
    """
    Find files matching a natural language description.
    Returns up to max_results entries sorted by score descending.
    """
    keywords = extract_keywords(query)
    if not keywords:
        return []

    index = get_index()

    # Score all entries
    results: list[FileEntry] = []
    for entry in index:
        s = score_entry(keywords, entry)
        if s > 0.25:
            entry.score = s
            results.append(entry)

    results.sort(key=lambda e: -e.score)
    return results[:max_results]


# ── Open file ─────────────────────────────────────────────────────────────────

def open_path(path: Path, app: Optional[str] = None) -> str:
    """
    Open a file or directory. Uses the specified app or xdg-open.
    Returns a status message.
    """
    if not path.exists():
        return f"Path not found: {path}"

    try:
        if app and shutil.which(app):
            subprocess.Popen(
                [app, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Opened {path.name} with {app}."
        else:
            # xdg-open respects the user's default application associations
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Opened {path.name}."
    except Exception as e:
        return f"Failed to open {path.name}: {e}"


# ── Public skill functions ────────────────────────────────────────────────────

def find_and_open(query: str, lang: str = "en") -> str:
    """
    Main entry point: find the best matching file for a query and open it.
    Returns a spoken/display response string.
    """
    app_hint = _detect_app_hint(query)
    results  = find_files(query)

    if not results:
        if lang == "ru":
            return f"Не нашёл файл по запросу «{query}»."
        return f"No file found matching '{query}'."

    best = results[0]

    # If score is ambiguous, offer top choices
    if len(results) > 1 and results[1].score > best.score * 0.85:
        choices = "\n".join(
            f"  {i+1}. {r.path.relative_to(HOME)}"
            for i, r in enumerate(results[:3])
        )
        if lang == "ru":
            return f"Нашёл несколько файлов:\n{choices}\nОткрываю первый."
        msg = f"Found a few matches:\n{choices}\nOpening the closest one."
        # Still open the best one
        result_msg = open_path(best.path, app_hint)
        return f"{msg}\n{result_msg}"

    result = open_path(best.path, app_hint)
    rel_path = str(best.path.relative_to(HOME))

    if lang == "ru":
        return f"Открываю ~/{rel_path}."
    return f"Opening ~/{rel_path}."


def list_directory(path_str: str, lang: str = "en") -> str:
    """
    List files/dirs in a given path. Supports ~ and relative names.
    e.g. list_directory("Downloads") → contents of ~/Downloads
    """
    # Resolve path
    p = Path(path_str.replace("~", str(HOME))).expanduser()
    if not p.is_absolute():
        p = HOME / p

    if not p.exists():
        if lang == "ru":
            return f"Папка «{path_str}» не найдена."
        return f"Directory '{path_str}' not found."

    if not p.is_dir():
        return find_and_open(path_str, lang)

    try:
        items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        if not items:
            if lang == "ru":
                return f"Папка ~/{p.relative_to(HOME)} пуста."
            return f"~/{p.relative_to(HOME)} is empty."

        dirs  = [i.name + "/" for i in items if i.is_dir()][:10]
        files = [i.name      for i in items if i.is_file()][:15]
        all_items = dirs + files

        header = (f"Contents of ~/{p.relative_to(HOME)}:"
                  if p != HOME else "Home directory:")
        listing = "\n".join(f"  {item}" for item in all_items)

        if len(items) > 25:
            listing += f"\n  ... and {len(items)-25} more"

        return f"{header}\n{listing}"
    except PermissionError:
        return f"Permission denied reading {path_str}."


def search_files_by_name(pattern: str, lang: str = "en") -> str:
    """
    Find files whose name contains pattern (case-insensitive).
    Returns a formatted list.
    """
    pat = pattern.lower().strip()
    index = get_index()
    matches = [e for e in index if pat in e.name or pat in e.path.name.lower()]
    matches = matches[:10]

    if not matches:
        if lang == "ru":
            return f"Файлы с именем «{pattern}» не найдены."
        return f"No files found with '{pattern}' in the name."

    lines = [f"Files matching '{pattern}':"]
    for e in matches:
        try:
            rel = e.path.relative_to(HOME)
            lines.append(f"  ~/{rel}")
        except ValueError:
            lines.append(f"  {e.path}")

    return "\n".join(lines)


def get_file_info(query: str, lang: str = "en") -> str:
    """
    Find a file and return info about it (size, modified date, path).
    """
    results = find_files(query, max_results=1)
    if not results:
        if lang == "ru":
            return f"Файл «{query}» не найден."
        return f"File not found: {query}"

    p = results[0].path
    try:
        stat = p.stat()
        size_bytes = stat.st_size
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))

        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            size_str = f"{size_bytes/1024:.1f} KB"
        else:
            size_str = f"{size_bytes/1024**2:.1f} MB"

        rel = p.relative_to(HOME)
        if lang == "ru":
            return f"~/{rel}\nРазмер: {size_str} | Изменён: {mtime}"
        return f"~/{rel}\nSize: {size_str} | Modified: {mtime}"
    except Exception as e:
        return str(e)


def invalidate_index():
    """Force a fresh index on the next search."""
    global _index_time
    _index_time = 0.0
