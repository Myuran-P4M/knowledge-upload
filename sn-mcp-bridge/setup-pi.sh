#!/bin/bash
# ============================================================
# setup-pi.sh — one-shot setup script for Raspberry Pi 5
# Run this once after copying the project to the Pi.
#
# Usage:
#   chmod +x setup-pi.sh
#   ./setup-pi.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "╔══════════════════════════════════════════╗"
echo "║     SN MCP Bridge — Pi 5 Setup           ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Install Docker if missing ────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo "[1/5] Installing Docker ..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  echo "      Docker installed. You may need to log out and back in."
else
  echo "[1/5] Docker already installed: $(docker --version)"
fi

# ── 2. Create .env from example if missing ──────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "[2/5] Creating .env from .env.example ..."
  cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"

  # Auto-fill PROJECT_ROOT_HOST
  sed -i "s|PROJECT_ROOT_HOST=.*|PROJECT_ROOT_HOST=$PROJECT_ROOT|" "$ENV_FILE"

  # Auto-generate MCP_AUTH_TOKEN
  if command -v openssl &>/dev/null; then
    TOKEN=$(openssl rand -hex 32)
    sed -i "s|MCP_AUTH_TOKEN=.*|MCP_AUTH_TOKEN=$TOKEN|" "$ENV_FILE"
    echo "      Generated MCP_AUTH_TOKEN: $TOKEN"
    echo "      *** Save this token — you'll need it in ServiceNow ***"
  fi

  echo ""
  echo "      [ACTION REQUIRED] Edit .env and fill in:"
  echo "        - SN_INSTANCE"
  echo "        - SN_USERNAME"
  echo "        - SN_PASSWORD"
  echo "        - SN_KB_SYS_ID"
  echo "        - ANTHROPIC_API_KEY"
  echo ""
  read -p "      Press Enter when .env is ready, or Ctrl+C to exit and edit first..."
else
  echo "[2/5] .env already exists — skipping."
fi

# ── 3. Create certs dir ─────────────────────────────────────────────────────
echo "[3/5] Ensuring certs directory exists ..."
mkdir -p "$SCRIPT_DIR/certs"

# ── 4. Build and start containers ───────────────────────────────────────────
echo "[4/5] Building and starting containers ..."
cd "$SCRIPT_DIR"
docker compose up -d --build

# ── 5. Show status ──────────────────────────────────────────────────────────
echo ""
echo "[5/5] Waiting for bridge to be healthy ..."
sleep 10

if curl -sf http://localhost:3000/health > /dev/null; then
  PI_IP=$(hostname -I | awk '{print $1}')
  echo ""
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║  MCP Bridge is UP                                        ║"
  echo "╠══════════════════════════════════════════════════════════╣"
  echo "║  HTTP  : http://$PI_IP:80   (redirects to HTTPS)  ║"
  echo "║  HTTPS : https://$PI_IP:443                        ║"
  echo "║                                                          ║"
  echo "║  ServiceNow endpoint:                                    ║"
  echo "║    POST https://$PI_IP/trigger-igt-upload         ║"
  echo "║                                                          ║"
  echo "║  Test:                                                   ║"
  echo "║    curl -k https://$PI_IP/health                  ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
  echo "  Note: '-k' flag needed because cert is self-signed."
  echo "  In ServiceNow REST Message, disable 'Mutual Auth' or"
  echo "  import the cert from ./certs/cert.pem into SN keystore."
else
  echo ""
  echo "[ERROR] Bridge did not respond. Check logs:"
  echo "  docker compose logs bridge"
fi
