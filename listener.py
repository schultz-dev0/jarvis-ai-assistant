"""
listener.py
-----------
Always-on voice listener with two stages:
  1. Wake word detection (openwakeword) — very low CPU
  2. Speech recording + transcription (faster-whisper) — triggered on wake

Emits callbacks:
  on_wake()                    — wake word detected
  on_transcript(text, lang)    — final transcription ready
  on_listening_start()         — started recording user speech
  on_listening_stop()          — stopped recording

No training required:
  - faster-whisper auto-detects English and Russian
  - openwakeword has a pre-trained "jarvis" community model
    (auto-downloaded on first run to ~/.local/share/openwakeword/)
"""

from __future__ import annotations

import os
import ctypes
import threading
import numpy as np
import time
from typing import Callable
from pathlib import Path

import config

# ── Constants ─────────────────────────────────────────────────────────────────
SAMPLE_RATE    = 16000
CHUNK_SIZE     = 1280          # ~80ms chunks — openwakeword expects this
SILENCE_CHUNKS = int(config.SILENCE_DURATION * SAMPLE_RATE / CHUNK_SIZE)

# openwakeword stores downloaded models here
OWW_MODEL_DIR = Path.home() / ".local" / "share" / "openwakeword"


# ── ALSA noise suppression ────────────────────────────────────────────────────
# PyAudio probes every ALSA device on pa.PyAudio() / pa.open() and dumps
# dozens of harmless "Unknown PCM" errors to stderr via the ALSA C library.
# We silence them by replacing ALSA's error handler with a no-op.

def _suppress_alsa_errors():
    """Install a no-op ALSA error handler to kill the stderr spam."""
    try:
        _HANDLER = ctypes.CFUNCTYPE(
            None,
            ctypes.c_char_p,   # filename
            ctypes.c_int,      # line
            ctypes.c_char_p,   # function
            ctypes.c_int,      # err
            ctypes.c_char_p,   # fmt
        )
        _noop = _HANDLER(lambda *_: None)
        _libasound = ctypes.cdll.LoadLibrary("libasound.so.2")
        _libasound.snd_lib_error_set_handler(_noop)
    except Exception:
        pass   # not on this system — silently continue


_suppress_alsa_errors()


# ── openwakeword model resolution ────────────────────────────────────────────

def _oww_model_path(model_name: str) -> Path | None:
    """
    Find the downloaded ONNX file for model_name in OWW_MODEL_DIR.
    Returns the Path if found, None otherwise.
    """
    OWW_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    # Try exact name first, then with .onnx extension
    for candidate in [
        OWW_MODEL_DIR / model_name,
        OWW_MODEL_DIR / f"{model_name}.onnx",
        OWW_MODEL_DIR / f"{model_name}.tflite",
    ]:
        if candidate.exists():
            return candidate
    return None


def _download_oww_model(model_name: str) -> Path | None:
    """
    Download model_name via openwakeword's built-in downloader.
    Returns the path to the downloaded file, or None on failure.
    """
    try:
        import openwakeword.utils as oww_utils
        print(f"[listener] Downloading wake word model '{model_name}'...")
        oww_utils.download_models([model_name])
        path = _oww_model_path(model_name)
        if path:
            print(f"[listener] Model downloaded to {path}")
        return path
    except Exception as e:
        print(f"[listener] Model download failed: {e}")
        return None


def _resolve_oww_model(model_name: str) -> Path | None:
    """
    Find or download the openwakeword model.
    Returns the ONNX path to pass to OWWModel, or None if unavailable.
    """
    # Already on disk?
    path = _oww_model_path(model_name)
    if path:
        return path

    # Try downloading
    path = _download_oww_model(model_name)
    if path:
        return path

    # Not available — list what IS available so the user can pick one
    try:
        import openwakeword.utils as oww_utils
        # Download the default bundled models as a fallback
        print("[listener] Downloading default openwakeword models...")
        oww_utils.download_models()
        path = _oww_model_path(model_name)
        if path:
            return path

        # Still nothing — show available models
        available = [f.stem for f in OWW_MODEL_DIR.glob("*.onnx")]
        if available:
            print(
                f"[listener] Wake word '{model_name}' not found.\n"
                f"           Available models: {', '.join(available)}\n"
                f"           Set WAKE_WORD_MODEL in config.py to one of the above."
            )
        else:
            print(
                "[listener] No wake word models found after download attempt.\n"
                "           Push-to-talk still works.\n"
                "           Try: python3 -c \"import openwakeword; "
                "openwakeword.utils.download_models()\""
            )
    except Exception as e:
        print(f"[listener] Could not resolve wake word model: {e}")

    return None


