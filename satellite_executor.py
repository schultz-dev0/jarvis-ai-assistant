"""Local skill execution runtime used by the Satellite client."""

from __future__ import annotations

import ast as _ast
import operator as _op
import re as _re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

import skills.apps as apps
import skills.files as files
import skills.phone as phone
import skills.system as system
import skills.web as web


def _media_play_music() -> str:
    apps.open_app("spotify")
    return "Playing music."


def _media_pause_music(lang: str = "en") -> str:
    if not shutil.which("playerctl"):
        return (
            "playerctl not found. Install with: sudo pacman -S playerctl"
            if lang == "en"
            else "playerctl не установлен."
        )
    subprocess.run(["playerctl", "pause"], timeout=2, check=False)
    return "Paused." if lang == "en" else "Пауза."


def _media_next_track(lang: str = "en") -> str:
    if not shutil.which("playerctl"):
        return (
            "playerctl not found. Install with: sudo pacman -S playerctl"
            if lang == "en"
            else "playerctl не установлен."
        )
    subprocess.run(["playerctl", "next"], timeout=2, check=False)
    return "Next track." if lang == "en" else "Следующий трек."


def _media_set_spotify_volume(value: str, lang: str = "en") -> str:
    if not shutil.which("playerctl"):
        return (
            "playerctl not found. Install with: sudo pacman -S playerctl"
            if lang == "en"
            else "playerctl не установлен."
        )
    vol = int(value)
    vol = max(0, min(200, vol))
    subprocess.run(["playerctl", "volume", str(vol / 100)], timeout=2, check=False)
    return f"Volume set to {vol}%."


def _files_find_file(query: str, lang: str = "en") -> str:
    results = files.find_files(query, max_results=5)
    if not results:
        return (
            f"No files found matching '{query}'."
            if lang == "en"
            else f"Файлов по запросу «{query}» не найдено."
        )
    lines = [
        f"Files matching '{query}':"
        if lang == "en"
        else f"Файлы по запросу «{query}»:"
    ]
    for res in results:
        lines.append(f"  {res.path} (score: {res.score:.2f})")
    return "\n".join(lines)


def _files_open_file(query: str, app_override: str | None = None, lang: str = "en") -> str:
    if app_override:
        matches = files.find_files(query)
        if matches:
            exe = app_override.lower().strip()
            aliases = {"vscode": "code", "obsidian": "obsidian", "vlc": "vlc"}
            exe = aliases.get(exe, exe)
            return files.open_path(matches[0].path, exe if shutil.which(exe) else None)
    return files.find_and_open(query, lang=lang)


# ── Date / time ───────────────────────────────────────────────────────────────

def _system_get_datetime(lang: str = "en") -> str:
    from datetime import datetime as _dt
    now = _dt.now()
    if lang == "ru":
        days_ru = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
        months_ru = ["января", "февраля", "марта", "апреля", "мая", "июня",
                     "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        dow = days_ru[now.weekday()]
        return f"Сейчас {now.strftime('%H:%M')}, {dow}, {now.day} {months_ru[now.month - 1]} {now.year} г."
    return now.strftime("It's %H:%M on %A, %B %-d, %Y.")


# ── System info ───────────────────────────────────────────────────────────────

def _system_get_info(lang: str = "en") -> str:
    lines: list[str] = []
    try:
        load = Path("/proc/loadavg").read_text().split()[:3]
        label = "CPU load (1/5/15 min)" if lang == "en" else "Загрузка CPU (1/5/15 мин)"
        lines.append(f"{label}: {load[0]} / {load[1]} / {load[2]}")
    except Exception:
        pass
    try:
        mem_info: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                mem_info[parts[0].rstrip(":")] = int(parts[1])
        total_mb = mem_info.get("MemTotal", 0) // 1024
        avail_mb = mem_info.get("MemAvailable", 0) // 1024
        used_mb = total_mb - avail_mb
        pct = int(used_mb / total_mb * 100) if total_mb else 0
        used_label = "used" if lang == "en" else "исп."
        lines.append(f"RAM: {used_mb} MB / {total_mb} MB ({pct}% {used_label})")
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["df", "-h", str(Path.home())], capture_output=True, text=True, timeout=3
        )
        df_lines = r.stdout.strip().splitlines()
        if len(df_lines) >= 2:
            parts = df_lines[1].split()
            if len(parts) >= 5:
                label = "Disk (~)" if lang == "en" else "Диск (~)"
                full_label = "full" if lang == "en" else "зап."
                lines.append(f"{label}: {parts[2]} / {parts[1]} ({parts[4]} {full_label})")
    except Exception:
        pass
    if not lines:
        return "System info unavailable." if lang == "en" else "Информация о системе недоступна."
    header = "System status:" if lang == "en" else "Состояние системы:"
    return header + "\n" + "\n".join(lines)


# ── Memory ────────────────────────────────────────────────────────────────────

def _memory_store_fact(key: str, value: str, lang: str = "en") -> str:
    if not key or not value:
        return "Please specify a key and value." if lang == "en" else "Укажите ключ и значение."
    from skills.memory import store_fact
    store_fact(key.strip(), value.strip())
    return (
        f"Remembered: {key} = {value}." if lang == "en"
        else f"Запомнила: {key} = {value}."
    )


