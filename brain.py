"""Compatibility shim. The VPS Brain now lives in server/brain.py."""

from server.brain import (  # noqa: F401
    JarvisIntent,
    SashaIntent,
    check_groq_alive,
    check_ollama_alive,
    detect_language,
    ensure_ollama_model_available,
    get_active_backend,
    parse_intent,
)
