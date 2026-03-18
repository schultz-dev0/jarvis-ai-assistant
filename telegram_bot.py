"""
telegram_bot.py
---------------
Telegram bot interface for the Sasha assistant.

Standalone:   python telegram_bot.py
Integrated:   start_telegram_bot() is called from main.py at startup.

Setup:
  1. Message @BotFather on Telegram → /newbot → copy the token.
  2. Add  TELEGRAM_BOT_TOKEN=<token>  to ~/.config/jarvis/settings.env
  3. Restart Sasha (or run standalone).
"""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from datetime import datetime, timedelta

import config

# ── Constants ─────────────────────────────────────────────────────────────────
_HISTORY_MAX    = 12    # max turns to keep per chat for multi-turn context
_HISTORY_TTL_H  = 24    # drop history after this many idle hours
_TG_CHAR_LIMIT  = 4096  # Telegram maximum message length

# ── Per-chat state ────────────────────────────────────────────────────────────
_histories: dict[int, list[tuple[str, str]]] = defaultdict(list)
_last_seen:  dict[int, datetime] = {}


# ── History helpers ───────────────────────────────────────────────────────────

def _get_history(chat_id: int) -> list[tuple[str, str]]:
    last = _last_seen.get(chat_id)
    if last and (datetime.utcnow() - last) > timedelta(hours=_HISTORY_TTL_H):
        _histories.pop(chat_id, None)
        _last_seen.pop(chat_id, None)
    return list(_histories[chat_id])


def _push_history(chat_id: int, role: str, text: str) -> None:
    hist = _histories[chat_id]
    hist.append((role, text))
    _histories[chat_id] = hist[-_HISTORY_MAX:]
    _last_seen[chat_id] = datetime.utcnow()


def _split_reply(text: str) -> list[str]:
    """Split long text into Telegram-sized chunks, breaking on newlines."""
    if len(text) <= _TG_CHAR_LIMIT:
        return [text]
    parts: list[str] = []
    while text:
        if len(text) <= _TG_CHAR_LIMIT:
            parts.append(text)
            break
        cut = text.rfind("\n", 0, _TG_CHAR_LIMIT)
        cut = cut if cut > 0 else _TG_CHAR_LIMIT
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts


# ── Command handlers ──────────────────────────────────────────────────────────

async def _cmd_start(update, context) -> None:
    cid = update.effective_chat.id
    _histories.pop(cid, None)
    _last_seen.pop(cid, None)
    name = config.ASSISTANT_NAME
    await update.message.reply_text(
        f"Hi! I'm {name}, your personal desktop assistant.\n\n"
        "Send me any message — commands, questions, or just chat.\n"
        "I speak English and Russian.\n\n"
        "• /help — what I can do\n"
        "• /clear — reset conversation"
    )


async def _cmd_clear(update, context) -> None:
    cid = update.effective_chat.id
    _histories.pop(cid, None)
    _last_seen.pop(cid, None)
    await update.message.reply_text("Conversation cleared.")


async def _cmd_help(update, context) -> None:
    name = config.ASSISTANT_NAME
    await update.message.reply_text(
        f"{name} — personal AI assistant\n\n"
        "What I can do:\n"
        "  • Open / close / find apps and files\n"
        "  • Weather, news, web search\n"
        "  • System info (CPU, RAM, disk)\n"
        "  • Volume, brightness, Wi-Fi, Bluetooth\n"
        "  • Date & time, calculator\n"
        "  • Remember facts about you\n"
        "  • Play / pause / skip / previous music track\n"
        "  • Phone via KDE Connect (SMS, ring, battery)\n"
        "  • General knowledge questions\n\n"
        "Commands:\n"
        "  /start — restart\n"
        "  /clear — clear conversation history\n"
        "  /help  — this message\n\n"
        "Examples:\n"
        "  weather in London\n"
        "  what's 15% of 240\n"
        "  open Firefox\n"
        "  remember my editor is neovim\n"
        "  news on AI safety"
    )


async def _handle_message(update, context) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return

    cid = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=cid, action="typing")

    history = _get_history(cid)
    _push_history(cid, "user", text)

    try:
        import brain
        import dispatcher as disp

        intent = await asyncio.to_thread(
            lambda: brain.parse_intent(text, history=history)
        )
        result = await asyncio.to_thread(
            lambda: disp.dispatch(intent, raw_input=text)
        )
        _push_history(cid, "assistant", result)

        if config.MEMORY_ENABLED:
            try:
                from skills.memory import extract_and_store_facts, record_interaction

                def _persist() -> None:
                    extract_and_store_facts(text, brain.detect_language(text))
                    record_interaction(
                        user_input=text,
                        action=intent.action,
                        target=intent.target,
                        result=result,
                        success=True,
                        lang=intent.language,
                    )

                await asyncio.to_thread(_persist)
            except Exception:
                pass

    except Exception as exc:
        result = f"Something went wrong: {exc}"
        _push_history(cid, "assistant", result)

    for part in _split_reply(result):
        await update.message.reply_text(part)


# ── Bot runner ────────────────────────────────────────────────────────────────

def _run_bot() -> None:
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("clear", _cmd_clear))
    app.add_handler(CommandHandler("help",  _cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))

    token_hint = config.TELEGRAM_BOT_TOKEN[-6:]
    print(f"[telegram] Bot polling started (token ...{token_hint})")
    app.run_polling(drop_pending_updates=True)


def start_telegram_bot() -> bool:
    """Launch the Telegram bot in a daemon thread. Returns True if started."""
    if not config.TELEGRAM_BOT_TOKEN:
        print("[telegram] TELEGRAM_BOT_TOKEN not set — bot disabled")
        return False
    threading.Thread(target=_run_bot, daemon=True, name="telegram-bot").start()
    return True


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if not config.TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN is not set.")
        print("Set it in ~/.config/jarvis/settings.env or as an environment variable.")
        sys.exit(1)

    _run_bot()
