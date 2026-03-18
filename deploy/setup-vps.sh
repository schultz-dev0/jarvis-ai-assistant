#!/usr/bin/env bash
# deploy/setup-vps.sh
# -------------------------------------------------------------------
# Set up Sasha Brain Bridge on a fresh Ubuntu 22.04/24.04 or Debian 12 VPS.
# Run from the project root as root:
#   sudo bash deploy/setup-vps.sh
# -------------------------------------------------------------------
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${BLUE}[sasha]${NC} $*"; }
ok()    { echo -e "${GREEN}[  ok ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[ warn]${NC} $*"; }
die()   { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }
hr()    { echo -e "${BOLD}────────────────────────────────────────${NC}"; }

# ── Pre-flight ────────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root:  sudo bash deploy/setup-vps.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=/dev/null
source /etc/os-release 2>/dev/null || true
if [[ "${ID:-}" =~ ubuntu|debian ]]; then
    ok "Detected $PRETTY_NAME"
else
    warn "Not Ubuntu/Debian — you may need to adapt package names."
fi

INSTALL_DIR=/opt/sasha
SASHA_USER=sasha
ENV_FILE=/etc/sasha/env

hr
info "Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    curl rsync
ok "System packages ready"

# ── Ollama ────────────────────────────────────────────────────────────────────
hr
if command -v ollama &>/dev/null; then
    ok "Ollama already installed ($(ollama --version 2>&1 | head -1))"
else
    info "Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
    systemctl enable --now ollama
    ok "Ollama installed and started"
fi

# Pull model in the background (may take minutes on first run)
info "Pulling Ollama model ${OLLAMA_MODEL:-llama3.2:3b} (background)..."
nohup ollama pull "${OLLAMA_MODEL:-llama3.2:3b}" >/tmp/ollama-pull.log 2>&1 &
ok "Pull started — check /tmp/ollama-pull.log"

# ── System user ───────────────────────────────────────────────────────────────
hr
if id "$SASHA_USER" &>/dev/null; then
    ok "User '$SASHA_USER' already exists"
else
    info "Creating system user '$SASHA_USER'..."
    useradd -r -s /usr/sbin/nologin -d "$INSTALL_DIR" "$SASHA_USER"
    ok "User created"
fi

# ── Install directory ─────────────────────────────────────────────────────────
hr
info "Syncing project to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
rsync -a --delete \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude 'node_modules' \
    "$PROJECT_DIR/" "$INSTALL_DIR/"
ok "Files synced"

# ── Python venv ───────────────────────────────────────────────────────────────
hr
info "Setting up Python venv..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -q -r "$INSTALL_DIR/requirements-server.txt"
ok "Python dependencies installed"

# ── Memory directory ──────────────────────────────────────────────────────────
mkdir -p /var/lib/sasha
chown "$SASHA_USER:$SASHA_USER" /var/lib/sasha

# ── Environment file ──────────────────────────────────────────────────────────
hr
mkdir -p /etc/sasha
chmod 750 /etc/sasha

if [[ -f "$ENV_FILE" ]]; then
    ok "$ENV_FILE already exists — not overwritten"
else
    info "Creating $ENV_FILE from template..."
    cp "$INSTALL_DIR/deploy/env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    chown root:root "$ENV_FILE"

    # Auto-generate a bridge token
    TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/CHANGE_ME_generate_with_secrets_token_hex_32/$TOKEN/" "$ENV_FILE"

    echo ""
    echo -e "${YELLOW}┌─────────────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│  Auto-generated SASHA_BRIDGE_TOKEN:                 │${NC}"
    echo -e "${YELLOW}│  $TOKEN  │${NC}"
    echo -e "${YELLOW}└─────────────────────────────────────────────────────┘${NC}"
    echo ""
    warn "Copy this token to your local PC:"
    warn "  Add to ~/.config/jarvis/settings.env:"
    warn "  SASHA_BRIDGE_TOKEN=$TOKEN"
    echo ""
fi

# ── File ownership ────────────────────────────────────────────────────────────
chown -R "$SASHA_USER:$SASHA_USER" "$INSTALL_DIR"

# ── systemd service ───────────────────────────────────────────────────────────
hr
info "Installing systemd service..."
cp "$INSTALL_DIR/deploy/sasha-brain.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable sasha-brain
ok "Service installed and enabled (not started yet)"

# ── Nginx ─────────────────────────────────────────────────────────────────────
hr
info "Installing nginx config..."
cp "$INSTALL_DIR/deploy/nginx-sasha.conf" /etc/nginx/sites-available/sasha
if [[ ! -L /etc/nginx/sites-enabled/sasha ]]; then
    ln -s /etc/nginx/sites-available/sasha /etc/nginx/sites-enabled/sasha
fi
nginx -t 2>/dev/null && ok "Nginx config valid" || warn "Nginx config has errors — fix your domain name first"

# ── Summary ───────────────────────────────────────────────────────────────────
hr
echo ""
echo -e "${GREEN}${BOLD}  Sasha VPS setup complete!${NC}"
echo ""
echo "  Next steps:"
echo ""
echo "  1. Edit /etc/sasha/env"
echo "       — Set TELEGRAM_BOT_TOKEN (from @BotFather)"
echo "       — Optionally set GROQ_API_KEY (https://console.groq.com)"
echo ""
echo "  2. Edit /etc/nginx/sites-available/sasha"
echo "       — Replace 'your.domain.example' with your real domain"
echo ""
echo "  3. Issue a TLS certificate:"
echo "       certbot --nginx -d your.domain.example"
echo ""
echo "  4. Start the service:"
echo "       systemctl start sasha-brain"
echo "       journalctl -u sasha-brain -f"
echo ""
echo "  5. On your LOCAL PC — add to ~/.config/jarvis/settings.env:"
echo "       JARVIS_BRIDGE_URL=wss://your.domain.example/ws/satellite/\$(hostname)"
echo "       SASHA_BRIDGE_TOKEN=<token from above>"
echo ""
hr
