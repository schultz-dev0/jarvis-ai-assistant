"""
tts.py
------
Text-to-speech using piper-tts (local, fast, high quality).
Selects English or Russian voice based on language.
Runs in a background thread to avoid blocking the UI.
"""

from __future__ import annotations

import subprocess
import shutil
import threading
import queue
import re
from pathlib import Path

import config

_tts_queue: queue.Queue[str | None] = queue.Queue(maxsize=5)  # Bounded queue to prevent accumulation
_tts_thread: threading.Thread | None = None
_speaking = threading.Event()
_queue_lock = threading.Lock()  # Protect queue access from multiple threads


def _detect_language(text: str) -> str:
    """Detect language from Cyrillic presence."""
    return "ru" if re.search(r"[а-яёА-ЯЁ]", text) else "en"


def _speak_blocking(text: str):
    """Speak text synchronously using piper."""
    lang = _detect_language(text)
    voice_path = config.TTS_VOICE_RU if lang == "ru" else config.TTS_VOICE_EN

    if not shutil.which("piper"):
        print(f"[tts] piper not found, would say: {text}")
        return

    if not Path(voice_path).exists():
        print(f"[tts] Voice model not found at {voice_path}, would say: {text}")
        return

    try:
        _speaking.set()
        piper_proc = subprocess.Popen(
            ["piper",
             "--model", str(voice_path),
             "--output-raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        aplay_proc = subprocess.Popen(
            ["aplay", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"],
            stdin=piper_proc.stdout,
            stderr=subprocess.DEVNULL,
        )

        piper_proc.stdin.write(text.encode())
        piper_proc.stdin.close()
        piper_proc.wait()
        aplay_proc.wait()

    except Exception as e:
        print(f"[tts] Error: {e}")
    finally:
        _speaking.clear()


def _tts_worker():
    """Background worker that processes the TTS queue serially."""
    while True:
        text = _tts_queue.get()
        if text is None:  # poison pill to stop
            break
        _speak_blocking(text)
        _tts_queue.task_done()


def start():
    """Start the background TTS worker thread."""
    global _tts_thread
    _tts_thread = threading.Thread(target=_tts_worker, daemon=True)
    _tts_thread.start()


def speak(text: str):
    """Queue text for speech (non-blocking). Interrupts any existing speech."""
    if not text:
        return
    
    with _queue_lock:
        # Clear existing queue atomically (interrupt current speech)
        try:
            while True:
                _tts_queue.get_nowait()
        except queue.Empty:
            pass
        
        # Queue new text, dropping oldest if queue is full
        try:
            _tts_queue.put(text, block=False)
        except queue.Full:
            # Drop oldest item and retry
            try:
                _tts_queue.get_nowait()
                _tts_queue.put(text, block=False)
            except queue.Empty:
                pass


def is_speaking() -> bool:
    return _speaking.is_set()


def stop():
    """Stop the TTS worker."""
    _tts_queue.put(None)
