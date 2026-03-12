#!/usr/bin/env sh
set -e

# -----------------------------------------------------------
# Require DATABASE_URL
# -----------------------------------------------------------
if [ -z "${DATABASE_URL}" ]; then
    echo "❌ DATABASE_URL is required but not set"
    exit 1
fi

# -----------------------------------------------------------
# Database readiness check
# -----------------------------------------------------------
# Strip SQLAlchemy driver suffix (e.g., +psycopg, +asyncpg) for pg_isready
PG_URL=$(echo "${DATABASE_URL}" | sed 's|^\(postgresql\)+[a-z]*://|\1://|')

echo "⏳ Waiting for database..."
retries=0
max_retries=30
until pg_isready -d "${PG_URL}" -q; do
    retries=$((retries + 1))
    if [ "$retries" -ge "$max_retries" ]; then
        echo "❌ Database not reachable after ${max_retries} attempts"
        exit 1
    fi
    sleep 1
done
echo "✅ Database is ready"

# Default to "upgrade head" when called without arguments
if [ $# -eq 0 ]; then
    set -- upgrade head
fi

echo "🔄 Running: alembic $*"
if ! alembic "$@"; then
    echo "❌ Alembic command failed"
    exit 1
fi
echo "✅ Alembic command complete"
