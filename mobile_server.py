"""
mobile_server.py
----------------
FastAPI web server that lets you control Jarvis from any device
on your local network — phone, tablet, another PC.

Access at:  http://<your-pc-ip>:7123
Find your IP with: ip addr show | grep "inet "

Features:
  - Mobile-optimised web UI with chat interface
  - Web Speech API for voice input (Chrome/Android)
  - REST endpoint for text commands
  - WebSocket for real-time streamed responses
  - Shared conversation history with the desktop app

Usage (started automatically by main.py):
  from mobile_server import start_mobile_server, broadcast_message
  start_mobile_server(dispatch_fn)  # runs in background thread
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from typing import Callable

import config

# ── Lazy imports (only when server actually starts) ───────────────────────────
# Prevents import errors if fastapi/uvicorn aren't installed yet.
_app          = None
_active_ws    : list = []       # connected WebSocket clients
_dispatch_fn  : Callable | None = None
_loop         : asyncio.AbstractEventLoop | None = None


# ── HTML mobile client (self-contained single page) ──────────────────────────

_MOBILE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#1a1110">
<title>SASHA</title>
<style>
  :root {
    --bg:      #1a1110;
    --surface: #271d1c;
    --border:  #534341;
    --primary: #ffb4ab;
    --text:    #f1dedc;
    --muted:   #a08c8a;
    --user-bg: #73332d;
    --bot-bg:  #322826;
    --accent:  #e0c38c;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  /* Header */
  header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 14px 18px 10px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
  }
  .dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--muted);
    flex-shrink: 0;
    transition: background .3s;
  }
  .dot.active    { background: var(--primary); }
  .dot.listening { background: var(--accent); animation: pulse 1s infinite; }
  .dot.thinking  { background: #e7bdb8; animation: pulse .6s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  .header-text h1 {
    font-size: 18px; font-weight: 700;
    letter-spacing: 4px; color: var(--primary);
    font-family: monospace;
  }
  .header-text p {
    font-size: 10px; color: var(--muted);
    letter-spacing: 2px; margin-top: 1px;
  }
  /* Chat */
  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    -webkit-overflow-scrolling: touch;
  }
  .msg {
    max-width: 85%;
    padding: 10px 14px;
    border-radius: 18px;
    font-size: 14px;
    line-height: 1.5;
    word-break: break-word;
    animation: fadein .2s ease;
  }
  @keyframes fadein { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:none} }
  .msg.user   { background:var(--user-bg); align-self:flex-end; border-bottom-right-radius:4px; }
  .msg.jarvis { background:var(--bot-bg);  align-self:flex-start; border-bottom-left-radius:4px;
                border-left: 2px solid var(--primary); }
  .msg.system { background:transparent; color:var(--muted); font-style:italic;
                font-size:12px; align-self:center; }
  .msg .sender {
    font-size: 10px; font-weight: 700; letter-spacing: 1px;
    margin-bottom: 4px; opacity: .7;
  }
  .msg.user .sender   { color: var(--accent); }
  .msg.jarvis .sender { color: var(--primary); }
  /* Typing indicator */
  .typing { display:flex; gap:4px; padding:4px 0; }
  .typing span {
    width:7px; height:7px; border-radius:50%;
    background:var(--muted); animation: bounce .9s infinite;
  }
  .typing span:nth-child(2) { animation-delay:.2s }
  .typing span:nth-child(3) { animation-delay:.4s }
  @keyframes bounce { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)} }
  /* Input area */
  footer {
    background: var(--surface);
    border-top: 1px solid var(--border);
    padding: 10px 12px;
    display: flex;
    gap: 8px;
    align-items: center;
    flex-shrink: 0;
    padding-bottom: max(10px, env(safe-area-inset-bottom));
  }
  #input {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 22px;
    padding: 10px 16px;
    color: var(--text);
    font-size: 15px;
    outline: none;
    -webkit-appearance: none;
  }
  #input:focus { border-color: var(--primary); }
  .btn {
    width: 44px; height: 44px;
    border-radius: 50%;
    border: none;
    font-size: 18px;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    transition: transform .1s, opacity .2s;
    -webkit-tap-highlight-color: transparent;
  }
  .btn:active { transform: scale(.92); }
  #sendBtn { background: var(--primary); color: #561e19; }
  #micBtn  {
    background: transparent;
    color: var(--muted);
    border: 1px solid var(--border);
    font-size: 20px;
  }
  #micBtn.recording {
    background: var(--user-bg);
    color: var(--primary);
    border-color: var(--primary);
    animation: pulse .8s infinite;
  }
  /* Status */
  #statusBar {
    font-size: 11px;
    color: var(--muted);
    letter-spacing: 1px;
    padding: 0 18px 6px;
    text-align: center;
    flex-shrink: 0;
  }
</style>
</head>
<body>
<header>
  <div class="dot" id="dot"></div>
  <div class="header-text">
    <h1>SASHA</h1>
    <p id="backendLabel">CONNECTING...</p>
  </div>
</header>

<div id="chat"></div>
<div id="statusBar">READY</div>

<footer>
  <button class="btn" id="micBtn" title="Hold to speak">🎙</button>
  <input id="input" type="text" placeholder="Ask Sasha anything..."
         autocomplete="off" autocorrect="off" spellcheck="false">
  <button class="btn" id="sendBtn" title="Send">➤</button>
</footer>

<script>
const chat      = document.getElementById('chat');
const input     = document.getElementById('input');
const sendBtn   = document.getElementById('sendBtn');
const micBtn    = document.getElementById('micBtn');
const statusBar = document.getElementById('statusBar');
const dot       = document.getElementById('dot');
const backendLbl= document.getElementById('backendLabel');

let ws, typingEl, recognition, isRecording = false;

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    setStatus('CONNECTED', 'active');
    // Ask for backend info
    ws.send(JSON.stringify({type: 'ping'}));
  };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'reply') {
      removeTyping();
      addMessage('jarvis', msg.text);
      setStatus('READY', 'active');
    } else if (msg.type === 'thinking') {
      showTyping();
      setStatus('THINKING...', 'thinking');
    } else if (msg.type === 'backend') {
      backendLbl.textContent = msg.label.toUpperCase();
    } else if (msg.type === 'error') {
      removeTyping();
      addMessage('system', '⚠ ' + msg.text);
      setStatus('ERROR', '');
    }
  };

  ws.onclose = () => {
    setStatus('DISCONNECTED — retrying...', '');
    dot.className = 'dot';
    setTimeout(connect, 3000);
  };
}

// ── Messages ──────────────────────────────────────────────────────────────────
function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  if (role !== 'system') {
    const s = document.createElement('div');
    s.className = 'sender';
    s.textContent = role === 'user' ? 'YOU' : 'JARVIS';
    div.appendChild(s);
  }
  const t = document.createElement('div');
  t.textContent = text;
  div.appendChild(t);
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function showTyping() {
  if (typingEl) return;
  typingEl = document.createElement('div');
  typingEl.className = 'msg jarvis';
  typingEl.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
  chat.appendChild(typingEl);
  chat.scrollTop = chat.scrollHeight;
}

function removeTyping() {
  if (typingEl) { typingEl.remove(); typingEl = null; }
}

// ── Send ──────────────────────────────────────────────────────────────────────
function send() {
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== 1) return;
  input.value = '';
  addMessage('user', text);
  showTyping();
  setStatus('PROCESSING...', 'thinking');
  ws.send(JSON.stringify({type: 'command', text}));
}

sendBtn.onclick = send;
input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

// ── Status ────────────────────────────────────────────────────────────────────
function setStatus(text, state) {
  statusBar.textContent = text;
  dot.className = 'dot' + (state ? ' ' + state : '');
}

// ── Voice (Web Speech API — works on Chrome Android) ──────────────────────────
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US';   // auto switches to ru-RU on Cyrillic input

  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript;
    input.value = text;
    send();
  };
  recognition.onend = () => stopRecording();
  recognition.onerror = () => stopRecording();

  micBtn.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    if (!isRecording) startRecording();
  });
  micBtn.addEventListener('pointerup',   () => { if (recognition) recognition.stop(); });
  micBtn.addEventListener('pointerleave',() => { if (recognition) recognition.stop(); });
} else {
  // Web Speech not available — disable button with hint
  micBtn.title = 'Voice requires Chrome/Android';
  micBtn.style.opacity = '0.4';
}

function startRecording() {
  isRecording = true;
  micBtn.classList.add('recording');
  setStatus('LISTENING...', 'listening');
  recognition.start();
}

function stopRecording() {
  isRecording = false;
  micBtn.classList.remove('recording');
  setStatus('PROCESSING...', 'thinking');
}

// ── Init ──────────────────────────────────────────────────────────────────────
addMessage('system', 'SASHA MOBILE — connecting...');
connect();
</script>
</body>
</html>
"""


