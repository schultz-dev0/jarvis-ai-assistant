#!/usr/bin/env bash
# Installs piper-tts + English/Russian voices
set -e

DATA_DIR="$HOME/.local/share/jarvis"
VOICES_DIR="$DATA_DIR/voices"
BIN="$HOME/.local/bin"

mkdir -p "$VOICES_DIR" "$BIN"

echo "→ Checking for piper..."

# Try pip first (easiest on Arch)
if ! command -v piper &>/dev/null; then
    echo "→ Installing piper-tts via pip..."
    pip install piper-tts --break-system-packages 2>/dev/null \
    && echo "✓ piper-tts installed via pip" \
    || {
        echo "→ pip failed, trying binary download..."
        # Detect arch
        ARCH=$(uname -m)
        case "$ARCH" in
            x86_64)  PIPER_FILE="piper_linux_x86_64.tar.gz" ;;
            aarch64) PIPER_FILE="piper_linux_aarch64.tar.gz" ;;
            *) echo "✗ Unsupported arch: $ARCH"; exit 1 ;;
        esac

        # Get latest release tag from GitHub API
        LATEST=$(curl -s https://api.github.com/repos/rhasspy/piper/releases/latest \
                 | grep '"tag_name"' | cut -d'"' -f4)
        echo "→ Latest piper release: $LATEST"

        URL="https://github.com/rhasspy/piper/releases/download/${LATEST}/${PIPER_FILE}"
        echo "→ Downloading $URL"
        curl -L "$URL" -o /tmp/piper.tar.gz
        mkdir -p "$DATA_DIR/piper"
        tar xf /tmp/piper.tar.gz -C "$DATA_DIR/piper"
        rm /tmp/piper.tar.gz
        ln -sf "$DATA_DIR/piper/piper" "$BIN/piper"
        echo "✓ piper binary installed to $BIN/piper"
    }
else
    echo "✓ piper already installed: $(which piper)"
fi

# Voice download helper
download_voice() {
    local LANG_CODE="$1"
    local VOICE_NAME="$2"
    local QUALITY="$3"
    local FILENAME="${LANG_CODE}-${VOICE_NAME}-${QUALITY}"
    local BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
    local LANG_DIR="${LANG_CODE/_//}"  # en_US → en/US

    if [ ! -f "$VOICES_DIR/${FILENAME}.onnx" ]; then
        echo "→ Downloading voice: $FILENAME"
        curl -L --progress-bar \
            "$BASE/${LANG_DIR}/${VOICE_NAME}/${QUALITY}/${FILENAME}.onnx" \
            -o "$VOICES_DIR/${FILENAME}.onnx"
        curl -L -s \
            "$BASE/${LANG_DIR}/${VOICE_NAME}/${QUALITY}/${FILENAME}.onnx.json" \
            -o "$VOICES_DIR/${FILENAME}.onnx.json"
        echo "✓ $FILENAME downloaded"
    else
        echo "✓ $FILENAME already present"
    fi
}

echo ""
echo "→ Downloading voice models..."
download_voice "en_US" "hfc_female" "medium"
download_voice "ru_RU" "ruslan"     "medium"

echo ""
echo "✓ Piper setup complete!"
echo "  Voices in: $VOICES_DIR"
echo ""

# Quick test
if command -v piper &>/dev/null; then
    echo "→ Testing piper..."
    echo "Jarvis online." | piper \
        --model "$VOICES_DIR/en_US-hfc_female-medium.onnx" \
        --output-raw 2>/dev/null | aplay -r 22050 -f S16_LE -t raw - 2>/dev/null \
        && echo "✓ Audio test passed" \
        || echo "⚠ Audio test failed — check your sound output (aplay -l)"
fi
