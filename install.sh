#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Jarvis Personal Assistant — Installer
# Arch Linux / Hyprland
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

JARVIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$HOME/.local/share/jarvis"
CONFIG_DIR="$HOME/.config/jarvis"
VOICES_DIR="$DATA_DIR/voices"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
info() { echo -e "${CYAN}[→]${NC} $1"; }

echo ""
echo -e "${CYAN}      ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗  ${NC}"
echo -e "${CYAN}      ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝  ${NC}"
echo -e "${CYAN}      ██║███████║██████╔╝██║   ██║██║███████╗  ${NC}"
echo -e "${CYAN} ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║  ${NC}"
echo -e "${CYAN} ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║  ${NC}"
echo ""
echo "  Personal AI Assistant — Installer"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
info "Installing system packages via pacman..."
sudo pacman -S --needed --noconfirm \
    python \
    python-pip \
    python-gobject \
    gtk4 \
    libadwaita \
    portaudio \
    alsa-utils \
    kdeconnect \
    brightnessctl \
    grim \
    slurp \
    wl-clipboard \
    playerctl \
    curl \
    wget 2>/dev/null || warn "Some packages may have failed — check manually"

log "System packages done"

# ── 2. Ollama ─────────────────────────────────────────────────────────────────
info "Checking Ollama..."
if ! command -v ollama &>/dev/null; then
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    log "Ollama installed"
else
    log "Ollama already installed"
fi

# Start Ollama service
info "Starting Ollama service..."
systemctl --user enable --now ollama 2>/dev/null || \
    (ollama serve &>/dev/null &
     sleep 3
     log "Ollama started in background")

# Pull the model
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
info "Pulling $OLLAMA_MODEL (this may take a few minutes)..."
ollama pull "$OLLAMA_MODEL"
log "Model $OLLAMA_MODEL ready"

# ── 3. Python dependencies ────────────────────────────────────────────────────
info "Installing Python dependencies..."
pip install --break-system-packages \
    faster-whisper \
    openwakeword \
    pyaudio \
    httpx \
    pydantic \
    numpy \
    "duckduckgo_search>=6.0.0" \
    fastapi \
    "uvicorn[standard]" 2>/dev/null

log "Python dependencies installed"

# ── 4. Piper TTS — download binary ───────────────────────────────────────────
info "Setting up Piper TTS..."
PIPER_VERSION="1.2.0"
PIPER_ARCHIVE="piper_linux_x86_64.tar.gz"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/${PIPER_ARCHIVE}"

if ! command -v piper &>/dev/null; then
    mkdir -p "$DATA_DIR/piper"
    cd "$DATA_DIR/piper"
    wget -q --show-progress "$PIPER_URL" -O "$PIPER_ARCHIVE"
    tar xf "$PIPER_ARCHIVE"
    rm "$PIPER_ARCHIVE"
    # Symlink to ~/.local/bin
    mkdir -p "$HOME/.local/bin"
    ln -sf "$DATA_DIR/piper/piper" "$HOME/.local/bin/piper"
    cd "$JARVIS_DIR"
    log "Piper installed"
else
    log "Piper already installed"
fi

# ── 5. Piper voices ───────────────────────────────────────────────────────────
info "Downloading Piper voice models..."
mkdir -p "$VOICES_DIR"

VOICE_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"

# English voice
EN_VOICE="en_US/hfc_female/medium/en_US-hfc_female-medium"
if [ ! -f "$VOICES_DIR/en_US-hfc_female-medium.onnx" ]; then
    info "Downloading English voice..."
    wget -q --show-progress \
        "$VOICE_BASE/${EN_VOICE}.onnx" \
        -O "$VOICES_DIR/en_US-hfc_female-medium.onnx"
    wget -q "$VOICE_BASE/${EN_VOICE}.onnx.json" \
        -O "$VOICES_DIR/en_US-hfc_female-medium.onnx.json"
    log "English voice downloaded"
else
    log "English voice already present"
fi

