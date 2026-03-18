"""
main.py
-------
Sasha — Personal AI Assistant
Entry point. Wires together:
  - GTK4 window (ui/window.py)
  - Brain / intent parser (brain.py)          — Ollama + Groq fallback
  - Dispatcher / skill router (dispatcher.py)
  - TTS (tts.py)
  - Mobile server (mobile_server.py)           — WiFi phone access
  - Memory / learning (skills/memory.py)
  - Proactive notifications (skills/proactive.py)
  - Filesystem skill (skills/files.py)         — file search + open
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if "PULSE_SERVER" not in os.environ:
    os.environ["PULSE_SERVER"] = f"unix:/run/user/{os.getuid()}/pulse/native"
os.environ["ALSA_PLUGIN_DIR"] = ""

import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

import config
import brain
import dispatcher
import tts
from ui.window import SashaWindow, MSG_USER, MSG_JARVIS, MSG_SYSTEM

# Ensure data directories exist
config.JARVIS_DATA_DIR.mkdir(parents=True, exist_ok=True)
config.JARVIS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
config.VOICES_DIR.mkdir(parents=True, exist_ok=True)

# ── Conversation history limit ────────────────────────────────────────────────
# 12 messages = 6 full exchanges. Enough for pronoun resolution ("it", "that",
# "the same one") without bloating the LLM context on every call.
MAX_HISTORY = 12


class SashaApp(Gtk.Application):

    def __init__(self):
        super().__init__(application_id="com.sasha.assistant")
        self.window: SashaWindow | None = None

        # Serialise LLM calls
        self._processing = threading.Event()

        # Conversation history: list of ("user"|"assistant", text) tuples
        self._history: list[tuple[str, str]] = []

    # ── History management ────────────────────────────────────────────────────

    def _add_to_history(self, role: str, text: str):
        self._history.append((role, text))
        if len(self._history) > MAX_HISTORY:
            self._history = self._history[-MAX_HISTORY:]

    # ── Startup ───────────────────────────────────────────────────────────────

    def do_activate(self):
        self.window = SashaWindow(
            app=self,
            on_text_input=self._handle_text,
        )
        self.window.present()

        tts.start()

        threading.Thread(target=self._startup_tasks, daemon=True).start()

    def _startup_tasks(self):
        """All background init in one thread, staggered to avoid startup lag."""
        self._check_backends()
        self._start_mobile_server()
        self._start_proactive()
        self._start_telegram()

        # Pre-build file index so the first file search is instant
        try:
            from skills.files import get_index
            idx = get_index()
            print(f"[main] File index ready: {len(idx)} files")
        except Exception as e:
            print(f"[main] File index error: {e}")

    # ── Backend status ────────────────────────────────────────────────────────

    def _check_backends(self):
        GLib.idle_add(self.window.set_status, "CHECKING MODEL...", "thinking")
        ollama_ok, ollama_msg = brain.ensure_ollama_model_available(
            auto_start=True,
            auto_pull=True,
        )
        groq_ok   = brain.check_groq_alive()

        if ollama_ok:
            label = f"OLLAMA: {config.OLLAMA_MODEL}"
            GLib.idle_add(self.window.add_message, ollama_msg, MSG_SYSTEM)
        elif groq_ok:
            label = f"GROQ: {config.GROQ_MODEL} (cloud)"
            GLib.idle_add(
                self.window.add_message,
                f"{ollama_msg} Using Groq cloud fallback.",
                MSG_SYSTEM,
            )
        else:
            label = "NO LLM — fallback mode"
            GLib.idle_add(
                self.window.add_message,
                f"{ollama_msg} No fallback LLM available.",
                MSG_SYSTEM,
            )

        GLib.idle_add(self.window.set_status, label, "idle")

    # ── Mobile server ─────────────────────────────────────────────────────────

    def _start_mobile_server(self):
        try:
            from mobile_server import start_mobile_server, get_local_ip
            start_mobile_server()
            ip   = get_local_ip()
            port = config.MOBILE_SERVER_PORT
            GLib.idle_add(
                self.window.add_message,
                f"Mobile access: http://{ip}:{port}",
                MSG_SYSTEM,
            )
        except Exception as e:
            print(f"[main] Mobile server: {e}")

    # ── Proactive notifications ───────────────────────────────────────────────

    def _start_proactive(self):
        try:
            from skills.proactive import start_proactive_loop

            def _push(text: str, lang: str = "en"):
                GLib.idle_add(self.window.add_message, text, MSG_SYSTEM)
                tts.speak(text)

            start_proactive_loop(_push)
        except Exception as e:
            print(f"[main] Proactive: {e}")

    def _start_telegram(self):
        try:
            from telegram_bot import start_telegram_bot
            if start_telegram_bot():
                GLib.idle_add(
                    self.window.add_message,
                    "Telegram bot active.",
                    MSG_SYSTEM,
                )
        except ImportError:
            pass  # python-telegram-bot not installed
        except Exception as e:
            print(f"[main] Telegram: {e}")

    # ── Core command handler ──────────────────────────────────────────────────

    def _handle_text(self, text: str):
        """
                Process a text command from any source (keyboard or mobile).
        Passes the rolling conversation history to the LLM so multi-turn
        exchanges work naturally:
          "open spotify"  →  "pause it"  →  "turn it up to 60"
        """
        if self._processing.is_set():
            return
        self._processing.set()

        try:
            self.window.set_thinking(True)

            # Record user turn in history first
            self._add_to_history("user", text)

            # Auto-learn facts from natural speech
            if config.MEMORY_ENABLED:
                try:
                    from skills.memory import extract_and_store_facts
                    extract_and_store_facts(text, brain.detect_language(text))
                except Exception:
                    pass

            # Parse intent with history context (exclude current turn — it's
            # already the final user message in the LLM call)
            intent = brain.parse_intent(text, history=self._history[:-1])

            # Execute
            result = dispatcher.dispatch(intent, raw_input=text)

            # Record assistant turn in history
            self._add_to_history("assistant", result)

            # Persist interaction for memory/learning
            if config.MEMORY_ENABLED:
                try:
                    from skills.memory import record_interaction
                    record_interaction(
                        user_input=text,
                        action=intent.action,
                        target=intent.target,
                        result=result,
                        success=True,
                        lang=intent.language,
                    )
                except Exception:
                    pass

            # Update desktop UI
            GLib.idle_add(self.window.add_message, result, MSG_JARVIS)

            # Push to any connected mobile clients
            try:
                from mobile_server import broadcast_message
                broadcast_message(result)
            except Exception:
                pass

            tts.speak(result)

        except Exception as e:
            msg = f"Error: {e}"
            GLib.idle_add(self.window.add_message, msg, MSG_SYSTEM)
        finally:
            self.window.set_thinking(False)
            self._processing.clear()

def main():
    app = SashaApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())