"""
ui/window.py
------------
Sasha GTK4 main window.
- Chat-style message history
- Text input with send button
- Status bar showing current state
- Reloads Matugen theme on startup
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Pango, Gdk

import threading
from datetime import datetime
from typing import Callable

import config
from ui.style import get_stylesheet


# ── Message types ─────────────────────────────────────────────────────────────
MSG_USER   = "user"
MSG_JARVIS = "jarvis"
MSG_SYSTEM = "system"


class SashaWindow(Gtk.ApplicationWindow):

    def __init__(self, app: Gtk.Application,
                 on_text_input: Callable[[str], None]):
        super().__init__(application=app, title=config.WINDOW_TITLE)

        self.on_text_input  = on_text_input

        self.set_default_size(config.WINDOW_DEFAULT_WIDTH, config.WINDOW_DEFAULT_HEIGHT)
        self.add_css_class("jarvis-window")

        # Load stylesheet
        self._apply_style()

        # Build layout
        self._build_ui()

        # Welcome message
        GLib.idle_add(self._show_welcome)

    # ── Styling ───────────────────────────────────────────────────────────────

    def _apply_style(self):
        css = get_stylesheet()
        provider = Gtk.CssProvider()
        provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        # Header
        root.append(self._build_header())

        # Chat scroll area
        self._chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._chat_box.add_css_class("jarvis-chat-area")
        self._chat_box.set_vexpand(True)

        scroll = Gtk.ScrolledWindow()
        scroll.add_css_class("jarvis-scroll")
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self._chat_box)
        self._scroll = scroll
        root.append(scroll)

        # Input area
        root.append(self._build_input_area())

        # Status bar
        root.append(self._build_status_bar())

    def _build_header(self) -> Gtk.Widget:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bar.add_css_class("jarvis-header")

        # Status dot
        self._status_dot = Gtk.Label(label="●")
        self._status_dot.add_css_class("status-dot")
        bar.append(self._status_dot)

        # Title / subtitle
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        title = Gtk.Label(label=config.ASSISTANT_NAME.upper())
        title.add_css_class("jarvis-title")
        title.set_xalign(0)
        sub = Gtk.Label(label="PERSONAL ASSISTANT")
        sub.add_css_class("jarvis-subtitle")
        sub.set_xalign(0)
        title_box.append(title)
        title_box.append(sub)
        title_box.set_hexpand(True)
        bar.append(title_box)

        return bar

    def _build_input_area(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.add_css_class("jarvis-input-area")

        # Text entry
        self._entry = Gtk.Entry()
        self._entry.add_css_class("jarvis-entry")
        self._entry.set_placeholder_text("Ask Sasha anything...")
        self._entry.set_hexpand(True)
        self._entry.connect("activate", self._on_send)
        box.append(self._entry)

        # Send button
        send_btn = Gtk.Button(label="➤")
        send_btn.add_css_class("send-button")
        send_btn.connect("clicked", self._on_send)
        box.append(send_btn)

        return box

    def _build_status_bar(self) -> Gtk.Widget:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bar.add_css_class("jarvis-status-bar")

        self._status_label = Gtk.Label(label="READY")
        self._status_label.add_css_class("status-label")
        self._status_label.set_xalign(0)
        bar.append(self._status_label)

        return bar

    # ── Message display ───────────────────────────────────────────────────────

    def add_message(self, text: str, msg_type: str = MSG_JARVIS):
        """Add a message bubble to the chat. Thread-safe via GLib.idle_add."""
        GLib.idle_add(self._add_message_main, text, msg_type)

    def _add_message_main(self, text: str, msg_type: str):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row.add_css_class("message-row")
        row.set_margin_top(4)

        if msg_type == MSG_SYSTEM:
            lbl = Gtk.Label(label=text)
            lbl.add_css_class("bubble")
            lbl.add_css_class("bubble-system")
            lbl.add_css_class("message-label")
            lbl.set_wrap(True)
            lbl.set_xalign(0.5)
            row.set_halign(Gtk.Align.CENTER)
            row.append(lbl)
        else:
            is_user = msg_type == MSG_USER
            row.set_halign(Gtk.Align.END if is_user else Gtk.Align.START)

            # Sender label
            sender_lbl = Gtk.Label(
                label="YOU" if is_user else config.ASSISTANT_NAME.upper()
            )
            sender_lbl.add_css_class("sender-label")
            sender_lbl.add_css_class("sender-user" if is_user else "sender-jarvis")
            sender_lbl.set_xalign(1.0 if is_user else 0.0)
            row.append(sender_lbl)

            # Bubble
            bubble = Gtk.Label(label=text)
            bubble.add_css_class("bubble")
            bubble.add_css_class("bubble-user" if is_user else "bubble-jarvis")
            bubble.add_css_class("message-label")
            bubble.set_wrap(True)
            bubble.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            bubble.set_xalign(0)
            bubble.set_max_width_chars(40)
            bubble.set_selectable(True)
            row.append(bubble)

            # Timestamp
            ts = Gtk.Label(label=datetime.now().strftime("%H:%M"))
            ts.add_css_class("message-time")
            ts.set_xalign(1.0 if is_user else 0.0)
            row.append(ts)

        self._chat_box.append(row)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        def _do():
            adj = self._scroll.get_vadjustment()
            adj.set_value(adj.get_upper())
        GLib.idle_add(_do)

    def _show_welcome(self):
        self.add_message(f"{config.ASSISTANT_NAME.upper()} ONLINE", MSG_SYSTEM)
        self.add_message(
            "Good day. I'm online and ready to assist. "
            "Type your request and I will take it from there.",
            MSG_JARVIS
        )

    # ── Input handling ────────────────────────────────────────────────────────

    def _on_send(self, *_):
        text = self._entry.get_text().strip()
        if not text:
            return
        self._entry.set_text("")
        self.add_message(text, MSG_USER)
        threading.Thread(
            target=self.on_text_input,
            args=(text,),
            daemon=True
        ).start()

    # ── Status updates ────────────────────────────────────────────────────────

    def set_status(self, text: str, state: str = "idle"):
        """Update status bar. state: 'idle' | 'listening' | 'thinking' | 'error'"""
        def _do():
            self._status_label.set_text(text)
            for cls in ("listening", "thinking", "error"):
                self._status_label.remove_css_class(cls)
                self._status_dot.remove_css_class(cls)
            if state != "idle":
                self._status_label.add_css_class(state)
                self._status_dot.add_css_class(state)
                self._status_dot.add_css_class("active")
            else:
                self._status_dot.remove_css_class("active")
        GLib.idle_add(_do)

    def set_thinking(self, thinking: bool):
        if thinking:
            self.set_status("THINKING...", "thinking")
        else:
            self.set_status("READY", "idle")
