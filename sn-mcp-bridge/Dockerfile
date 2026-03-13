# ── Base image: ARM64-compatible (Raspberry Pi 5) ──────────────────────────
FROM node:20-alpine

LABEL maintainer="sn-mcp-bridge"
LABEL description="MCP Bridge: ServiceNow → Claude IGT upload skill"

# Install Python 3, pip, openssl (for cert generation), curl (healthcheck)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    bash \
    curl \
    openssl

WORKDIR /app

# Install Node dependencies first (layer cache)
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

# Copy bridge server
COPY app.js .

# Install Python dependencies from the mounted project at runtime
# (script run via entrypoint so the volume is available)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:3000/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
