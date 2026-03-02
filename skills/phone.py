"""
skills/phone.py
---------------
Phone integration via KDE Connect (kdeconnect-cli).
Supports: SMS, ring, battery check, notification list.
Install: sudo pacman -S kdeconnect
Pair via KDE Connect app on Android + kdeconnect-app on desktop.
"""

import subprocess
import shutil
import json
import re

import config


# ── Device detection ──────────────────────────────────────────────────────────

def _get_device_id() -> str | None:
    """Return the configured or auto-detected device ID."""
    if config.KDECONNECT_DEVICE:
        return config.KDECONNECT_DEVICE

    if not shutil.which("kdeconnect-cli"):
        return None

    try:
        result = subprocess.run(
            ["kdeconnect-cli", "--list-available", "--id-only"],
            capture_output=True, text=True, timeout=5
        )
        ids = result.stdout.strip().splitlines()
        if ids:
            return ids[0]
    except Exception:
        pass

    return None


def _check_available() -> tuple[bool, str]:
    """Returns (available, device_id_or_error)."""
    if not shutil.which("kdeconnect-cli"):
        return False, "kdeconnect-cli not found. Install with: sudo pacman -S kdeconnect"
    device_id = _get_device_id()
    if not device_id:
        return False, "No paired phone found. Pair your phone via KDE Connect first."
    return True, device_id


# ── SMS ───────────────────────────────────────────────────────────────────────

def send_sms(contact: str, message: str) -> str:
    """
    Send an SMS. contact can be a name or phone number.
    Note: kdeconnect-cli requires a phone number; name resolution would need
    a contacts database. For now we accept numbers directly.
    """
    ok, device_or_err = _check_available()
    if not ok:
        return device_or_err

    if not message:
        return "No message text provided."

    # If contact looks like a name (not a number), let the user know
    if not re.match(r"^[\d\+\-\s\(\)]+$", contact):
        return (
            f"I need a phone number to send an SMS. "
            f"I don't have a contacts list to look up '{contact}'. "
            f"What's their number?"
        )

    try:
        subprocess.run(
            ["kdeconnect-cli", "--device", device_or_err,
             "--send-sms", message, "--destination", contact],
            check=True, capture_output=True
        )
        return f"SMS sent to {contact}."
    except subprocess.CalledProcessError as e:
        return f"Failed to send SMS: {e.stderr.decode()}"


# ── Ring ──────────────────────────────────────────────────────────────────────

def ring_phone() -> str:
    """Ring the paired phone."""
    ok, device_or_err = _check_available()
    if not ok:
        return device_or_err

    try:
        subprocess.run(
            ["kdeconnect-cli", "--device", device_or_err, "--ring"],
            check=True, capture_output=True
        )
        return "Ringing your phone."
    except subprocess.CalledProcessError:
        return "Failed to ring phone."


# ── Battery ───────────────────────────────────────────────────────────────────

def get_battery(lang: str = "en") -> str:
    """Check phone battery level."""
    ok, device_or_err = _check_available()
    if not ok:
        return device_or_err

    try:
        result = subprocess.run(
            ["kdeconnect-cli", "--device", device_or_err, "--battery"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip() or result.stderr.strip()
        if lang == "ru":
            return f"Батарея телефона: {output}"
        return f"Phone battery: {output}"
    except Exception as e:
        return f"Couldn't check battery: {e}"


# ── Notifications ─────────────────────────────────────────────────────────────

def get_notifications(lang: str = "en") -> str:
    """
    List available KDE Connect plugins/status.
    Full notification mirroring depends on the phone granting notification access.
    """
    ok, device_or_err = _check_available()
    if not ok:
        return device_or_err

    try:
        result = subprocess.run(
            ["kdeconnect-cli", "--device", device_or_err, "--list-notifications"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip()
        if not output:
            return "No notifications from your phone right now." if lang == "en" \
                   else "Нет уведомлений с телефона."
        return output
    except Exception as e:
        return f"Couldn't read notifications: {e}"


# ── File transfer ─────────────────────────────────────────────────────────────

def send_file(filepath: str) -> str:
    """Send a file to the paired phone."""
    ok, device_or_err = _check_available()
    if not ok:
        return device_or_err

    try:
        subprocess.run(
            ["kdeconnect-cli", "--device", device_or_err, "--share", filepath],
            check=True, capture_output=True
        )
        return f"File sent to phone."
    except subprocess.CalledProcessError:
        return "Failed to send file."