# ── FastAPI app factory ───────────────────────────────────────────────────────

def _build_app(dispatch_fn: Callable[[str], str]):
    global _dispatch_fn
    _dispatch_fn = dispatch_fn

    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse
        import uvicorn
    except ImportError:
        raise RuntimeError(
            "fastapi and uvicorn are required for the mobile server.\n"
            "Install with: pip install fastapi uvicorn --break-system-packages"
        )

    app = FastAPI(title="Sasha Mobile API", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return _MOBILE_HTML

    @app.post("/command")
    async def command(body: dict):
        """REST endpoint: POST {"text": "open firefox"} → {"reply": "..."}"""
        text = (body.get("text") or "").strip()
        if not text:
            return {"error": "empty command"}
        try:
            import brain, dispatcher
            intent = await asyncio.get_event_loop().run_in_executor(
                None, brain.parse_intent, text
            )
            reply = await asyncio.get_event_loop().run_in_executor(
                None, dispatcher.dispatch, intent, text
            )
            return {"reply": reply, "action": intent.action}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/status")
    async def status():
        import brain
        return {
            "backend": brain.get_active_backend(),
            "ollama":  brain.check_ollama_alive(),
            "groq_key_set": bool(config.GROQ_API_KEY),
        }

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        _active_ws.append(ws)
        # Send backend info on connect
        import brain
        try:
            await ws.send_json({"type": "backend", "label": brain.get_active_backend()})
        except Exception:
            # Silently drop if send fails on connection
            if ws in _active_ws:
                _active_ws.remove(ws)
            return
        
        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)

                if msg.get("type") == "ping":
                    try:
                        await ws.send_json({"type": "pong"})
                    except Exception:
                        break  # Connection lost, exit loop
                    continue

                if msg.get("type") == "command":
                    text = (msg.get("text") or "").strip()
                    if not text:
                        continue

                    # Acknowledge — show thinking indicator
                    try:
                        await ws.send_json({"type": "thinking"})
                    except Exception:
                        break  # Connection lost

                    # Run in thread pool so we don't block the event loop
                    loop = asyncio.get_event_loop()
                    try:
                        import brain, dispatcher
                        intent = await loop.run_in_executor(None, brain.parse_intent, text)
                        reply  = await loop.run_in_executor(None, dispatcher.dispatch, intent, text)
                        
                        try:
                            await ws.send_json({"type": "reply", "text": reply})
                        except Exception:
                            break  # Connection lost

                        # Also speak on the desktop
                        try:
                            import tts
                            tts.speak(reply)
                        except Exception:
                            pass

                    except Exception as e:
                        try:
                            await ws.send_json({"type": "error", "text": str(e)})
                        except Exception:
                            break  # Connection lost sending error

        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            if ws in _active_ws:
                _active_ws.remove(ws)

    return app, uvicorn


