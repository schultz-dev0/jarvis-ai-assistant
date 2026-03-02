"""
skills/system.py
----------------
System control: volume, brightness, Wi-Fi, screenshots.
Uses pipewire (wpctl), brightnessctl, nmcli, grim+slurp.
"""

import subprocess
import shutil
from datetime import datetime
from pathlib import Path


# ── Volume ────────────────────────────────────────────────────────────────────

def set_volume(value: str) -> str:
    """
    value: "up", "down", "mute", "unmute", or an integer 0-100.
    Uses wpctl (pipewire). Falls back to pactl.
    """
    value = (value or "").strip().lower()
    if shutil.which("wpctl"):
        if value == "up":
            subprocess.run(["wpctl", "set-volume", "-l", "1.5", "@DEFAULT_AUDIO_SINK@", "5%+"])
            return "Volume increased."
        elif value == "down":
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"])
            return "Volume decreased."
        elif value in ("mute", "toggle"):
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
            return "Volume toggled."
        elif value == "unmute":
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
            return "Unmuted."
        else:
            try:
                pct = int(value.replace("%", ""))
                pct = max(0, min(150, pct))
                subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{pct}%"])
                return f"Volume set to {pct}%."
            except ValueError:
                return f"Didn't understand volume value '{value}'."
    else:
        return "wpctl not found. Is pipewire installed?"


def get_volume() -> str:
    """Return current volume as a string."""
    try:
        result = subprocess.run(
            ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
            capture_output=True, text=True
        )
        return result.stdout.strip()
    except Exception:
        return "Unknown"


# ── Brightness ────────────────────────────────────────────────────────────────

def set_brightness(value: str) -> str:
    """value: "up", "down", or integer 0-100."""
    value = (value or "").strip().lower()
    if not shutil.which("brightnessctl"):
        return "brightnessctl not found."

    if value == "up":
        subprocess.run(["brightnessctl", "set", "10%+"])
        return "Brightness increased."
    elif value == "down":
        subprocess.run(["brightnessctl", "set", "10%-"])
        return "Brightness decreased."
    else:
        try:
            pct = int(value.replace("%", ""))
            pct = max(1, min(100, pct))
            subprocess.run(["brightnessctl", "set", f"{pct}%"])
            return f"Brightness set to {pct}%."
        except ValueError:
            return f"Didn't understand brightness value '{value}'."


# ── Wi-Fi ─────────────────────────────────────────────────────────────────────

def toggle_wifi(value: str) -> str:
    """value: "on" or "off"."""
    value = (value or "").strip().lower()
    if not shutil.which("nmcli"):
        return "nmcli not found."
    if value == "on":
        subprocess.run(["nmcli", "radio", "wifi", "on"])
        return "Wi-Fi enabled."
    elif value == "off":
        subprocess.run(["nmcli", "radio", "wifi", "off"])
        return "Wi-Fi disabled."
    else:
        # Toggle
        result = subprocess.run(
            ["nmcli", "radio", "wifi"], capture_output=True, text=True
        )
        current = result.stdout.strip()
        new_state = "off" if current == "enabled" else "on"
        subprocess.run(["nmcli", "radio", "wifi", new_state])
        return f"Wi-Fi turned {new_state}."


# ── Screenshot ────────────────────────────────────────────────────────────────

def screenshot(mode: str = "region") -> str:
    """
    Take a screenshot using grim + slurp (Wayland/Hyprland standard).
    mode: "region" (select area) or "full" (entire screen).
    Saves to ~/Pictures/Screenshots/.
    """
    save_dir = Path.home() / "Pictures" / "Screenshots"
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    outfile = save_dir / f"screenshot_{timestamp}.png"

    if not shutil.which("grim"):
        return "grim not found. Install grim for screenshots."

    try:
        if mode == "full":
            subprocess.run(["grim", str(outfile)], check=True)
        else:
            if not shutil.which("slurp"):
                subprocess.run(["grim", str(outfile)], check=True)
            else:
                slurp = subprocess.run(["slurp"], capture_output=True, text=True, check=True)
                region = slurp.stdout.strip()
                subprocess.run(["grim", "-g", region, str(outfile)], check=True)

        # Copy to clipboard if wl-copy is available
        if shutil.which("wl-copy"):
            with open(outfile, "rb") as f:
                subprocess.run(["wl-copy", "--type", "image/png"], stdin=f)

        return f"Screenshot saved to {outfile.name}."
    except subprocess.CalledProcessError:
        return "Screenshot cancelled."
    except Exception as e:
        return f"Screenshot failed: {e}"


# ── System info ───────────────────────────────────────────────────────────────

def get_system_info() -> dict:
    """Return a dict of basic system info."""
    info = {}

    # CPU usage
    try:
        result = subprocess.run(
            ["top", "-bn1"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if "Cpu(s)" in line or "%Cpu" in line:
                info["cpu"] = line.strip()
                break
    except Exception:
        pass

    # Memory
    try:
        result = subprocess.run(["free", "-h"], capture_output=True, text=True)
        lines = result.stdout.splitlines()
        if len(lines) > 1:
            info["memory"] = lines[1]
    except Exception:
        pass

    # Uptime
    try:
        result = subprocess.run(["uptime", "-p"], capture_output=True, text=True)
        info["uptime"] = result.stdout.strip()
    except Exception:
        pass

    return info
