#!/usr/bin/env sh
# ---------------------------------------------------------------
# Standalone Alembic migration runner
# ---------------------------------------------------------------
# Purpose:
#   Run database migrations independently of the application.
#   Designed to be used as a Kubernetes Job command in NERSC Spin
#   or executed manually from any host with database access.
#
# Required environment variables:
#   DATABASE_URL  - PostgreSQL connection string
#                   (e.g., postgresql+psycopg://user:pass@host:5432/db)
#
# Usage:
#   # Apply all pending migrations
#   ./migrate.sh
#
#   # Pass extra arguments to alembic
#   ./migrate.sh downgrade -1
#   ./migrate.sh current
#   ./migrate.sh history
#
# See docs/cicd/DEPLOYMENT.md for full deployment and migration
# documentation.
# ---------------------------------------------------------------
set -e

if [ -z "${DATABASE_URL}" ]; then
    echo "❌ DATABASE_URL is required but not set"
    exit 1
fi

# Strip SQLAlchemy driver suffix for pg_isready
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
if ! uv run alembic "$@"; then
    echo "❌ Alembic command failed"
    exit 1
fi
echo "✅ Alembic command complete"