# ── Public API ────────────────────────────────────────────────────────────────

def broadcast_message(text: str, msg_type: str = "reply"):
    """
    Push a message to all connected mobile WebSocket clients.
    Call this from main.py so mobile clients see desktop responses too.
    """
    if not _active_ws or not _loop:
        return
    payload = json.dumps({"type": msg_type, "text": text})
    asyncio.run_coroutine_threadsafe(_broadcast(payload), _loop)


async def _broadcast(payload: str):
    dead = []
    for ws in list(_active_ws):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _active_ws:
            _active_ws.remove(ws)


def get_local_ip() -> str:
    """Return the machine's LAN IP so the user knows where to connect."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_mobile_server(dispatch_fn: Callable[[str], str] | None = None):
    """
    Start the mobile server in a background daemon thread.
    Safe to call from the main GTK thread.
    """
    if not config.MOBILE_SERVER_ENABLED:
        print("[mobile] Mobile server disabled in config")
        return

    def _run():
        global _loop
        try:
            app, uvicorn = _build_app(dispatch_fn or (lambda t: ""))
        except RuntimeError as e:
            print(f"[mobile] {e}")
            return

        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

        ip = get_local_ip()
        print(f"[mobile] Server started → http://{ip}:{config.MOBILE_SERVER_PORT}")
        print(f"[mobile] Open this URL on your phone to access Jarvis remotely")

        _loop.run_until_complete(
            uvicorn.Server(
                uvicorn.Config(
                    app,
                    host=config.MOBILE_SERVER_HOST,
                    port=config.MOBILE_SERVER_PORT,
                    log_level="error",
                    loop="asyncio",
                )
            ).serve()
        )

    t = threading.Thread(target=_run, daemon=True, name="jarvis-mobile-server")
    t.start()
