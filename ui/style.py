"""
ui/style.py
-----------
Reads ~/.config/matugen/generated/colors.css and generates a GTK4 stylesheet
that maps Material You color tokens to Jarvis UI widget classes.
Falls back to dark defaults if the matugen file is missing.
"""

from __future__ import annotations
import re
from pathlib import Path
import config

# ── Default fallback colors (matches the warm dark palette in colors.css) ─────
DEFAULTS = {
    "background":               "#1a1110",
    "surface":                  "#1a1110",
    "surface_container":        "#271d1c",
    "surface_container_high":   "#322826",
    "surface_container_highest":"#3d3231",
    "surface_bright":           "#423735",
    "on_surface":               "#f1dedc",
    "on_surface_variant":       "#d8c2bf",
    "primary":                  "#ffb4ab",
    "on_primary":               "#561e19",
    "primary_container":        "#73332d",
    "on_primary_container":     "#ffdad6",
    "secondary":                "#e7bdb8",
    "secondary_container":      "#5d3f3c",
    "on_secondary_container":   "#ffdad6",
    "tertiary":                 "#e0c38c",
    "outline":                  "#a08c8a",
    "outline_variant":          "#534341",
    "error":                    "#ffb4ab",
    "scrim":                    "#000000",
}


def _parse_matugen(path: Path) -> dict[str, str]:
    """Parse @define-color declarations from a CSS file."""
    colors: dict[str, str] = {}
    if not path.exists():
        return colors
    text = path.read_text()
    for m in re.finditer(r"@define-color\s+(\w+)\s+(#[0-9a-fA-F]{3,8})", text):
        colors[m.group(1)] = m.group(2)
    return colors


def load_colors() -> dict[str, str]:
    """Return merged color dict: matugen values override defaults."""
    colors = dict(DEFAULTS)
    matugen = _parse_matugen(Path(config.MATUGEN_CSS).expanduser())
    colors.update(matugen)
    return colors


def build_css(colors: dict[str, str]) -> str:
    """Generate a complete GTK4 CSS stylesheet for Jarvis."""
    c = colors
    return f"""
/* ── Jarvis GTK4 Stylesheet — generated from Matugen ─────────────────────── */

* {{
    -gtk-icon-shadow: none;
}}

window.jarvis-window {{
    background-color: {c['background']};
    color: {c['on_surface']};
}}

/* ── Header bar ──────────────────────────────────────────────────────────── */
.jarvis-header {{
    background-color: {c['surface_container']};
    border-bottom: 1px solid {c['outline_variant']};
    padding: 12px 16px;
}}

.jarvis-title {{
    color: {c['primary']};
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 4px;
    font-family: monospace;
}}

.jarvis-subtitle {{
    color: {c['on_surface_variant']};
    font-size: 11px;
    letter-spacing: 2px;
}}

.status-dot {{
    min-width: 8px;
    min-height: 8px;
    border-radius: 50%;
    background-color: {c['outline']};
}}
.status-dot.active {{
    background-color: {c['primary']};
}}
.status-dot.listening {{
    background-color: {c['tertiary']};
}}
.status-dot.thinking {{
    background-color: {c['secondary']};
}}

/* ── Chat area ───────────────────────────────────────────────────────────── */
.jarvis-chat-area {{
    background-color: {c['background']};
}}

scrolledwindow.jarvis-scroll {{
    background-color: {c['background']};
    border: none;
}}

/* ── Message bubbles ─────────────────────────────────────────────────────── */
.message-row {{
    padding: 4px 16px;
}}

.bubble {{
    border-radius: 18px;
    padding: 10px 14px;
}}

.bubble-user {{
    background-color: {c['primary_container']};
    color: {c['on_primary_container']};
    border-bottom-right-radius: 4px;
}}

.bubble-jarvis {{
    background-color: {c['surface_container_high']};
    color: {c['on_surface']};
    border-bottom-left-radius: 4px;
    border-left: 2px solid {c['primary']};
}}

.bubble-system {{
    background-color: transparent;
    color: {c['on_surface_variant']};
    font-style: italic;
    font-size: 12px;
}}

.message-label {{
    font-size: 14px;
    line-height: 1.5;
}}

.message-time {{
    font-size: 10px;
    color: {c['outline']};
    margin-top: 2px;
}}

.sender-label {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    margin-bottom: 2px;
}}

.sender-jarvis {{
    color: {c['primary']};
}}

.sender-user {{
    color: {c['secondary']};
}}

/* ── Input area ──────────────────────────────────────────────────────────── */
.jarvis-input-area {{
    background-color: {c['surface_container']};
    border-top: 1px solid {c['outline_variant']};
    padding: 12px 12px;
}}

.jarvis-entry {{
    background-color: {c['surface_container_highest']};
    color: {c['on_surface']};
    border: 1px solid {c['outline_variant']};
    border-radius: 24px;
    padding: 10px 16px;
    font-size: 14px;
    caret-color: {c['primary']};
}}

.jarvis-entry:focus {{
    border-color: {c['primary']};
    outline: none;
    box-shadow: 0 0 0 2px alpha({c['primary']}, 0.2);
}}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
.send-button {{
    background-color: {c['primary']};
    color: {c['on_primary']};
    border-radius: 50%;
    min-width: 40px;
    min-height: 40px;
    padding: 0;
    border: none;
    font-size: 16px;
}}

.send-button:hover {{
    background-color: {c['primary_container']};
    color: {c['on_primary_container']};
}}

.mic-button {{
    background-color: transparent;
    color: {c['on_surface_variant']};
    border-radius: 50%;
    min-width: 40px;
    min-height: 40px;
    padding: 0;
    border: 1px solid {c['outline_variant']};
    font-size: 18px;
    transition: all 200ms;
}}

.mic-button:hover {{
    border-color: {c['primary']};
    color: {c['primary']};
}}

.mic-button.recording {{
    background-color: {c['tertiary_container'] if 'tertiary_container' in c else c['primary_container']};
    color: {c['on_tertiary'] if 'on_tertiary' in c else c['on_primary']};
    border-color: {c['tertiary']};
    animation: pulse 1s infinite;
}}

/* ── Status bar ──────────────────────────────────────────────────────────── */
.jarvis-status-bar {{
    background-color: {c['surface_container_lowest'] if 'surface_container_lowest' in c else c['background']};
    padding: 4px 16px;
    border-top: 1px solid {c['outline_variant']};
}}

.status-label {{
    font-size: 11px;
    color: {c['on_surface_variant']};
    letter-spacing: 1px;
}}

.status-label.thinking {{
    color: {c['secondary']};
}}

.status-label.listening {{
    color: {c['tertiary']};
}}

.status-label.error {{
    color: {c['error']};
}}

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
scrollbar {{
    background-color: transparent;
    min-width: 4px;
    min-height: 4px;
}}

scrollbar slider {{
    background-color: {c['outline_variant']};
    border-radius: 4px;
    min-width: 4px;
    min-height: 4px;
}}

scrollbar slider:hover {{
    background-color: {c['outline']};
}}
"""


def get_stylesheet() -> str:
    """Load matugen colors and return complete GTK CSS."""
    colors = load_colors()
    return build_css(colors)
