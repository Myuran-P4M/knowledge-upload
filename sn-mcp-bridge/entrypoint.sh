#!/bin/sh
set -e

PROJECT_ROOT="${PROJECT_ROOT:-/project}"
REQ_FILE="$PROJECT_ROOT/sn-igt-upload/requirements.txt"

echo "[entrypoint] Project root: $PROJECT_ROOT"

# Install Python deps from the mounted project (runs once, fast on subsequent starts)
if [ -f "$REQ_FILE" ]; then
  echo "[entrypoint] Installing Python dependencies from $REQ_FILE ..."
  pip3 install --break-system-packages -q -r "$REQ_FILE"
  echo "[entrypoint] Python deps installed."
else
  echo "[entrypoint] WARNING: $REQ_FILE not found — skipping Python dep install"
fi

echo "[entrypoint] Starting Node.js bridge server ..."
exec node /app/app.js