# Russian voice
RU_VOICE="ru_RU/ruslan/medium/ru_RU-ruslan-medium"
if [ ! -f "$VOICES_DIR/ru_RU-ruslan-medium.onnx" ]; then
    info "Downloading Russian voice..."
    wget -q --show-progress \
        "$VOICE_BASE/${RU_VOICE}.onnx" \
        -O "$VOICES_DIR/ru_RU-ruslan-medium.onnx"
    wget -q "$VOICE_BASE/${RU_VOICE}.onnx.json" \
        -O "$VOICES_DIR/ru_RU-ruslan-medium.onnx.json"
    log "Russian voice downloaded"
else
    log "Russian voice already present"
fi

# ── 6. openwakeword models ────────────────────────────────────────────────────
info "Pre-downloading openwakeword Jarvis model..."
python3 -c "import openwakeword; openwakeword.utils.download_models(['jarvis']); print('Wake word model ready')" || warn "openwakeword model download failed — it will retry on first run"

# ── 7. Whisper model ──────────────────────────────────────────────────────────
info "Pre-downloading Whisper base model..."
python3 -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8'); print('Whisper model ready')" || warn "Whisper model will download on first run"

# ── 8. Directories and config ─────────────────────────────────────────────────
mkdir -p "$CONFIG_DIR"
mkdir -p "$HOME/Pictures/Screenshots"

# Write default config if not present
if [ ! -f "$CONFIG_DIR/settings.env" ]; then
    cat > "$CONFIG_DIR/settings.env" <<EOF
# Jarvis Settings
OLLAMA_MODEL=llama3.2:3b
OLLAMA_BASE_URL=http://localhost:11434

# Cloud AI fallback — free at https://console.groq.com (no credit card)
GROQ_API_KEY=
GROQ_MODEL=llama3-8b-8192

# Weather default city (leave blank to be asked each time)
WEATHER_LOCATION=

# KDE Connect phone device ID (leave blank to auto-detect)
KDECONNECT_DEVICE=

# Mobile server — access Jarvis from your phone via browser
MOBILE_SERVER_ENABLED=true
MOBILE_SERVER_PORT=7123
EOF
    log "Default config written to $CONFIG_DIR/settings.env"
fi

# ── 9. Systemd user service (autostart) ──────────────────────────────────────
info "Installing systemd user service..."
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/jarvis.service" <<EOF
[Unit]
Description=Jarvis Personal Assistant
After=graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$JARVIS_DIR
ExecStart=/usr/bin/python3 $JARVIS_DIR/main.py
Restart=on-failure
RestartSec=5
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_RUNTIME_DIR=/run/user/%i
EnvironmentFile=-$CONFIG_DIR/settings.env

[Install]
WantedBy=graphical-session.target
EOF

systemctl --user daemon-reload
systemctl --user enable jarvis.service
log "Systemd service installed and enabled"

# ── 10. Desktop entry ─────────────────────────────────────────────────────────
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/jarvis.desktop" <<EOF
[Desktop Entry]
Name=Jarvis
Comment=Personal AI Assistant
Exec=python3 $JARVIS_DIR/main.py
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Utility;AI;
Keywords=assistant;ai;voice;jarvis;
StartupWMClass=jarvis
EOF

log "Desktop entry created"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Jarvis installation complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Next steps:"
echo "  1. Start now:     python3 $JARVIS_DIR/main.py"
echo "  2. Auto-start:    systemctl --user start jarvis"
echo "  3. Phone pairing: Install 'KDE Connect' on your Android phone"
echo "                    then open kdeconnect-app on desktop to pair"
echo "  4. Set your city: Edit $CONFIG_DIR/settings.env"
echo "                    Set WEATHER_LOCATION=YourCity"
echo "  5. Cloud AI:      Get a FREE Groq API key at https://console.groq.com"
echo "                    Set GROQ_API_KEY= in $CONFIG_DIR/settings.env"
echo "                    (No credit card — Jarvis will auto-use it if Ollama goes offline)"
echo "  6. Mobile access: Once running, open http://\$(hostname -I | awk '{print \$1}'):7123"
echo "                    on your phone browser to use Jarvis over WiFi"
echo ""
echo "  Wake word: say 'Jarvis' to activate"
echo "  Languages: English and Russian supported"
echo "  Learning:  Jarvis remembers your habits and improves over time"
echo ""