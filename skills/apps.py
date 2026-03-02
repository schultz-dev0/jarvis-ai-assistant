"""
skills/apps.py
--------------
Open, close, and focus applications via hyprctl (Hyprland).
Uses fuzzy name matching so "spotify" finds "com.spotify.client", etc.
"""

import subprocess
import json
import shutil
from difflib import get_close_matches

# ── App alias map ─────────────────────────────────────────────────────────────
# Maps friendly names → actual executable / desktop app name
APP_ALIASES: dict[str, str] = {
    "spotify":     "spotify",
    "firefox":     "firefox",
    "chrome":      "google-chrome-stable",
    "chromium":    "chromium",
    "terminal":    "kitty",           # change to your terminal
    "kitty":       "kitty",
    "alacritty":   "alacritty",
    "files":       "nautilus",
    "file manager":"nautilus",
    "code":        "code",
    "vscode":      "code",
    "discord":     "discord",
    "telegram":    "telegram-desktop",
    "vlc":         "vlc",
    "steam":       "steam",
    "settings":    "gnome-control-center",
    "calculator":  "gnome-calculator",
    "text editor": "gedit",
    "thunar":      "thunar",
    "dolphin":     "dolphin",
    "obsidian":    "obsidian",
}

# Russian alias map
APP_ALIASES_RU: dict[str, str] = {
    "спотифай":    "spotify",
    "браузер":     "firefox",
    "терминал":    "kitty",
    "дискорд":     "discord",
    "телеграм":    "telegram-desktop",
    "стим":        "steam",
    "файлы":       "nautilus",
}


def _resolve_app(name: str) -> str:
    """Resolve fuzzy app name to executable."""
    if not name:
        return name
    low = name.lower().strip()

    # Check RU aliases first
    if low in APP_ALIASES_RU:
        low = APP_ALIASES_RU[low]

    # Exact match
    if low in APP_ALIASES:
        return APP_ALIASES[low]

    # Fuzzy match
    matches = get_close_matches(low, APP_ALIASES.keys(), n=1, cutoff=0.6)
    if matches:
        return APP_ALIASES[matches[0]]

    # Return as-is — maybe it's already the binary name
    return low


def open_app(target: str) -> str:
    """Launch an application. Returns status message."""
    exe = _resolve_app(target)
    if not exe:
        return f"I don't know how to open '{target}'."

    if not shutil.which(exe):
        return f"'{exe}' doesn't appear to be installed."

    try:
        subprocess.Popen(
            ["hyprctl", "dispatch", "exec", exe],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Opened {target}."
    except FileNotFoundError:
        # Fallback if hyprctl not available (e.g. testing outside Hyprland)
        subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Launched {target}."


def close_app(target: str) -> str:
    """Close windows matching the app name via hyprctl."""
    exe = _resolve_app(target)
    try:
        # Get all windows
        result = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True
        )
        clients = json.loads(result.stdout)
        closed = 0
        for client in clients:
            class_name = client.get("class", "").lower()
            title = client.get("title", "").lower()
            if exe.lower() in class_name or exe.lower() in title:
                addr = client["address"]
                subprocess.run(["hyprctl", "dispatch", "closewindow", f"address:{addr}"],
                               capture_output=True)
                closed += 1
        if closed:
            return f"Closed {closed} window(s) of {target}."
        return f"No open windows found for {target}."
    except Exception as e:
        return f"Error closing {target}: {e}"


def focus_app(target: str) -> str:
    """Bring app window to focus."""
    exe = _resolve_app(target)
    try:
        subprocess.run(
            ["hyprctl", "dispatch", "focuswindow", f"class:{exe}"],
            capture_output=True
        )
        return f"Focused {target}."
    except Exception as e:
        return f"Error focusing {target}: {e}"


def list_open_apps() -> list[str]:
    """Return list of currently open app class names."""
    try:
        result = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True
        )
        clients = json.loads(result.stdout)
        return [c.get("class", "") for c in clients if c.get("class")]
    except Exception:
        return []
