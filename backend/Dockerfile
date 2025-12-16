# syntax=docker/dockerfile:1.6

########################################
# Stage 1: Builder
########################################
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install uv binary
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

# Copy dependency manifests
COPY pyproject.toml uv.lock* /app/

# Install deps into uv-managed virtualenv
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project

# Copy only required app files
COPY app /app/app
COPY migrations /app/migrations
COPY pyproject.toml /app/
COPY README.md /app/
COPY alembic.ini /app/

# Install project in editable mode
RUN --mount=type=cache,target=/root/.cache/uv uv sync

########################################
# Stage 2: Runtime
########################################
FROM python:3.13-slim-bookworm AS runtime

ARG ENV=development
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    UV_SYSTEM_PYTHON=1 \
    ENV=${ENV}

WORKDIR /app

# Minimal utilities (for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*

# Copy uv binary
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

# Copy preinstalled virtualenv and source files
COPY --from=builder /app /app

# COPY entrypoint.sh BEFORE switching users
COPY entrypoint.sh /app/entrypoint.sh

# Make it executable WHILE STILL ROOT
RUN chmod +x /app/entrypoint.sh

# Create non-root user for runtime safety
RUN adduser --disabled-password --gecos "" appuser
USER appuser

EXPOSE 8000

# Healthcheck endpoint (optional)
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O- http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]