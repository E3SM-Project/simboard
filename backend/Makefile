# ============================================================
#  EarthFrame Backend Makefile
#  Description: Common developer commands for local use
# ============================================================

# Variables
APP_NAME=app.main:app
HOST=127.0.0.1
PORT=8000

# Colors
GREEN=\033[0;32m
NC=\033[0m

# ============================================================
#  Setup & Environment
# ============================================================

.PHONY: install shell clean

install:
	@echo "$(GREEN)Installing dependencies...$(NC)"
	poetry install

shell:
	@echo "$(GREEN)Entering Poetry shell...$(NC)"
	poetry shell

clean:
	@echo "$(GREEN)Cleaning cache and build files...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf dist build .mypy_cache .ruff_cache

# ============================================================
#  Development Server
# ============================================================

.PHONY: run reload

run:
	@echo "$(GREEN)Starting FastAPI server...$(NC)"
	poetry run uvicorn $(APP_NAME) --host $(HOST) --port $(PORT)

reload:
	@echo "$(GREEN)Starting FastAPI server with auto-reload...$(NC)"
	poetry run uvicorn $(APP_NAME) --reload --host $(HOST) --port $(PORT)

reload-debug:
	@echo "$(GREEN)Starting FastAPI server with auto-reload and debug logging...$(NC)"
	poetry run uvicorn $(APP_NAME) --reload --host $(HOST) --port $(PORT) --log-level debug

# ============================================================
#  Database Migrations (Alembic)
# ============================================================

.PHONY: migrate upgrade downgrade history current

migrate:
	@echo "$(GREEN)Generating new Alembic migration...$(NC)"
	poetry run alembic revision --autogenerate -m "$(m)"

upgrade:
	@echo "$(GREEN)Upgrading database to latest migration...$(NC)"
	poetry run alembic upgrade head

downgrade:
	@echo "$(GREEN)Downgrading database...$(NC)"
	poetry run alembic downgrade $(rev)

history:
	@echo "$(GREEN)Listing migration history...$(NC)"
	poetry run alembic history

current:
	@echo "$(GREEN)Current database version:$(NC)"
	poetry run alembic current

# ============================================================
#  Code Quality
# ============================================================

.PHONY: lint format

lint:
	@echo "$(GREEN)Linting with Ruff...$(NC)"
	poetry run ruff check .

format:
	@echo "$(GREEN)Auto-fixing issues with Ruff...$(NC)"
	poetry run ruff check . --fix

test:
	@echo "$(GREEN)Running tests with pytest...$(NC)"
	poetry run pytest tests

# ============================================================
#  Misc
# ============================================================

.PHONY: help

help:
	@echo "$(GREEN)Available commands:$(NC)"
	@echo "  make install         - Install dependencies via Poetry"
	@echo "  make shell           - Enter Poetry shell"
	@echo "  make run             - Start FastAPI server"
	@echo "  make reload          - Start FastAPI with auto-reload"
	@echo "  make migrate m='msg' - Create Alembic migration with message"
	@echo "  make upgrade         - Apply all migrations"
	@echo "  make downgrade rev=  - Downgrade to specific revision"
	@echo "  make current         - Show current DB revision"
	@echo "  make history         - Show migration history"
	@echo "  make lint            - Run linter (Ruff)"
	@echo "  make format          - Auto-fix code issues with Ruff"
	@echo "  make clean           - Remove caches and build artifacts"
