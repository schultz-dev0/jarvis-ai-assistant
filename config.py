"""
config.py
---------
Central configuration for Jarvis.
All user-tweakable settings live here.
"""

from pathlib import Path
import os

# ── Paths ────────────────────────────────────────────────────────────────────
HOME              = Path.home()
JARVIS_DATA_DIR   = HOME / ".local" / "share" / "jarvis"
JARVIS_CONFIG_DIR = HOME / ".config" / "jarvis"
MATUGEN_CSS       = HOME / ".config" / "matugen" / "generated" / "colors.css"
VOICES_DIR        = JARVIS_DATA_DIR / "voices"
LOG_FILE          = JARVIS_DATA_DIR / "jarvis.log"
MEMORY_FILE       = JARVIS_DATA_DIR / "memory.json"

# ── LLM (Ollama — primary) ────────────────────────────────────────────────────
OLLAMA_BASE_URL   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL      = os.environ.get("OLLAMA_MODEL",    "llama3.2:3b")

# ── LLM (Groq — cloud fallback, free tier) ───────────────────────────────────
# Get a free API key at https://console.groq.com (no credit card required)
# Free tier: 14,400 requests/day, ~6,000 tokens/min on llama3-8b-8192
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL        = os.environ.get("GROQ_MODEL",   "llama3-8b-8192")
GROQ_BASE_URL     = "https://api.groq.com/openai/v1"

# ── Whisper STT ──────────────────────────────────────────────────────────────
# "tiny" = fastest, "base" = good balance, "small" = best accuracy
WHISPER_MODEL     = "base"
# Silence threshold for auto-stopping recording (seconds)
SILENCE_DURATION  = 1.8

# ── Wake Word ─────────────────────────────────────────────────────────────────
# openwakeword model name — "jarvis" community model
WAKE_WORD_MODEL   = "jarvis"
WAKE_WORD_SCORE   = 0.6          # detection confidence threshold (0-1)

# ── TTS (Piper) ───────────────────────────────────────────────────────────────
# Voices are auto-downloaded by install.sh into VOICES_DIR
TTS_VOICE_EN      = VOICES_DIR / "en_US-hfc_female-medium.onnx"
TTS_VOICE_RU      = VOICES_DIR / "ru_RU-ruslan-medium.onnx"
TTS_SPEED         = 1.0          # speech rate multiplier

# ── Phone (KDE Connect) ───────────────────────────────────────────────────────
# Leave blank to auto-detect first paired device
KDECONNECT_DEVICE = os.environ.get("KDECONNECT_DEVICE", "")

# ── Web ───────────────────────────────────────────────────────────────────────
WEATHER_LOCATION  = os.environ.get("WEATHER_LOCATION", "")   # blank = auto IP
# News is fully query-driven via DuckDuckGo — no sources to configure here.

# ── Mobile Server (WiFi access from phone/tablet) ────────────────────────────
# Lets you talk to Jarvis from any device on your local network via browser.
# Access at http://<your-pc-ip>:MOBILE_SERVER_PORT
MOBILE_SERVER_ENABLED = os.environ.get("MOBILE_SERVER_ENABLED", "true").lower() == "true"
MOBILE_SERVER_PORT    = int(os.environ.get("MOBILE_SERVER_PORT", "7123"))
# Optional: restrict to specific IP (leave blank to allow all LAN connections)
MOBILE_SERVER_HOST    = os.environ.get("MOBILE_SERVER_HOST", "0.0.0.0")

# ── Memory / Learning ─────────────────────────────────────────────────────────
MEMORY_ENABLED        = True
# How many recent interactions to keep
MEMORY_MAX_INTERACTIONS = 100
# Inject memory context into LLM prompts
MEMORY_INJECT_CONTEXT   = True

# ── UI ────────────────────────────────────────────────────────────────────────
WINDOW_DEFAULT_WIDTH  = 480
WINDOW_DEFAULT_HEIGHT = 720
WINDOW_TITLE          = "Jarvis"
ASSISTANT_NAME        = "Jarvis"