#!/usr/bin/env sh
set -e

echo "ENV=$ENV"

if [ "$ENV" = "production" ]; then
    echo "🚀 Starting SimBoard backend (production mode)..."
    # In production, HTTPS is expected to be handled by a reverse proxy (e.g., Traefik).
    # Uvicorn is started without SSL options here; do not enable HTTPS at the app layer in production.
    exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
else
    echo "⚙️ Starting SimBoard backend (development mode with HTTPS + autoreload)..."

    # Check for dev certs via env vars
    if [ -z "${SSL_KEYFILE}" ] || [ -z "${SSL_CERTFILE}" ]; then
        echo "❌ Missing SSL_KEYFILE or SSL_CERTFILE environment variables"
        echo "   Set SSL_KEYFILE and SSL_CERTFILE environment variables"
        exit 1
    fi

    exec uv run uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --ssl-keyfile "${SSL_KEYFILE}" \
        --ssl-certfile "${SSL_CERTFILE}" \
        --reload
fi