class VoiceListener:
    """
    Manages wake word detection and speech-to-text in background threads.
    Call start() to begin, stop() to shut down.
    """

    def __init__(
        self,
        on_wake:            Callable[[], None]            | None = None,
        on_transcript:      Callable[[str, str], None]    | None = None,
        on_listening_start: Callable[[], None]            | None = None,
        on_listening_stop:  Callable[[], None]            | None = None,
        on_error:           Callable[[str], None]         | None = None,
    ):
        self.on_wake            = on_wake            or (lambda: None)
        self.on_transcript      = on_transcript      or (lambda t, l: None)
        self.on_listening_start = on_listening_start or (lambda: None)
        self.on_listening_stop  = on_listening_stop  or (lambda: None)
        self.on_error           = on_error           or (lambda e: print(f"[listener] {e}"))

        self._running      = False
        self._thread:  threading.Thread | None = None
        self._oww_model    = None
        self._oww_key      = None   # the key used to read scores from predict()
        self._whisper      = None

    def _load_models(self) -> bool:
        """Load openwakeword (optional) and faster-whisper."""

        wake_disabled = os.environ.get("JARVIS_DISABLE_WAKEWORD", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        # ── Wake word ─────────────────────────────────────────────────────────
        # Non-fatal: if the model can't be loaded, push-to-talk still works.
        try:
            if wake_disabled:
                print("[listener] Wake word disabled by JARVIS_DISABLE_WAKEWORD")
                raise RuntimeError("wakeword disabled")

            from openwakeword.model import Model as OWWModel

            model_name = config.WAKE_WORD_MODEL

            # openwakeword API differs across versions. Current versions expose
            # built-in models when Model() is constructed with no args.
            self._oww_model = OWWModel()
            available = list(getattr(self._oww_model, "models", {}).keys())

            alias_map = {
                "jarvis": "hey_jarvis",
                "hey jarvis": "hey_jarvis",
            }
            resolved_name = alias_map.get(model_name.lower().strip(), model_name)

            if resolved_name in available:
                self._oww_key = resolved_name
                if resolved_name != model_name:
                    print(
                        f"[listener] Wake word '{model_name}' not available; "
                        f"using '{resolved_name}'"
                    )
                else:
                    print(f"[listener] Wake word loaded: '{resolved_name}'")
            elif available:
                self._oww_key = available[0]
                print(
                    f"[listener] Wake word '{model_name}' not found. "
                    f"Using '{self._oww_key}' from available models."
                )
            else:
                print("[listener] openwakeword loaded but no models are available")
                self._oww_model = None

        except Exception as e:
            print(f"[listener] Wake word unavailable ({e}) — push-to-talk still works")
            self._oww_model = None

        # ── Whisper STT ───────────────────────────────────────────────────────
        try:
            from faster_whisper import WhisperModel
            self._whisper = WhisperModel(
                config.WHISPER_MODEL,
                device="cpu",
                compute_type="int8",
            )
            print("[listener] faster-whisper loaded")
        except Exception as e:
            self.on_error(f"Whisper model failed to load: {e}")
            return False

        return True

    def _record_utterance(self, stream) -> np.ndarray:
        """Record audio until silence. Returns float32 audio array."""
        self.on_listening_start()
        frames: list[np.ndarray] = []
        silent_chunks = 0

        while self._running:
            data  = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            chunk = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            frames.append(chunk)

            energy = np.sqrt(np.mean(chunk ** 2))
            if energy < 0.005:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks >= SILENCE_CHUNKS and len(frames) > 10:
                break

        self.on_listening_stop()
        return np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)

    def _transcribe(self, audio: np.ndarray) -> tuple[str, str]:
        """Transcribe float32 audio array. Returns (text, language)."""
        if len(audio) < SAMPLE_RATE * 0.3:
            return "", "en"

        segments, info = self._whisper.transcribe(
            audio,
            beam_size=5,
            language=None,
            vad_filter=True,
        )
        text = " ".join(seg.text for seg in segments).strip()
        lang = info.language if info.language in ("en", "ru") else "en"
        return text, lang

    def _run(self):
        """Main listener loop — runs in a background daemon thread."""
        try:
            import pyaudio
        except ImportError:
            self.on_error("pyaudio not installed. Run: pip install pyaudio --break-system-packages")
            return

        if not self._load_models():
            return

        pa     = pyaudio.PyAudio()
        stream = pa.open(
            rate=SAMPLE_RATE,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )

        if self._oww_model:
            print(f"[listener] Listening for wake word '{config.WAKE_WORD_MODEL}'...")
        else:
            print("[listener] Running in push-to-talk only mode (no wake word)")

        try:
            while self._running:
                data  = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                chunk = np.frombuffer(data, dtype=np.int16)

                if self._oww_model is None:
                    time.sleep(0.05)
                    continue

                pred  = self._oww_model.predict(chunk)

                # Use the resolved key (model stem), fall back to config name
                score = pred.get(self._oww_key, 0.0) or pred.get(config.WAKE_WORD_MODEL, 0.0)

                # If the key still doesn't match, grab the highest score
                if score == 0.0 and pred:
                    score = max(pred.values())

                if score >= config.WAKE_WORD_SCORE:
                    print(f"[listener] Wake word detected (score={score:.2f})")
                    self.on_wake()
                    self._oww_model.reset()

                    audio = self._record_utterance(stream)
                    if len(audio) > 0:
                        text, lang = self._transcribe(audio)
                        if text:
                            print(f"[listener] Transcript [{lang}]: {text}")
                            self.on_transcript(text, lang)

        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def start(self):
        """Start the listener in a background daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the listener thread."""
        self._running = False

    def transcribe_once(self, audio_array: np.ndarray) -> tuple[str, str]:
        """
        Transcribe a pre-recorded numpy array (int16 or float32, 16kHz).
        Used for the push-to-talk mic button in the UI.
        Returns (text, language).
        """
        if self._whisper is None:
            try:
                from faster_whisper import WhisperModel
                self._whisper = WhisperModel(
                    config.WHISPER_MODEL, device="cpu", compute_type="int8"
                )
            except Exception:
                return "", "en"

        if audio_array.dtype == np.int16:
            audio_array = audio_array.astype(np.float32) / 32768.0

        return self._transcribe(audio_array)