# ── Calculator ────────────────────────────────────────────────────────────────

def _calculate(value: str, lang: str = "en") -> str:
    expr = (value or "").strip()
    if not expr:
        return "No expression provided." if lang == "en" else "Выражение не указано."

    # Handle "X% of Y" / "X% от Y"
    m = _re.match(
        r"^(\d+(?:[.,]\d+)?)\s*%\s+(?:of|от)\s+(\d+(?:[.,]\d+)?)$",
        expr, _re.IGNORECASE,
    )
    if m:
        pct = float(m.group(1).replace(",", ".")) / 100
        num = float(m.group(2).replace(",", "."))
        result = pct * num
        r: int | float = int(result) if result == int(result) else round(result, 4)
        return f"{expr} = {r}"

    # Normalise for safe AST eval
    clean = (
        expr.replace(",", ".")
            .replace("×", "*").replace("÷", "/")
            .replace("^", "**")
    )
    clean = _re.sub(r"(\d)\s*%", r"(\1/100)", clean)

    _SAFE_OPS = {
        _ast.Add: _op.add, _ast.Sub: _op.sub,
        _ast.Mult: _op.mul, _ast.Div: _op.truediv,
        _ast.Pow: _op.pow, _ast.Mod: _op.mod,
        _ast.FloorDiv: _op.floordiv, _ast.USub: _op.neg,
    }

    def _eval(node: _ast.expr) -> float:
        if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, _ast.BinOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, _ast.UnaryOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_eval(node.operand))
        raise ValueError("Unsupported expression")

    try:
        tree = _ast.parse(clean, mode="eval")
        result_f = _eval(tree.body)
        r = int(result_f) if result_f == int(result_f) else round(result_f, 6)
        return f"{expr} = {r}"
    except ZeroDivisionError:
        return "Division by zero." if lang == "en" else "Деление на ноль."
    except Exception:
        return (
            f"Could not evaluate '{expr}'." if lang == "en"
            else f"Не удалось вычислить '{expr}'."
        )


# ── Additional media ──────────────────────────────────────────────────────────

def _media_previous_track(lang: str = "en") -> str:
    if not shutil.which("playerctl"):
        return (
            "playerctl not found. Install with: sudo pacman -S playerctl"
            if lang == "en" else "playerctl не установлен."
        )
    subprocess.run(["playerctl", "previous"], timeout=2, check=False)
    return "Previous track." if lang == "en" else "Предыдущий трек."


# ── Bluetooth ─────────────────────────────────────────────────────────────────

def _system_toggle_bluetooth(value: str = "", lang: str = "en") -> str:
    if not shutil.which("bluetoothctl"):
        return "bluetoothctl not found." if lang == "en" else "bluetoothctl не найден."
    v = (value or "").strip().lower()
    if v == "on":
        subprocess.run(["bluetoothctl", "power", "on"], capture_output=True, timeout=5, check=False)
        return "Bluetooth enabled." if lang == "en" else "Bluetooth включён."
    if v == "off":
        subprocess.run(["bluetoothctl", "power", "off"], capture_output=True, timeout=5, check=False)
        return "Bluetooth disabled." if lang == "en" else "Bluetooth выключен."
    # Toggle based on current state
    r = subprocess.run(["bluetoothctl", "show"], capture_output=True, text=True, timeout=5, check=False)
    if "Powered: yes" in r.stdout:
        subprocess.run(["bluetoothctl", "power", "off"], capture_output=True, timeout=5, check=False)
        return "Bluetooth turned off." if lang == "en" else "Bluetooth выключен."
    subprocess.run(["bluetoothctl", "power", "on"], capture_output=True, timeout=5, check=False)
    return "Bluetooth turned on." if lang == "en" else "Bluetooth включён."


TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "apps.open_app": apps.open_app,
    "apps.close_app": apps.close_app,
    "apps.focus_app": apps.focus_app,
    "files.find_file": _files_find_file,
    "files.open_file": _files_open_file,
    "files.list_directory": files.list_directory,
    "system.get_datetime": _system_get_datetime,
    "system.get_info": _system_get_info,
    "system.set_volume": system.set_volume,
    "system.set_brightness": system.set_brightness,
    "system.toggle_wifi": system.toggle_wifi,
    "system.toggle_bluetooth": _system_toggle_bluetooth,
    "system.screenshot": system.screenshot,
    "system.calculate": _calculate,
    "memory.store_fact": _memory_store_fact,
    "web.get_weather": web.get_weather,
    "web.get_news": web.get_news,
    "web.search_web": web.search_web,
    "phone.send_sms": phone.send_sms,
    "phone.ring_phone": phone.ring_phone,
    "phone.get_battery": phone.get_battery,
    "phone.get_notifications": phone.get_notifications,
    "media.play_music": _media_play_music,
    "media.pause_music": _media_pause_music,
    "media.previous_track": _media_previous_track,
    "media.next_track": _media_next_track,
    "media.set_spotify_volume": _media_set_spotify_volume,
}


def list_tools() -> list[str]:
    return sorted(TOOL_REGISTRY.keys())


def execute_tool(tool: str, arguments: dict[str, Any]) -> str:
    if tool not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {tool}")
    fn = TOOL_REGISTRY[tool]
    return str(fn(**arguments))
