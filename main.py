"""
main.py
-------
Jarvis — Personal AI Assistant
Entry point. Wires together:
  - GTK4 window (ui/window.py)
  - Brain / intent parser (brain.py)          — Ollama + Groq fallback
  - Dispatcher / skill router (dispatcher.py)
  - TTS (tts.py)
  - Voice listener (listener.py)
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
import numpy as np
import pyaudio
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

import config
import brain
import dispatcher
import tts
from ui.window import JarvisWindow, MSG_USER, MSG_JARVIS, MSG_SYSTEM
from listener import VoiceListener

# Ensure data directories exist
config.JARVIS_DATA_DIR.mkdir(parents=True, exist_ok=True)
config.JARVIS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
config.VOICES_DIR.mkdir(parents=True, exist_ok=True)

# ── Conversation history limit ────────────────────────────────────────────────
# 12 messages = 6 full exchanges. Enough for pronoun resolution ("it", "that",
# "the same one") without bloating the LLM context on every call.
MAX_HISTORY = 12


class JarvisApp(Gtk.Application):

    def __init__(self):
        super().__init__(application_id="com.jarvis.assistant")
        self.window: JarvisWindow | None = None
        self._listener: VoiceListener | None = None

        # Push-to-talk recording state
        self._mic_audio: list[np.ndarray] = []
        self._mic_stream = None
        self._pa = None
        self._mic_recording = threading.Event()

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
        self.window = JarvisWindow(
            app=self,
            on_text_input=self._handle_text,
            on_voice_start=self._voice_start,
            on_voice_stop=self._voice_stop,
        )
        self.window.present()

        tts.start()
        self._start_wake_listener()

        threading.Thread(target=self._startup_tasks, daemon=True).start()

    def _startup_tasks(self):
        """All background init in one thread, staggered to avoid startup lag."""
        self._check_backends()
        self._start_mobile_server()
        self._start_proactive()

        # Pre-build file index so the first file search is instant
        try:
            from skills.files import get_index
            idx = get_index()
            print(f"[main] File index ready: {len(idx)} files")
        except Exception as e:
            print(f"[main] File index error: {e}")

    # ── Backend status ────────────────────────────────────────────────────────

    def _check_backends(self):
        ollama_ok = brain.check_ollama_alive()
        groq_ok   = brain.check_groq_alive()

        if ollama_ok:
            label = f"OLLAMA: {config.OLLAMA_MODEL}"
            try:
                brain.parse_intent("hello")
            except Exception:
                pass
        elif groq_ok:
            label = f"GROQ: {config.GROQ_MODEL} (cloud)"
            GLib.idle_add(
                self.window.add_message,
                "Ollama offline — using Groq cloud fallback.",
                MSG_SYSTEM,
            )
        else:
            label = "NO LLM — fallback mode"
            GLib.idle_add(
                self.window.add_message,
                "No LLM available. Set GROQ_API_KEY or run 'ollama serve'.",
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

    # ── Core command handler ──────────────────────────────────────────────────

    def _handle_text(self, text: str):
        """
        Process a text command from any source (keyboard, mic, mobile, wake word).
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

    # ── Push-to-talk ──────────────────────────────────────────────────────────

    def _voice_start(self):
        """Mic button pressed: open stream and record until _mic_recording is cleared."""
        try:
            self._pa = pyaudio.PyAudio()
            self._mic_audio = []
            self._mic_stream = self._pa.open(
                rate=16000, channels=1,
                format=pyaudio.paInt16,
                input=True, frames_per_buffer=1280,
            )
            self._mic_recording.set()
            while self._mic_recording.is_set():
                data = self._mic_stream.read(1280, exception_on_overflow=False)
                self._mic_audio.append(np.frombuffer(data, dtype=np.int16))
        except Exception as e:
            self._mic_recording.clear()
            GLib.idle_add(self.window.add_message, f"Mic error: {e}", MSG_SYSTEM)

    def _voice_stop(self):
        """Mic button released: stop recording, transcribe, dispatch."""
        try:
            # Stop the loop first — then close the stream safely
            self._mic_recording.clear()

            import time; time.sleep(0.08)   # let current read() finish

            if self._mic_stream:
                self._mic_stream.stop_stream()
                self._mic_stream.close()
                self._mic_stream = None
            if self._pa:
                self._pa.terminate()
                self._pa = None

            if not self._mic_audio:
                GLib.idle_add(self.window.set_status, "READY", "idle")
                return

            audio = np.concatenate(self._mic_audio).astype(np.float32) / 32768.0

            if self._listener is None:
                self._listener = VoiceListener()

            text, lang = self._listener.transcribe_once(audio)

            if text:
                GLib.idle_add(self.window.add_message, text, MSG_USER)
                threading.Thread(
                    target=self._handle_text, args=(text,), daemon=True
                ).start()
            else:
                GLib.idle_add(self.window.set_status, "DIDN'T CATCH THAT", "idle")

        except Exception as e:
            GLib.idle_add(self.window.add_message, f"Voice error: {e}", MSG_SYSTEM)
            GLib.idle_add(self.window.set_status, "READY", "idle")

    # ── Wake word ─────────────────────────────────────────────────────────────

    def _start_wake_listener(self):
        self._listener = VoiceListener(
            on_wake=self._on_wake_word,
            on_transcript=self._on_wake_transcript,
            on_listening_start=lambda: self.window.set_status("LISTENING...", "listening"),
            on_listening_stop=lambda:  self.window.set_status("PROCESSING...", "thinking"),
            on_error=lambda e: GLib.idle_add(
                self.window.add_message, f"Voice: {e}", MSG_SYSTEM
            ),
        )
        self._listener.start()

    def _on_wake_word(self):
        # Detect last used language so the ack is in the right tongue
        lang = "en"
        for role, text in reversed(self._history):
            if role == "user":
                lang = brain.detect_language(text)
                break
        tts.speak("Yes?" if lang == "en" else "Да?")
        GLib.idle_add(self.window.set_status, "WAKE WORD DETECTED", "listening")

    def _on_wake_transcript(self, text: str, lang: str):
        GLib.idle_add(self.window.add_message, text, MSG_USER)
        threading.Thread(
            target=self._handle_text, args=(text,), daemon=True
        ).start()


def main():
    app = JarvisApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())