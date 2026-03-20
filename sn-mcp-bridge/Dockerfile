# ── Base image: ARM64-compatible (Raspberry Pi 5) ──────────────────────────
# node:20-slim is Debian-based — pre-built pymupdf wheels work here (Alpine/musl does not)
FROM node:20-slim

LABEL maintainer="sn-mcp-bridge"
LABEL description="MCP Bridge: ServiceNow → Claude IGT upload skill"

# Install Python 3, pip, curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Node dependencies first (layer cache)
COPY package.json ./
RUN npm install --omit=dev

# Copy bridge server
COPY app.js .

# Install Python dependencies from the mounted project at runtime
# (script run via entrypoint so the volume is available)
COPY entrypoint.sh /entrypoint.sh
# Strip Windows CRLF line endings and make executable
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
