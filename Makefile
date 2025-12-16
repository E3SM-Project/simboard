# ============================================================
#  🌍 SimBoard Unified Project Makefile
# ============================================================

# ------------------------------------------------------------
# Colors
# ------------------------------------------------------------
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
BLUE   := \033[0;34m
CYAN   := \033[0;36m
NC     := \033[0m

# ------------------------------------------------------------
# Directories
# ------------------------------------------------------------
BACKEND_DIR  := backend
FRONTEND_DIR := frontend

# ------------------------------------------------------------
# Environment Selection
# ------------------------------------------------------------
# Allowed: dev | dev_docker | prod
env ?= dev
export APP_ENV := $(env)

COMPOSE_FILE_DEV  := docker-compose.dev.yml
COMPOSE_FILE_PROD := docker-compose.yml
COMPOSE_FILE      := $(if $(filter prod,$(env)),$(COMPOSE_FILE_PROD),$(COMPOSE_FILE_DEV))


# ============================================================
# 🧭 HELP MENU
# ============================================================

.PHONY: help
help:
	@echo "$(YELLOW)SimBoard Monorepo Commands$(NC)"
	@echo ""
	@echo "$(BLUE)Environment:$(NC) APP_ENV=$(env)"
	@echo ""
	@echo "  $(YELLOW)Project Setup$(NC)"
	@echo "    make setup-dev env=dev                     # Bare-metal dev setup"
	@echo "    make setup-dev-docker env=dev_docker       # Docker dev setup"
	@echo "    make setup-dev-assets env=<env>            # Ensure .env + certs exist"
	@echo "    make copy-env env=<env>                    # Copy .env.example → .env"
	@echo "    make gen-certs                             # Generate dev SSL certs"
	@echo ""
	@echo "  $(YELLOW)Backend Commands$(NC)"
	@echo "    make backend-install                       # Create venv + install deps"
	@echo "    make backend-clean                         # Clean caches"
	@echo "    make backend-run                           # Start FastAPI"
	@echo "    make backend-reload                        # Start with auto-reload"
	@echo "    make backend-migrate m='msg'               # Create Alembic migration"
	@echo "    make backend-upgrade                       # Apply migrations"
	@echo "    make backend-downgrade rev=<rev>           # Downgrade DB"
	@echo "    make backend-test                          # Run pytest"
	@echo ""
	@echo "  $(YELLOW)Frontend Commands$(NC)"
	@echo "    make frontend-install                      # Install dependencies"
	@echo "    make frontend-dev                          # Start Vite dev server"
	@echo "    make frontend-build                        # Build site"
	@echo "    make frontend-preview                      # Preview built site"
	@echo "    make frontend-lint                         # ESLint"
	@echo ""
	@echo "  $(YELLOW)Docker$(NC)"
	@echo "    make docker-up env=<env> svc=<svc>         # Start service(s)"
	@echo "    make docker-build env=<env> svc=<svc>      # Build service images"
	@echo ""
	@echo "  $(YELLOW)Database (via Docker)$(NC)"
	@echo "    make db-init env=<env>                     # Migrate + seed dev DB"


# ============================================================
# ⚙️ CORE SETUP
# ============================================================

.PHONY: setup-dev setup-dev-docker setup-dev-assets copy-env gen-certs

# ------------------------------------------------------------
# Bare-metal dev
# ------------------------------------------------------------
# Always use env=dev for bare-metal setup.
setup-dev: env=dev
setup-dev: setup-dev-assets install
	@echo "$(GREEN)🚀 Starting Postgres (Docker-only)...$(NC)"
	@docker compose -f $(COMPOSE_FILE_DEV) up -d db

	@echo "$(GREEN)⏳ Waiting for Postgres...$(NC)"
	@until docker compose -f $(COMPOSE_FILE_DEV) exec db pg_isready -U simboard -d simboard >/dev/null 2>&1; do printf "."; sleep 1; done
	@echo "$(GREEN)\n✅ Postgres is ready!$(NC)"

	@echo "$(GREEN)📜 Running migrations + seeding via bare-metal backend...$(NC)"
	cd $(BACKEND_DIR) && APP_ENV=dev uv run alembic upgrade head
	cd $(BACKEND_DIR) && APP_ENV=dev uv run python app/scripts/seed.py || true

	@echo "$(GREEN)✨ Bare-metal dev is ready!$(NC)"
	@echo "$(CYAN)Run:  make backend-reload env=dev$(NC)"
	@echo "$(CYAN)Run:  make frontend-dev env=dev$(NC)"

# ------------------------------------------------------------
# Docker dev
# ------------------------------------------------------------
# Always use env=dev_docker for docker setup.
setup-dev-docker: env=dev_docker
setup-dev-docker: setup-dev-assets install
	@echo "$(GREEN)🐳 Building Docker images...$(NC)"
	make docker-build env=dev_docker

	@echo "$(GREEN)🐳 Starting Postgres...$(NC)"
	APP_ENV=dev_docker docker compose -f $(COMPOSE_FILE_DEV) up -d db

	@echo "$(GREEN)⏳ Waiting for Postgres...$(NC)"
	@until docker compose -f $(COMPOSE_FILE_DEV) exec db pg_isready >/dev/null 2>&1; do printf "."; sleep 1; done

	@echo "$(GREEN)🐳 Starting backend container for migrations...$(NC)"
	APP_ENV=dev_docker docker compose -f $(COMPOSE_FILE_DEV) up -d backend

	@echo "$(GREEN)⏳ Waiting for backend...$(NC)"
	@until docker compose -f $(COMPOSE_FILE_DEV) exec backend ls >/dev/null 2>&1; do printf "."; sleep 1; done

	@echo "$(GREEN)📜 Running DB migrations...$(NC)"
	make db-init env=dev_docker

	@echo "$(GREEN)✨ Docker dev environment ready!$(NC)"
	@echo "$(CYAN)Run: make docker-up env=dev_docker svc=backend$(NC)"
	@echo "$(CYAN)Run: make docker-up env=dev_docker svc=frontend$(NC)"

# ------------------------------------------------------------
# Environment Files + Certificates
# ------------------------------------------------------------
setup-dev-assets:
	@echo "$(GREEN)✨ Ensuring env + certs exist...$(NC)"
	make copy-env env=$(env)
	make gen-certs

copy-env:
	@if [ -n "$(env)" ]; then envs="$(env)"; else envs="dev dev_docker prod"; fi; \
	for e in $$envs; do \
		echo ""; echo "$(BLUE)🔧 Environment: $$e$(NC)"; \
		for file in backend frontend; do \
			src=".envs/$$e/$$file.env.example"; \
			dst=".envs/$$e/$$file.env"; \
			if [ -f "$$dst" ]; then echo "$(YELLOW)⚠️  $$dst exists, skipping$(NC)"; \
			elif [ -f "$$src" ]; then cp "$$src" "$$dst"; echo "$(GREEN)✔ $$src → $$dst$(NC)"; \
			else echo "$(YELLOW)⚠️ Missing $$src$(NC)"; fi; \
		done; \
	done

gen-certs:
	@echo "$(GREEN)🔐 Generating dev SSL certificates...$(NC)"
	cd certs && ./generate-dev-certs.sh


# ============================================================
# 🧑‍💻 BACKEND COMMANDS
# ============================================================

.PHONY: backend-install backend-clean backend-run backend-reload backend-migrate backend-upgrade backend-downgrade backend-test

backend-install:
	cd $(BACKEND_DIR) && uv venv .venv && uv sync --all-groups

backend-clean:
	cd $(BACKEND_DIR) && find . -type d -name "__pycache__" -exec rm -rf {} + && rm -rf .pytest_cache .ruff_cache build dist .mypy_cache

backend-run:
	cd $(BACKEND_DIR) && APP_ENV=$(env) uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 \
		--ssl-keyfile ../certs/dev.key --ssl-certfile ../certs/dev.crt

backend-reload:
	cd $(BACKEND_DIR) && APP_ENV=$(env) uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 \
		--ssl-keyfile ../certs/dev.key --ssl-certfile ../certs/dev.crt

backend-migrate:
	cd $(BACKEND_DIR) && APP_ENV=$(env) uv run alembic revision --autogenerate -m "$(m)"

backend-upgrade:
	cd $(BACKEND_DIR) && APP_ENV=$(env) uv run alembic upgrade head

backend-downgrade:
	cd $(BACKEND_DIR) && APP_ENV=$(env) uv run alembic downgrade $(rev)

backend-test:
	cd $(BACKEND_DIR) && APP_ENV=$(env) uv run pytest -q


# ============================================================
# 🧑‍💻 FRONTEND COMMANDS
# ============================================================

.PHONY: frontend-install frontend-clean frontend-dev frontend-build frontend-preview frontend-lint frontend-fix

frontend-install:
	cd $(FRONTEND_DIR) && pnpm install

frontend-clean:
	cd $(FRONTEND_DIR) && rm -rf node_modules dist .turbo

frontend-dev:
	cd $(FRONTEND_DIR) && APP_ENV=$(env) pnpm dev

frontend-build:
	cd $(FRONTEND_DIR) && APP_ENV=$(env) pnpm build

frontend-preview:
	cd $(FRONTEND_DIR) && pnpm preview

frontend-lint:
	cd $(FRONTEND_DIR) && pnpm lint

frontend-fix:
	cd $(FRONTEND_DIR) && pnpm lint:fix


# ============================================================
# 🐳 DOCKER COMMANDS
# ============================================================

.PHONY: docker-help docker-build docker-rebuild docker-up docker-down docker-restart docker-logs docker-shell docker-ps docker-config

docker-help:
	@echo "$(YELLOW)Docker commands:$(NC)"
	@echo "  make docker-build env=<env> svc=<svc>"
	@echo "  make docker-up env=<env> svc=<svc>"
	@echo "  make docker-down env=<env>"

docker-build:
	APP_ENV=$(env) docker compose -f $(COMPOSE_FILE) build $(svc)

docker-rebuild:
	APP_ENV=$(env) docker compose -f $(COMPOSE_FILE) build --no-cache $(svc)

docker-up:
	APP_ENV=$(env) docker compose -f $(COMPOSE_FILE) up $(svc)

docker-up-detached:
	APP_ENV=$(env) docker compose -f $(COMPOSE_FILE) up -d $(svc)

docker-down:
	APP_ENV=$(env) docker compose -f $(COMPOSE_FILE) down

docker-restart:
	APP_ENV=$(env) docker compose -f $(COMPOSE_FILE) restart $(svc)

docker-logs:
	APP_ENV=$(env) docker compose -f $(COMPOSE_FILE) logs -f $(svc)

docker-shell:
	APP_ENV=$(env) docker compose -f $(COMPOSE_FILE) exec $(svc) bash

docker-ps:
	APP_ENV=$(env) docker compose -f $(COMPOSE_FILE) ps

docker-config:
	APP_ENV=$(env) docker compose -f $(COMPOSE_FILE) config


# ============================================================
# 🗃️ DATABASE COMMANDS (VIA DOCKER)
# ============================================================

.PHONY: db-migrate db-upgrade db-rollback db-seed db-init

db-migrate:
	APP_ENV=$(env) docker compose -f docker-compose.dev.yml exec backend uv run alembic revision --autogenerate -m "$(m)"

db-upgrade:
	APP_ENV=$(env) docker compose -f docker-compose.dev.yml exec backend uv run alembic upgrade head

db-rollback:
	APP_ENV=$(env) docker compose -f docker-compose.dev.yml exec backend uv run alembic downgrade -1

db-seed:
	@if [ "$(env)" != "prod" ]; then \
		APP_ENV=$(env) docker compose -f docker-compose.dev.yml exec backend uv run python app/scripts/seed.py; \
	else echo "$(RED)❌ Seeding disabled in production.$(NC)"; fi

db-init:
	make db-upgrade env=$(env)
	make db-seed env=$(env)


# ============================================================
# 🧼 CLEANUP
# ============================================================

.PHONY: clean install

install:
	make backend-install
	make frontend-install

clean:
	make backend-clean
	make frontend-clean


# ============================================================
# 🚀 BUILD & PREVIEW
# ============================================================

build:
	make frontend-build
	@echo "$(GREEN)Backend handled via Docker or packaging.$(NC)"

preview:
	make frontend-preview
