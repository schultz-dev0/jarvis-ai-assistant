"""
config.py
---------
Central configuration for Sasha assistant.
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

# ── Settings file auto-load ───────────────────────────────────────────────────
# Reads ~/.config/jarvis/settings.env before any os.environ.get() call so that
# user values set there are picked up automatically.
_settings_file = JARVIS_CONFIG_DIR / "settings.env"
if _settings_file.exists():
	try:
		for _line in _settings_file.read_text(encoding="utf-8").splitlines():
			_line = _line.strip()
			if _line and not _line.startswith("#") and "=" in _line:
				_k, _, _v = _line.partition("=")
				os.environ.setdefault(_k.strip(), _v.strip())
	except Exception:
		pass

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
# openwakeword model name — legacy voice trigger setting
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
# Lets you talk to the assistant from any device on your local network via browser.
# Access at http://<your-pc-ip>:MOBILE_SERVER_PORT
MOBILE_SERVER_ENABLED = os.environ.get("MOBILE_SERVER_ENABLED", "true").lower() == "true"
MOBILE_SERVER_PORT    = int(os.environ.get("MOBILE_SERVER_PORT", "7123"))
# Optional: restrict to specific IP (leave blank to allow all LAN connections)
MOBILE_SERVER_HOST    = os.environ.get("MOBILE_SERVER_HOST", "0.0.0.0")

# ── Memory / Learning ─────────────────────────────────────────────────────────
MEMORY_ENABLED        = True
# Keep a larger rolling window for long-term recall
MEMORY_MAX_INTERACTIONS = 2000
# Retain dated memory records for this many days
MEMORY_RETENTION_DAYS   = 3650
# How many most-recent timestamped facts to inject into prompts
MEMORY_RECENT_FACTS_LIMIT = 8
# Inject memory context into LLM prompts
MEMORY_INJECT_CONTEXT   = True

# ── UI ────────────────────────────────────────────────────────────────────────
WINDOW_DEFAULT_WIDTH  = 480
WINDOW_DEFAULT_HEIGHT = 720
WINDOW_TITLE          = "Sasha"
ASSISTANT_NAME        = "Sasha"

# ── Telegram bot ──────────────────────────────────────────────────────────────
# Get a token from @BotFather on Telegram, then set it in settings.env:
#   TELEGRAM_BOT_TOKEN=123456:ABC-...
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ── Bridge security ───────────────────────────────────────────────────────────
# Shared secret between the VPS Brain and local Satellite.
# Generate one with:  python3 -c "import secrets; print(secrets.token_hex(32))"
# Set on VPS in /etc/sasha/env and locally in ~/.config/jarvis/settings.env.
SASHA_BRIDGE_TOKEN = os.environ.get("SASHA_BRIDGE_TOKEN", "")

# Invocation aliases the assistant should respond to (text/command prefix)
ASSISTANT_ALIASES_EN = ("sasha", "alex", "sanya", "alexander")
ASSISTANT_ALIASES_RU = ("саня", "санек", "саша", "леха")

# Optional prompt customisation. These can be set in settings.env.
# JARVIS_SYSTEM_PROMPT applies to all languages.
# JARVIS_SYSTEM_PROMPT_EN / JARVIS_SYSTEM_PROMPT_RU apply per language.
SYSTEM_PROMPT_FILE = JARVIS_CONFIG_DIR / "system_prompt.txt"
SYSTEM_PROMPT_GLOBAL = os.environ.get("JARVIS_SYSTEM_PROMPT", "").strip()
SYSTEM_PROMPT_EN = os.environ.get("JARVIS_SYSTEM_PROMPT_EN", "").strip()
SYSTEM_PROMPT_RU = os.environ.get("JARVIS_SYSTEM_PROMPT_RU", "").strip()