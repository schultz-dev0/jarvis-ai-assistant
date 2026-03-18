# JARVIS — Personal AI Assistant

A local-first, privacy-respecting AI assistant for Arch Linux / Hyprland.
Voice-activated, bilingual (English + Russian), with a GTK4 UI, mobile browser
access over WiFi, filesystem awareness, and a persistent learning system.

```
          ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
          ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
          ██║███████║██████╔╝██║   ██║██║███████╗
     ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
     ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
      ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
```

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [File Structure](#file-structure)
4. [Configuration Reference](#configuration-reference)
5. [Module Reference](#module-reference)
   - [main.py](#mainpy)
   - [brain.py](#brainpy)
   - [dispatcher.py](#dispatcherpy)
   - [tts.py](#ttspy)
   - [listener.py](#listenerpy)
   - [mobile_server.py](#mobile_serverpy)
   - [skills/apps.py](#skillsappspy)
   - [skills/system.py](#skillssystempy)
   - [skills/web.py](#skillswebpy)
   - [skills/phone.py](#skillsphonepy)
   - [skills/files.py](#skillsfilespy)
   - [skills/memory.py](#skillsmemorypy)
   - [skills/proactive.py](#skillsproactivepy)
   - [ui/window.py](#uiwindowpy)
   - [ui/style.py](#uistylepy)
6. [All Voice Commands](#all-voice-commands)
7. [Intent Action Reference](#intent-action-reference)
8. [Adding a New Skill](#adding-a-new-skill)
9. [Adding a New Voice Command](#adding-a-new-voice-command)
10. [LLM Backend Guide](#llm-backend-guide)
11. [Memory and Learning System](#memory-and-learning-system)
12. [Filesystem Search Tuning](#filesystem-search-tuning)
13. [Mobile Access](#mobile-access)
14. [Proactive Notifications](#proactive-notifications)
15. [Data Files Reference](#data-files-reference)
16. [Dependencies](#dependencies)
17. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Clone and enter the repo
git clone <your-repo> ~/jarvis
cd ~/jarvis

# 2. Run the installer (Arch Linux)
chmod +x install.sh
./install.sh

# 3. (Optional) Set your Groq API key for cloud fallback
#    Get a free key at https://console.groq.com — no credit card required
echo "GROQ_API_KEY=gsk_your_key_here" >> ~/.config/jarvis/settings.env

# 4. Start Jarvis
python3 main.py

# 5. Or as a systemd service (auto-starts with desktop session)
systemctl --user start jarvis
```

**Wake word:** say `"Jarvis"` out loud, or click the 🎙 button.
**Phone access:** open `http://<your-pc-ip>:7123` in your phone's browser.

---

## Architecture Overview

```
User input (voice / keyboard / mobile)
          │
          ▼
    listener.py          ← Wake word (openwakeword) + STT (faster-whisper)
          │
          ▼
      brain.py           ← NLP → JarvisIntent  (Ollama → Groq → rule-based)
          │
          ▼
   dispatcher.py         ← Routes intent to the right skill
          │
    ┌─────┴──────┬──────────┬───────────┬──────────┬──────────┐
    ▼            ▼          ▼           ▼          ▼          ▼
apps.py     system.py   web.py      phone.py   files.py  memory.py
(open apps) (vol/bright) (weather/  (KDE      (find &   (learning)
                          news)      Connect)   open)
          │
          ▼
       tts.py             ← Text-to-speech (Piper)
          │
          ▼
   ui/window.py           ← GTK4 chat window
          │
          ▼
  mobile_server.py        ← FastAPI server → phone browser
```

### Request flow in detail

1. `listener.py` detects the wake word → records audio → transcribes with Whisper
2. OR the user types in `ui/window.py`
3. OR a command arrives via WebSocket from `mobile_server.py`
4. All three paths call `main.py → _handle_text(text)`
5. `_handle_text` appends to `self._history`, calls `brain.parse_intent(text, history)`
6. `brain.py` tries Ollama, then Groq, then rule-based → returns a `JarvisIntent`
7. `dispatcher.py` routes the intent to the correct `skills/` module
8. The result string is shown in the UI, spoken by TTS, and pushed to mobile clients
9. `skills/memory.py` records the interaction for future personalisation

---

## File Structure

```
jarvis/
├── main.py                  Entry point, GTK app, conversation history
├── brain.py                 NLP intent parser (Ollama + Groq + fallback)
├── dispatcher.py            Routes intents to skills
├── config.py                All settings (edit this first)
├── listener.py              Wake word + Whisper STT
├── tts.py                   Piper text-to-speech
├── mobile_server.py         FastAPI WiFi server for phone access
├── install.sh               Full Arch Linux installer
├── install_piper.sh         Standalone Piper TTS installer
│
├── skills/
│   ├── apps.py              Open/close/focus applications
│   ├── system.py            Volume, brightness, WiFi, screenshots
│   ├── web.py               Weather, news, web search, datetime
│   ├── phone.py             KDE Connect — SMS, ring, battery, notifications
│   ├── files.py             Filesystem index, fuzzy file search, open files
│   ├── memory.py            Persistent learning and user fact storage
│   └── proactive.py         Background notifications (battery, news, calendar)
│
├── ui/
│   ├── __init__.py
│   ├── window.py            GTK4 chat window
│   └── style.py             Matugen-aware CSS theme loader
│
└── README.md                This file
```

**Runtime data** (created automatically, never commit these):
```
~/.config/jarvis/settings.env     User configuration overrides
~/.local/share/jarvis/
    memory.json                   Learned facts, usage stats, interaction log
    watched_topics.json           News topics to watch proactively
    voices/                       Piper .onnx voice models
    piper/                        Piper binary
    jarvis.log                    Log file
```

---

## Configuration Reference

All settings live in `config.py`. User overrides go in
`~/.config/jarvis/settings.env` (loaded as environment variables by the
systemd service). Environment variables always take precedence.

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Local model to use |
| `GROQ_API_KEY` | *(empty)* | Cloud fallback key — get free at console.groq.com |
| `GROQ_MODEL` | `llama3-8b-8192` | Groq model name |
| `WHISPER_MODEL` | `base` | STT accuracy: `tiny` / `base` / `small` / `medium` |
| `SILENCE_DURATION` | `1.8` | Seconds of silence before recording stops |
| `WAKE_WORD_MODEL` | `jarvis` | openwakeword model name |
| `WAKE_WORD_SCORE` | `0.6` | Detection confidence threshold (0–1) |
| `TTS_VOICE_EN` | `...hfc_female-medium.onnx` | English Piper voice path |
| `TTS_VOICE_RU` | `...ruslan-medium.onnx` | Russian Piper voice path |
| `TTS_SPEED` | `1.0` | Speech rate multiplier |
| `KDECONNECT_DEVICE` | *(auto-detect)* | Phone device ID |
| `WEATHER_LOCATION` | *(empty)* | Default city for weather queries |
| `MOBILE_SERVER_ENABLED` | `true` | Enable/disable WiFi server |
| `MOBILE_SERVER_PORT` | `7123` | Port for mobile server |
| `MOBILE_SERVER_HOST` | `0.0.0.0` | Bind address (restrict to `192.168.x.x` for security) |
| `MEMORY_ENABLED` | `True` | Enable learning system |
| `MEMORY_MAX_INTERACTIONS` | `100` | How many past interactions to keep |
| `MEMORY_INJECT_CONTEXT` | `True` | Inject learned facts into LLM prompts |
| `JARVIS_SYSTEM_PROMPT` | *(empty)* | Extra global system prompt instructions |
| `JARVIS_SYSTEM_PROMPT_EN` | *(empty)* | Extra English-only system prompt instructions |
| `JARVIS_SYSTEM_PROMPT_RU` | *(empty)* | Extra Russian-only system prompt instructions |

**Example `~/.config/jarvis/settings.env`:**
```env
OLLAMA_MODEL=llama3.2:3b
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
WEATHER_LOCATION=London, England
KDECONNECT_DEVICE=abc123def456
MOBILE_SERVER_PORT=7123
WHISPER_MODEL=small
JARVIS_SYSTEM_PROMPT=Be concise and practical. Prefer actionable responses.
```

You can also put long-form system instructions in:

```text
~/.config/jarvis/system_prompt.txt
```

When `main.py` starts, Sasha now verifies Ollama availability and model presence.
If Ollama is down, it attempts to start it; if the configured model is missing,
it attempts to pull it automatically before enabling local inference.

---

## Module Reference

### main.py

The entry point and application controller.

**Class: `JarvisApp(Gtk.Application)`**

Orchestrates all subsystems. Key attributes:

| Attribute | Type | Purpose |
|---|---|---|
| `self._history` | `list[tuple[str,str]]` | Rolling conversation history, capped at `MAX_HISTORY=12` |
| `self._mic_recording` | `threading.Event` | Controls the push-to-talk recording loop (set=recording, clear=stop) |
| `self._processing` | `threading.Event` | Prevents overlapping LLM calls |

**Key methods:**

`_handle_text(text: str)`
The central command processor. Called from the keyboard handler, voice
transcription callback, and mobile WebSocket handler.
Sequence: adds to history → extracts facts → calls `brain.parse_intent(text, history)` →
calls `dispatcher.dispatch(intent)` → updates UI, mobile clients, TTS, and memory.

`_voice_start()` / `_voice_stop()`
Push-to-talk handlers. `_voice_start` opens a PyAudio stream and reads chunks
into `self._mic_audio` while `self._mic_recording` is set.
`_voice_stop` clears `self._mic_recording`, waits 80ms for the last read to
finish, then closes the stream cleanly. This ordering is critical — clearing
the event before closing the stream prevents a race condition crash.

`_startup_tasks()`
Runs in a background thread on activate: checks LLM backends, starts the mobile
server, starts the proactive loop, and pre-builds the file index.

`_on_wake_word()`
Detects the last used language from history and speaks "Yes?" or "Да?" accordingly.

---

### brain.py

Converts natural language to a structured `JarvisIntent` using the LLM.

**Class: `JarvisIntent(BaseModel)`**

Pydantic model representing a parsed command:

| Field | Type | Description |
|---|---|---|
| `action` | `str` | One of the supported action strings (see [Intent Action Reference](#intent-action-reference)) |
| `target` | `str \| None` | Primary subject (app name, city, file keywords, news topic, etc.) |
| `value` | `str \| None` | Secondary parameter (volume level, message text, app override, etc.) |
| `language` | `str` | `"en"` or `"ru"` — always set by Python, never trusted from the LLM |
| `reply` | `str` | Short Jarvis-style acknowledgement sentence (1–2 sentences) |

**Key functions:**

`detect_language(text: str) -> str`
Detects language by scanning for Cyrillic characters. Returns `"ru"` or `"en"`.
This is done in Python, not by the LLM, for reliability.

`parse_intent(user_input: str, history: list[tuple[str,str]] | None = None) -> JarvisIntent`
Main public API. Tries Ollama → Groq → rule-based fallback in order.
Automatically injects memory context into the system prompt if `MEMORY_ENABLED`.
`history` should be the recent conversation as `[("user","..."), ("assistant","..."), ...]`
tuples, which are appended to the LLM message array for multi-turn context.

`check_ollama_alive() -> bool`
Quick health-check against the Ollama `/api/tags` endpoint. 3-second timeout.

`check_groq_alive() -> bool`
Checks Groq `/v1/models`. Returns `False` immediately if `GROQ_API_KEY` is unset.

`get_active_backend() -> str`
Returns a human-readable string like `"ollama:llama3.2:3b"` or `"groq:llama3-8b-8192"`.

**Editing the LLM prompts:**

The system prompts are `SYSTEM_PROMPT_EN` and `SYSTEM_PROMPT_RU` at the top of
`brain.py`. When adding a new action:
1. Add the action name to the `ACTIONS:` list in both prompts
2. Add a rule in the `RULES:` section explaining how to populate `target`/`value`
3. Add 1–2 `EXAMPLES:` entries showing exact JSON output

---

### dispatcher.py

Routes a `JarvisIntent` to the appropriate skill function.

**`dispatch(intent: JarvisIntent, raw_input: str = "") -> str`**

The only public function. Contains a large `if/elif` chain on `intent.action`.
Returns a final response string used for both TTS and UI display.

When adding a new action, add a new `elif action == "your_action":` block here
that calls the appropriate skill and returns a string.

The `raw_input` parameter is the original unmodified user text, available as a
fallback if `intent.target` and `intent.value` are both empty.

---

### tts.py

Text-to-speech using Piper. Runs in a background daemon thread.

**`start()`**
Starts the background TTS worker thread. Call once at startup.

**`speak(text: str)`**
Queues text for speech. Non-blocking. Clears any currently queued speech first
(interrupts), so the most recent response always plays.

**`is_speaking() -> bool`**
Returns `True` while Piper is actively synthesising/playing audio.

**`stop()`**
Sends a poison pill to the TTS worker thread to shut it down cleanly.

Language is detected from Cyrillic presence and selects either
`TTS_VOICE_EN` or `TTS_VOICE_RU` automatically. To use different voices,
update these paths in `config.py` — they must be `.onnx` Piper voice files.

---

### listener.py

Two-stage voice pipeline: wake word detection → speech recording → Whisper transcription.

**Class: `VoiceListener`**

Constructor callbacks (all optional):

| Callback | Signature | Called when |
|---|---|---|
| `on_wake` | `() -> None` | Wake word detected |
| `on_transcript` | `(text: str, lang: str) -> None` | Transcription complete |
| `on_listening_start` | `() -> None` | Recording started |
| `on_listening_stop` | `() -> None` | Recording stopped |
| `on_error` | `(msg: str) -> None` | Any error in the listener thread |

**`start()`** — starts the background listener thread.
**`stop()`** — stops the thread.
**`transcribe_once(audio_array: np.ndarray) -> tuple[str, str]`**
Transcribes a pre-recorded numpy array (int16 or float32, 16kHz).
Used by the push-to-talk button to transcribe mic button audio.
Returns `(text, language)`.

Wake word detection is optional — if openwakeword fails to load, the listener
logs a warning and continues. Push-to-talk will still work.

---

### mobile_server.py

FastAPI server providing browser-based access to Jarvis from any LAN device.

**`start_mobile_server(dispatch_fn=None)`**
Starts the server in a daemon thread. Safe to call from the GTK main thread.
Prints the access URL to stdout and the UI.

**`broadcast_message(text: str, msg_type: str = "reply")`**
Pushes a message to all connected WebSocket clients.
Call this from `main.py` whenever Jarvis produces a response so mobile clients
stay in sync with the desktop session.

**`get_local_ip() -> str`**
Returns the machine's LAN IP address.

**Endpoints:**

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves the self-contained mobile HTML UI |
| `/command` | POST | REST command: `{"text": "open firefox"}` → `{"reply": "..."}` |
| `/status` | GET | Returns backend status JSON |
| `/ws` | WebSocket | Real-time bidirectional chat |

The HTML UI (`_MOBILE_HTML`) is a self-contained single-page app embedded as a
string. It uses the Web Speech API for voice input (works on Chrome/Android
without any app install). Edit `_MOBILE_HTML` directly to change the mobile UI.

**Security note:** The server binds to `0.0.0.0` by default, accepting all LAN
connections. To restrict access, set `MOBILE_SERVER_HOST=192.168.1.x` in
`settings.env` to bind only to your specific network interface.

---

### skills/apps.py

Opens, closes, and focuses applications via `hyprctl dispatch exec`.

**`open_app(target: str) -> str`**
Resolves fuzzy name → executable via `APP_ALIASES` and `get_close_matches`,
then runs `hyprctl dispatch exec <exe>`. Falls back to direct `subprocess.Popen`
if not running under Hyprland.

**`close_app(target: str) -> str`**
Lists all open windows via `hyprctl clients -j`, finds matches by class/title,
closes each with `hyprctl dispatch closewindow address:...`.

**`focus_app(target: str) -> str`**
Brings a window to focus with `hyprctl dispatch focuswindow class:<exe>`.

**`list_open_apps() -> list[str]`**
Returns a list of currently open app class names.

**To add a new app alias:**
```python
# In skills/apps.py, add to APP_ALIASES:
APP_ALIASES: dict[str, str] = {
    ...
    "yourapp":  "your-binary-name",
    "your app": "your-binary-name",   # multi-word aliases work too
}

# For Russian aliases:
APP_ALIASES_RU: dict[str, str] = {
    ...
    "твоёприложение": "your-binary-name",
}
```

---

### skills/system.py

Controls system settings and utilities.

**`set_volume(value: str) -> str`**
`value`: `"up"`, `"down"`, `"mute"`, `"unmute"`, or an integer `0–150`.
Uses `wpctl` (PipeWire). No fallback currently — install `pipewire-pulse` if
`wpctl` is missing.

**`get_volume() -> str`**
Returns current volume string from `wpctl get-volume`.

**`set_brightness(value: str) -> str`**
`value`: `"up"`, `"down"`, or integer `0–100`.
Uses `brightnessctl`. Requires the user to be in the `video` group:
`sudo usermod -aG video $USER`.

**`toggle_wifi(value: str) -> str`**
`value`: `"on"`, `"off"`, or empty (toggles). Uses `nmcli radio wifi`.

**`screenshot(mode: str = "region") -> str`**
`mode`: `"region"` (select area with slurp) or `"full"` (entire screen).
Saves to `~/Pictures/Screenshots/` with timestamp filename.
Copies to clipboard via `wl-copy` if available.

**`get_system_info() -> dict`**
Returns a dict with `cpu`, `memory`, and `uptime` strings.

---

### skills/web.py

Web data retrieval. Requires internet access. No API keys needed.

**`get_weather(location: str | None = None, lang: str = "en") -> str`**
Fetches from `wttr.in` (free, no key). If `location` is `None`, uses
`config.WEATHER_LOCATION`. Falls back to a simpler one-line format if the JSON
endpoint fails. Returns a formatted weather string with temperature, feels-like,
humidity, and wind.

**`get_news(topic: str | None = None, lang: str = "en", max_items: int = 5) -> str`**
Searches DuckDuckGo News for `topic`. If `topic` is `None`, searches
`"breaking world news today"`. Deduplicates by title and formats results with
source and relative age. Returns a numbered list of headlines.

**`search_web(query: str, lang: str = "en") -> str`**
Two-stage: first tries DDG Instant Answer API for structured answers, then
falls back to `duckduckgo_search` text search. Returns the best result trimmed
to 400 characters.

**`get_datetime(lang: str = "en") -> str`**
Returns the current local time and date as a string. No network required.

---

### skills/phone.py

Phone integration via KDE Connect.

**Prerequisites:**
1. Install `kdeconnect` on your PC: `sudo pacman -S kdeconnect`
2. Install the KDE Connect app on your Android phone (Play Store or F-Droid)
3. Pair via `kdeconnect-app` on the desktop
4. (Optional) Set `KDECONNECT_DEVICE` in `settings.env` to skip auto-detection

**`send_sms(contact: str, message: str) -> str`**
Sends an SMS via your paired phone. `contact` must be a phone number (e.g.
`"+447911123456"`). Name resolution is not supported — the function will tell
you to provide a number if a name is given.

**`ring_phone() -> str`**
Makes the paired phone ring remotely. Useful for finding a lost phone.

**`get_battery(lang: str = "en") -> str`**
Returns the phone's current battery percentage string.

**`get_notifications(lang: str = "en") -> str`**
Lists pending notifications from the phone (requires notification access
permission granted in the KDE Connect Android app).

**`send_file(filepath: str) -> str`**
Sends a file to the paired phone via KDE Connect.

---

### skills/files.py

Fuzzy filesystem search and file/directory operations.

**Index constants** (edit in `files.py` to tune performance):

| Constant | Default | Description |
|---|---|---|
| `HOME_MAX_DEPTH` | `5` | Depth of walk from `~/` |
| `CONFIG_MAX_DEPTH` | `4` | Depth of walk from `~/.config` |
| `INDEX_TTL` | `120` | Seconds before rebuilding the index |
| `EXCLUDED_DIRS` | (see code) | Directory names that are skipped entirely |
| `OPENABLE_EXTENSIONS` | (see code) | File types included in the index |

**`find_and_open(query: str, lang: str = "en") -> str`**
Main entry point for `open_file` actions. Extracts keywords from the query,
scores all indexed files, opens the best match with `xdg-open` (or a specific
app if mentioned). If multiple results score similarly, lists the top 3 and
opens the best one.

**`find_files(query: str, max_results: int = 5) -> list[FileEntry]`**
Returns a ranked list of `FileEntry` objects without opening anything.
Used by the `find_file` action to list matches for the user to choose from.

**`list_directory(path_str: str, lang: str = "en") -> str`**
Lists the contents of a directory. Supports `~` expansion and relative names
(e.g. `"Downloads"` resolves to `~/Downloads`). Shows directories first, then
files, capped at 25 items.

**`search_files_by_name(pattern: str, lang: str = "en") -> str`**
Exact substring search on filenames. Returns a list of matching paths.

**`get_file_info(query: str, lang: str = "en") -> str`**
Finds a file and returns its path, size, and last-modified date.

**`invalidate_index()`**
Forces the index to rebuild on the next search. Call this if you've created or
deleted important files and want Jarvis to see them immediately.

**How scoring works:**
Each keyword is scored against the filename stem and every directory component
in the path using both exact substring matching (score: 0.85) and fuzzy
`SequenceMatcher` ratio (score: ratio × 0.8). A file that scores near-zero on
*any* keyword is penalised to 30% of its combined score, enforcing AND-logic
(all keywords should match somewhere in the path).

**Adding directories to the search scope:**
```python
# In skills/files.py, add to EXTRA_ROOTS:
EXTRA_ROOTS: list[Path] = [
    ...
    HOME / "your_custom_dir",
]
```

**Excluding a directory:**
```python
# In skills/files.py, add to EXCLUDED_DIRS:
EXCLUDED_DIRS: set[str] = {
    ...
    "your_large_dir_name",
}
```

---

### skills/memory.py

Persistent learning system. Stores data as JSON in `~/.local/share/jarvis/memory.json`.

**`record_interaction(user_input, action, target, result, success, lang)`**
Call after every dispatched command. Updates:
- `app_usage` counter for app-open commands
- `location_counts` and `preferred_location` for weather queries
- The `interactions` log (last `MEMORY_MAX_INTERACTIONS` entries)

**`store_fact(key: str, value: str)`**
Store an arbitrary user fact. Example:
```python
store_fact("user_name", "Alex")
store_fact("work_start", "9am")
store_fact("reminder_1", "2025-12-25 09:00|Wish family happy Christmas")
```
All stored facts are injected into LLM prompts as a `MEMORY CONTEXT` block.

**`store_correction(original: str, corrected: str)`**
Record when a user rephrases a failed command. Future calls that are similar
to `original` will be noted in context. (Currently stored but not yet used
to automatically retry — a good future enhancement.)

**`get_context_hint(lang: str = "en") -> str`**
Builds the memory context string injected into LLM prompts. Includes:
- Preferred weather city
- Top 4 most-used apps
- Up to 5 stored facts

**`extract_and_store_facts(user_input: str, lang: str = "en")`**
Scans natural language for self-disclosure patterns and auto-stores them:
- `"my name is Alex"` → `store_fact("user_name", "Alex")`
- `"I live in Manchester"` → `store_fact("user_city", "Manchester")`
- `"I work at 9am"` → `store_fact("wake_time", "9am")`

**`get_top_apps(n: int = 5) -> list[str]`**
Returns the n most frequently opened app names.

**`get_preferred_location() -> str`**
Returns the most-used weather city, or empty string.

**`get_recent_summary(n: int = 5, lang: str = "en") -> str`**
Returns a formatted summary of the last n interactions.

**`wipe_memory()`**
Resets all memory to blank. Irreversible.

**Memory file structure (`memory.json`):**
```json
{
  "app_usage":          { "firefox": 42, "spotify": 18 },
  "preferred_location": "London, England",
  "location_counts":    { "London, England": 15, "New York": 3 },
  "facts":              { "user_name": "Alex", "user_city": "Manchester" },
  "corrections":        {},
  "interactions":       [ { "ts": 1234567890, "input": "...", "action": "...", ... } ],
  "schema_version":     1
}
```

---

### skills/proactive.py

Background thread that pushes notifications without the user asking.

**`start_proactive_loop(push_fn: Callable[[str, str], None])`**
Starts the daemon thread. `push_fn(text, lang)` is called to display/speak a
notification. In `main.py` this is wired to `window.add_message` + `tts.speak`.
Also broadcasts to all connected mobile clients automatically.

**Check intervals:**

| Check | Interval | What it does |
|---|---|---|
| Battery | 5 min | Warns if phone battery < 20% (max once per hour) |
| News | 30 min | Checks for new headlines on watched topics |
| Calendar | 10 min | Parses `.ics` files in `~/` for upcoming events |
| Reminders | 60 sec | Checks `memory.facts` for `reminder_N` keys |

**`add_watched_topic(topic: str)`**
Adds a topic to `~/.local/share/jarvis/watched_topics.json`. Topics are also
auto-populated from your recent `get_news` interactions in memory.

**Adding a new proactive check:**
1. Write a `_check_yourthing()` function
2. Add a `last_yourthing = 0.0` variable at the top of `_proactive_loop`
3. Add to the loop:
```python
if now - last_yourthing >= YOUR_INTERVAL:
    _check_yourthing()
    last_yourthing = now
```

---

### ui/window.py

GTK4 chat-style main window.

**`JarvisWindow(app, on_text_input, on_voice_start, on_voice_stop)`**

Constructor callbacks are called in worker threads (not the GTK main thread).

**`add_message(text: str, msg_type: str = MSG_JARVIS)`**
Adds a message bubble. Thread-safe — internally calls `GLib.idle_add`.
`msg_type` values: `MSG_USER`, `MSG_JARVIS`, `MSG_SYSTEM`.

**`set_status(text: str, state: str = "idle")`**
Updates the status bar and status dot colour.
`state` values: `"idle"`, `"listening"`, `"thinking"`, `"error"`.

**`set_thinking(thinking: bool)`**
Shortcut for `set_status("THINKING...", "thinking")` / `set_status("READY", "idle")`.

---

### ui/style.py

Loads colour tokens from Matugen's generated CSS and builds a GTK4 stylesheet.

**`load_colors() -> dict[str, str]`**
Reads `~/.config/matugen/generated/colors.css` and merges its `@define-color`
declarations over the built-in dark defaults. Safe to call if Matugen isn't
installed — defaults are used automatically.

**`build_css(colors: dict) -> str`**
Generates the complete GTK CSS from a colour dict. To change the UI appearance,
edit the CSS strings in this function or override colours in your Matugen config.

**`get_stylesheet() -> str`**
Calls `load_colors()` then `build_css()`. Called once at window creation.

---

## All Voice Commands

### Apps
| Say | Action |
|---|---|
| `"open firefox"` | Opens Firefox |
| `"launch spotify"` | Opens Spotify |
| `"close discord"` | Closes Discord windows |
| `"focus terminal"` | Brings terminal to front |

### Files & Filesystem
| Say | Action |
|---|---|
| `"open the vscode matugen template"` | Searches filesystem and opens best match |
| `"find my hyprland config"` | Lists matching files, does not open |
| `"open my project notes in obsidian"` | Opens file with specific app |
| `"show me my Downloads"` | Lists ~/Downloads |
| `"what files are in my projects folder"` | Lists ~/projects |
| `"open the readme in the jarvis project"` | Opens best-matching README |

### System
| Say | Action |
|---|---|
| `"volume up"` / `"turn it up"` | Increases volume by 5% |
| `"volume down"` | Decreases volume by 5% |
| `"mute"` | Toggles mute |
| `"set volume to 60"` | Sets volume to 60% |
| `"brightness up"` | Increases brightness by 10% |
| `"brightness down"` | Decreases brightness by 10% |
| `"turn wifi off"` | Disables WiFi |
| `"take a screenshot"` | Region screenshot (select area) |
| `"take a full screenshot"` | Full screen screenshot |

### Weather & News
| Say | Action |
|---|---|
| `"what's the weather"` | Weather for default/detected location |
| `"weather in London"` | Weather for specific city |
| `"weather in Basildon Essex"` | Weather with region (more accurate) |
| `"what's the news"` | Top world headlines |
| `"news on Tesla"` | News on a specific topic |
| `"latest Ukraine news"` | News matching that topic exactly |
| `"search for quantum computing"` | Web search |

### Music
| Say | Action |
|---|---|
| `"play music"` | Opens Spotify |
| `"pause"` | Pauses playback via playerctl |
| `"next track"` | Skips to next track |
| `"set spotify volume to 40"` | Sets player volume |

### Phone (KDE Connect)
| Say | Action |
|---|---|
| `"ring my phone"` | Makes phone ring remotely |
| `"what's my phone battery"` | Reports phone battery % |
| `"show my notifications"` | Lists phone notifications |
| `"send a text to +447911123456 I'll be late"` | Sends SMS |

### Conversation
| Say | Action |
|---|---|
| `"what can you do"` | Lists capabilities |
| `"hi jarvis"` | General chat / greeting |
| Anything else | Routes to chat action — LLM replies directly |

### Multi-turn (conversation history)
These work because prior turns are passed to the LLM:
```
"Open Spotify"                         → opens Spotify
"Pause it"                             → pauses Spotify
"Turn it up to 80"                     → sets volume to 80%
"Take a screenshot and send it to mum" → (future — currently two steps)
```

---

## Intent Action Reference

Complete list of all supported action values returned by the LLM:

| Action | target | value | Skill |
|---|---|---|---|
| `open_app` | App name | — | `skills/apps.py` |
| `close_app` | App name | — | `skills/apps.py` |
| `focus_app` | App name | — | `skills/apps.py` |
| `set_volume` | — | `"up"` / `"down"` / `"mute"` / `"unmute"` / `"0-150"` | `skills/system.py` |
| `set_brightness` | — | `"up"` / `"down"` / `"0-100"` | `skills/system.py` |
| `toggle_wifi` | — | `"on"` / `"off"` | `skills/system.py` |
| `screenshot` | — | `"full"` / `""` | `skills/system.py` |
| `get_weather` | City name or null | — | `skills/web.py` |
| `get_news` | Topic or null | — | `skills/web.py` |
| `search_web` | Query | — | `skills/web.py` |
| `play_music` | — | — | `skills/apps.py` + playerctl |
| `pause_music` | — | — | playerctl |
| `next_track` | — | — | playerctl |
| `set_spotify_volume` | — | `"0-100"` | playerctl |
| `phone_sms` | Phone number | Message text | `skills/phone.py` |
| `phone_ring` | — | — | `skills/phone.py` |
| `phone_battery` | — | — | `skills/phone.py` |
| `phone_notify` | — | — | `skills/phone.py` |
| `open_file` | Search keywords | App override (optional) | `skills/files.py` |
| `find_file` | Search keywords | — | `skills/files.py` |
| `list_directory` | Directory name / path | — | `skills/files.py` |
| `chat` | — | — | LLM reply used directly |
| `unknown` | — | — | Error message |

---

## Adding a New Skill

### 1. Create the skill module

```python
# skills/myskill.py

def do_something(target: str, lang: str = "en") -> str:
    """Does something useful. Returns a spoken response string."""
    result = ...  # your logic here
    if lang == "ru":
        return f"Результат: {result}"
    return f"Result: {result}"
```

### 2. Register the action in the LLM prompt (`brain.py`)

```python
# In SYSTEM_PROMPT_EN, add to ACTIONS list:
ACTIONS: ..., my_action

# Add a rule if target/value need explanation:
# For my_action: put the thing in target, the modifier in value.

# Add an example:
User: "do something with widgets"
{"action": "my_action", "target": "widgets", "value": null, "language": "en", "reply": "On it."}
```

Do the same in `SYSTEM_PROMPT_RU`.

### 3. Route the action in `dispatcher.py`

```python
elif action == "my_action":
    from skills.myskill import do_something
    return do_something(target=target, lang=lang)
```

### 4. (Optional) Add to the intent action table in this README

That's it. No other files need touching.

---

## Adding a New Voice Command

If the new command maps to an **existing action** (e.g. opening a new app),
you only need to update `skills/apps.py`:

```python
APP_ALIASES["myapp"] = "myapp-binary"
```

If the new command needs its **own action**, follow [Adding a New Skill](#adding-a-new-skill).

If you want to teach the LLM to handle a new phrasing of an existing action,
add an example to the relevant system prompt in `brain.py`.

---

## LLM Backend Guide

### Ollama (local — default)

Runs entirely on your machine. Best for privacy.

```bash
# Install
curl -fsSL https://ollama.com/install.sh | sh

# Pull the default model (3B — fast on any CPU)
ollama pull llama3.2:3b

# Or a better model if you have the RAM
ollama pull llama3.1:8b    # ~8GB RAM
ollama pull llama3.1:70b   # ~40GB RAM — needs a good GPU

# Start the server
ollama serve

# Change the model Jarvis uses
echo "OLLAMA_MODEL=llama3.1:8b" >> ~/.config/jarvis/settings.env
```

**Performance tip:** The LLM is only parsing intent (classifying + extracting
entities), not generating long text. `llama3.2:3b` is sufficient and fast.
Bigger models won't significantly improve intent parsing accuracy.

### Groq (cloud fallback — free)

Activates automatically if Ollama is unreachable.

1. Sign up at [console.groq.com](https://console.groq.com) (no credit card)
2. Create an API key
3. Add to settings: `GROQ_API_KEY=gsk_your_key_here`

**Free tier limits:** 14,400 requests/day, ~6,000 tokens/minute on `llama3-8b-8192`.
For typical Jarvis usage this is effectively unlimited.

To change the Groq model:
```env
GROQ_MODEL=llama3-70b-8192    # higher quality, same free tier
GROQ_MODEL=mixtral-8x7b-32768 # alternative
```

### Adding a different cloud provider

The Groq integration in `brain.py` uses a standard OpenAI-compatible API.
Any provider with this API can be added by copying `_call_groq` and changing
the `base_url` and auth header. OpenRouter, Together AI, and Fireworks AI all
use the same format.

---

## Memory and Learning System

### What Jarvis learns automatically

| Data | How it's learned | How it's used |
|---|---|---|
| App usage frequency | Every `open_app` command | Top apps shown in memory context |
| Preferred weather city | Every `get_weather` command | Auto-fills blank weather queries |
| Your name | `"my name is X"` in speech | Personalises LLM replies |
| Your city | `"I live in X"` in speech | Used in weather and context |
| Watched news topics | Every `get_news` command | Proactive news alerts |
| Reminders | Via `store_fact("reminder_N", "YYYY-MM-DD HH:MM|message")` | Proactive alerts |

### Storing custom facts

You can store any fact programmatically or add a skill to let users say
`"remember that..."`:

```python
from skills.memory import store_fact
store_fact("user_name", "Alex")
store_fact("preferred_editor", "nvim")
store_fact("work_hours", "9am to 5pm")
```

### Inspecting memory

```bash
cat ~/.local/share/jarvis/memory.json | python3 -m json.tool
```

### Wiping memory

```python
from skills.memory import wipe_memory
wipe_memory()
```

Or simply delete the file:
```bash
rm ~/.local/share/jarvis/memory.json
```

---

## Filesystem Search Tuning

### It's finding the wrong file

The scoring system uses ALL keywords AND-style — a file missing any keyword is
penalised. Make your query more specific:

```
"open notes"                  → too vague, many matches
"open jarvis project notes"   → directory + filename keywords → much better
```

### It's slow on first search

The index walks `~/` up to 5 levels deep. If you have large directories of
small files (e.g. a massive `~/Documents`), add them to `EXCLUDED_DIRS` or
reduce `HOME_MAX_DEPTH` in `skills/files.py`.

### It's not finding files in a custom directory

Add the directory to `EXTRA_ROOTS`:
```python
EXTRA_ROOTS: list[Path] = [
    ...
    HOME / "my_custom_projects",
    Path("/opt/myapp/configs"),   # absolute paths work too
]
```

### Forcing a fresh index

```python
from skills.files import invalidate_index
invalidate_index()
```

---

## Mobile Access

1. Jarvis prints its URL at startup: `Mobile access: http://192.168.1.50:7123`
2. Open that URL in **Chrome on Android** (or any modern mobile browser)
3. Voice input requires Chrome — other browsers may not support Web Speech API
4. To add to your Android home screen: Chrome → Menu → "Add to Home screen"
   (creates a PWA-style shortcut that opens fullscreen)

**Commands sent from mobile also play through the desktop speakers** via TTS.

**To disable mobile server:**
```env
MOBILE_SERVER_ENABLED=false
```

**To change the port:**
```env
MOBILE_SERVER_PORT=8080
```

---

## Proactive Notifications

Jarvis will speak and display notifications for:

- **Low phone battery** (`< 20%`) — checked every 5 minutes
- **New headlines** on topics you've asked about — checked every 30 minutes
- **Calendar events** (if `.ics` files exist in `~/`) — checked every 10 minutes
- **Custom reminders** set via `memory.store_fact`

### Adding a news topic to watch

```python
from skills.proactive import add_watched_topic
add_watched_topic("AI regulation")
add_watched_topic("Arch Linux")
```

Or just ask Jarvis about it — topics you query are automatically watched.

### Setting a reminder

```python
from skills.memory import store_fact
store_fact("reminder_1", "2025-12-25 09:00|Wish family happy Christmas")
```

The reminder fires when the system clock is within 5 minutes of the specified time.

---

## Data Files Reference

| File | Contents | Created by |
|---|---|---|
| `~/.config/jarvis/settings.env` | User config overrides | `install.sh` |
| `~/.local/share/jarvis/memory.json` | Learning data, facts, interaction log | `skills/memory.py` |
| `~/.local/share/jarvis/watched_topics.json` | News topics to watch | `skills/proactive.py` |
| `~/.local/share/jarvis/voices/*.onnx` | Piper voice models | `install.sh` |
| `~/.local/share/jarvis/piper/piper` | Piper binary | `install.sh` |
| `~/.local/share/jarvis/jarvis.log` | Log file (not yet wired — future) | — |
| `~/.config/matugen/generated/colors.css` | Matugen theme colours | Matugen |
| `~/Pictures/Screenshots/` | Screenshot output | `skills/system.py` |

---

## Dependencies

### System packages (installed by `install.sh`)
```
python, python-pip, python-gobject, gtk4, libadwaita
portaudio, alsa-utils
kdeconnect
brightnessctl
grim, slurp, wl-clipboard
playerctl
curl, wget
```

### Python packages
```
faster-whisper       Whisper STT
openwakeword         Wake word detection
pyaudio              Microphone input
httpx                HTTP client (Ollama, Groq, web APIs)
pydantic             JarvisIntent schema validation
numpy                Audio array handling
duckduckgo_search    News and web search
fastapi              Mobile server
uvicorn              ASGI server for FastAPI
icalendar            (optional) Calendar .ics parsing
```

### External tools
```
ollama               Local LLM server
piper                TTS binary (~/.local/bin/piper)
```

---

## Troubleshooting

**Jarvis doesn't respond to wake word**
- Check openwakeword installed: `python3 -c "import openwakeword"`
- Push-to-talk (🎙 button) still works even if wake word is broken
- Try lowering `WAKE_WORD_SCORE` to `0.4` in `config.py`

**Voice input button doesn't work / crashes**
- Ensure `pyaudio` is installed: `pip install pyaudio --break-system-packages`
- Check microphone permissions and that a default input device is set
- Run `python3 main.py` from a terminal to see error output

**"Ollama not detected" on startup**
- Run `ollama serve` in a terminal
- Or enable the user service: `systemctl --user enable --now ollama`
- Set `GROQ_API_KEY` as a backup

**Piper not found / no audio output**
- Check `which piper` — should point to `~/.local/bin/piper`
- Re-run `install_piper.sh`
- Test manually: `echo "hello" | piper --model ~/.local/share/jarvis/voices/en_US-hfc_female-medium.onnx --output-raw | aplay -r 22050 -f S16_LE -t raw -`

**Mobile server not reachable from phone**
- Both devices must be on the same WiFi network
- Check firewall: `sudo ufw allow 7123` or equivalent
- Verify the server started: look for `Mobile access: http://...` in the UI

**File search returns wrong results**
- Use more specific keywords: `"open hyprland config"` → `"open hyprland dot config"`
- Check what's in the index: call `find_files("your query")` in a Python shell
- Run `invalidate_index()` if files were recently created

**Weather shows wrong city**
- Set `WEATHER_LOCATION=YourCity, Region` in `settings.env`
- For best accuracy include the region: `"London, England"` not just `"London"`

**Memory not persisting between sessions**
- Check `~/.local/share/jarvis/memory.json` exists and is readable
- Check `MEMORY_ENABLED = True` in `config.py`

---

## Hybrid Architecture (VPS Brain + Local Satellite)

This repository now includes a modular split that supports a public VPS Brain
and a private LAN Satellite (dial-out bridge, no inbound port forwarding).

### Folder Structure Map

```text
jarvis/
├── server/
│   ├── __init__.py
│   ├── brain.py            VPS NLP + intent parsing
│   ├── dispatcher.py       VPS dispatcher (sends action requests to Satellite)
│   ├── bridge.py           FastAPI WebSocket bridge (Satellite dials out)
│   ├── protocol.py         JSON envelope + message factories
│   ├── memory_store.py     VPS-persistent memory.json handling
│   └── run_server.py       VPS server entry point
├── satellite.py            Local client entry point (Arch/Hyprland)
├── satellite_executor.py   Local tool runtime + registry (skills execution)
├── brain.py                Compatibility shim -> server.brain
└── dispatcher.py           Compatibility shim for local/in-process mode
```

### JSON Protocol (Brain <-> Satellite)

All messages use the same envelope:

```json
{
    "protocol": "1.0",
    "id": "uuid",
    "ts": "2026-03-18T12:34:56.000000+00:00",
    "type": "message.type",
    "payload": {}
}
```

Satellite -> Brain message types:
- `satellite.hello`: startup identity + capabilities (`tools`, audio/ui flags)
- `satellite.status`: heartbeat/status updates
- `satellite.input_text`: user text from mic/keyboard/mobile (`text`, `language`, `source`)
- `satellite.audio_chunk`: reserved for streaming PCM/audio frames
- `satellite.action_result`: response to `brain.execute_action` (`request_id`, `ok`, `result`, `error`)

Brain -> Satellite message types:
- `brain.execute_action`: tool call request (`tool`, `arguments`, `intent_action`)
- `brain.speak_text`: TTS output request (`text`, `language`)
- `brain.ui_update`: UI status/output update (`text`, `level`)
- `brain.ping`: heartbeat probe

Example action request:

```json
{
    "protocol": "1.0",
    "id": "8cae5c9d-2b71-4a88-95ec-b467a548f17b",
    "ts": "2026-03-18T12:35:12.101112+00:00",
    "type": "brain.execute_action",
    "payload": {
        "tool": "system.set_volume",
        "arguments": {"value": "up"},
        "intent_action": "set_volume"
    }
}
```

Example result:

```json
{
    "protocol": "1.0",
    "id": "9db7c4e2-76ac-4e55-a6de-f95d4d3ef643",
    "ts": "2026-03-18T12:35:12.302929+00:00",
    "type": "satellite.action_result",
    "payload": {
        "request_id": "8cae5c9d-2b71-4a88-95ec-b467a548f17b",
        "ok": true,
        "result": "Increasing volume."
    }
}
```

### Run Hybrid Mode

On VPS (Brain):

```bash
python3 -m server.run_server
```

On local Arch machine (Satellite):

```bash
export JARVIS_SATELLITE_ID=basildon-main
export JARVIS_BRIDGE_URL=ws://<vps-host>:8765/ws/satellite/basildon-main
python3 satellite.py
```

### Memory Modernization

In hybrid mode, memory is server-side and persistent on VPS via `server/memory_store.py`.
Set a dedicated location with:

```bash
export JARVIS_MEMORY_FILE=/var/lib/jarvis/memory.json
```

This ensures intent context + history are available even while local rigs are offline.

### Migration Guide: Skills Stay Local But Discoverable

1. Keep OS-touching skills on Satellite (`skills/apps.py`, `skills/system.py`, `skills/files.py`, etc.).
2. Register callable tool names in `satellite_executor.py` (`TOOL_REGISTRY`).
3. Ensure each tool has JSON-serializable arguments and returns a plain string.
4. Brain dispatcher (`server/dispatcher.py`) maps each intent action to a tool name + args.
5. Satellite announces available tools in `satellite.hello.payload.capabilities.tools`.
6. Brain can enforce capability checks before dispatching (future hardening).
7. To add a new skill:
     - Implement local function in `skills/<domain>.py`
     - Add it to `TOOL_REGISTRY` in `satellite_executor.py`
     - Add action mapping in `server/dispatcher.py`
     - Add prompt/examples in `server/brain.py` for reliable intent extraction
