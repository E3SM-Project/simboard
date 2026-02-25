#!/usr/bin/env sh
set -e

echo "ENV=$ENV"

# -----------------------------------------------------------
# Database readiness check
# -----------------------------------------------------------
if [ -n "${DATABASE_URL}" ]; then
    # Extract host and port from DATABASE_URL
    # Supports: postgresql[+driver]://user:pass@host:port/dbname
    DB_HOST=$(echo "${DATABASE_URL}" | sed -n 's|.*@\([^:/]*\).*|\1|p')
    DB_PORT=$(echo "${DATABASE_URL}" | sed -n 's|.*@[^:]*:\([0-9]*\).*|\1|p')
    DB_PORT=${DB_PORT:-5432}

    echo "⏳ Waiting for database at ${DB_HOST}:${DB_PORT}..."
    retries=0
    max_retries=30
    until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -q; do
        retries=$((retries + 1))
        if [ "$retries" -ge "$max_retries" ]; then
            echo "❌ Database not reachable after ${max_retries} attempts"
            exit 1
        fi
        sleep 1
    done
    echo "✅ Database is ready"
fi

# -----------------------------------------------------------
# Run Alembic migrations
# -----------------------------------------------------------
echo "🔄 Running Alembic migrations..."
if ! uv run alembic upgrade head; then
    echo "❌ Alembic migrations failed"
    exit 1
fi
echo "✅ Alembic migrations complete"

# -----------------------------------------------------------
# Start application
# -----------------------------------------------------------
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
