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

COMPOSE_FILE_LOCAL := docker-compose.local.yml
COMPOSE_FILE_PROD := docker-compose.yml

# ============================================================
# 🧭 HELP MENU
# ============================================================

.PHONY: help
help:
	@echo "$(YELLOW)SimBoard Monorepo Commands$(NC)"
	@echo ""

	@echo "$(BLUE)Setup & Installation:$(NC)"
	@echo "  make install                               # Install backend, frontend, and pre-commit dependencies"
	@echo "  make setup-local                           # Bare-metal local environment setup"
	@echo "  make setup-local-assets                    # Ensure .env files + certs exist"
	@echo "  make copy-env-files                        # Copy .env.example → .env"
	@echo "  make gen-certs                             # Generate local SSL certs"
	@echo ""

	@echo "$(BLUE)Cleanup:$(NC)"
	@echo "  make clean                                 # Remove backend and frontend build/cache artifacts"
	@echo "  make backend-clean                         # Clean Python caches"
	@echo "  make frontend-clean                        # Remove node_modules + build artifacts"
	@echo ""

	@echo "$(BLUE)Backend:$(NC)"
	@echo "  make backend-install                       # Create venv (if missing) + install deps"
	@echo "  make backend-reset                         # Recreate venv + reinstall deps"
	@echo "  make backend-run                           # Start FastAPI server with hot reload"
	@echo "  make backend-migrate m='msg'               # Create Alembic migration"
	@echo "  make backend-upgrade                       # Apply DB migrations"
	@echo "  make backend-downgrade rev=<rev>           # Downgrade DB"
	@echo "  make backend-test                          # Run pytest"
	@echo ""

	@echo "$(BLUE)Frontend:$(NC)"
	@echo "  make frontend-install                      # Install frontend dependencies"
	@echo "  make frontend-run                          # Start Vite dev server with hot reload"
	@echo "  make frontend-build                        # Build frontend"
	@echo "  make frontend-preview                      # Preview production build"
	@echo "  make frontend-lint                         # Run ESLint"
	@echo "  make frontend-fix                          # Run ESLint with --fix"
	@echo ""

	@echo "$(BLUE)Pre-commit:$(NC)"
	@echo "  make pre-commit-install                    # Install git pre-commit hooks"
	@echo "  make pre-commit-run                        # Run all pre-commit hooks"
	@echo ""

	@echo "$(BLUE)Docker Compose:$(NC)"
	@echo "  make docker-build svc=<svc>                # Build Docker image(s)"
	@echo "  make docker-rebuild svc=<svc>              # Build Docker image(s) without cache"
	@echo "  make docker-up svc=<svc>                   # Start service(s)"
	@echo "  make docker-up-detached svc=<svc>          # Start service(s) in background"
	@echo "  make docker-down                           # Stop all services"
	@echo "  make docker-restart svc=<svc>              # Restart service(s)"
	@echo "  make docker-logs svc=<svc>                 # Follow service logs"
	@echo "  make docker-shell svc=<svc>                # Shell into running container"
	@echo "  make docker-ps                             # List running containers"
	@echo "  make docker-config                         # Show resolved docker-compose config"
	@echo ""

# ============================================================
# ⚙️ CORE SETUP
# ============================================================

.PHONY: setup-local setup-local-assets copy-env-files gen-certs install

# ------------------------------------------------------------
# Bare-metal environment
# ------------------------------------------------------------
# Always use env=local for bare-metal setup.
setup-local: setup-local-assets db-up install
	@echo "$(GREEN)⏳ Waiting for Postgres...$(NC)"
	@until docker compose -f $(COMPOSE_FILE_LOCAL) exec db pg_isready -U simboard -d simboard >/dev/null 2>&1; do printf "."; sleep 1; done
	@echo "$(GREEN)\n✅ Postgres is ready!$(NC)"

	@echo "$(GREEN)📜 Running migrations + seeding via bare-metal backend...$(NC)"
	cd $(BACKEND_DIR) && uv run alembic upgrade head
	cd $(BACKEND_DIR) && uv run python app/scripts/seed.py || true

	@echo "$(GREEN)✨ Bare-metal local environment is ready!$(NC)"
	@echo "$(CYAN)Run:  make backend-run"
	@echo "$(CYAN)Run:  make frontend-run"

db-up:
	@echo "$(GREEN)🚀 Starting Postgres (Docker-only)...$(NC)"
	@docker compose -f $(COMPOSE_FILE_LOCAL) up -d db

# ------------------------------------------------------------
# Environment Files + Certificates
# ------------------------------------------------------------
setup-local-assets:
	@echo "$(GREEN)✨ Ensuring env + certs exist...$(NC)"
	make copy-env-files env=$(env)
	make gen-certs

copy-env-files:
	@envs="local"; \
	echo ""; \
	for e in $$envs; do \
		echo "$(BLUE)🔧 Environment: $$e$(NC)"; \
		mkdir -p ".envs/$$e"; \
		for file in backend frontend db; do \
			src=".envs/example/$$file.env.example"; \
			dst=".envs/$$e/$$file.env"; \
			if [ -f "$$dst" ]; then \
				echo "$(YELLOW)⚠️  $$dst exists, skipping$(NC)"; \
			elif [ -f "$$src" ]; then \
				cp "$$src" "$$dst"; \
				echo "$(GREEN)✔ $$src → $$dst$(NC)"; \
			else \
				echo "$(YELLOW)⚠️ Missing $$src$(NC)"; \
			fi; \
		done; \
		\
		src=".envs/example/backend.production.env.example"; \
		dst=".envs/$$e/backend.production.env"; \
		if [ -f "$$dst" ]; then \
			echo "$(YELLOW)⚠️  $$dst exists, skipping$(NC)"; \
		elif [ -f "$$src" ]; then \
			cp "$$src" "$$dst"; \
			echo "$(GREEN)✔ $$src → $$dst$(NC)"; \
		else \
			echo "$(YELLOW)⚠️ Missing $$src$(NC)"; \
		fi; \
	done; \
	\
	src=".envs/example/.env.example"; \
	dst=".envs/local/.env"; \
	if [ -f "$$dst" ]; then \
		echo "$(YELLOW)⚠️  $$dst exists, skipping$(NC)"; \
	elif [ -f "$$src" ]; then \
		mkdir -p ".envs/local"; \
		cp "$$src" "$$dst"; \
		echo "$(GREEN)✔ $$src → $$dst$(NC)"; \
	else \
		echo "$(YELLOW)⚠️ Missing $$src$(NC)"; \
	fi

gen-certs:
	@echo "$(GREEN)🔐 Generating local SSL certificates...$(NC)"
	cd certs && ./generate-local-certs.sh

# ------------------------------------------------------------
# Pre-commit
# ------------------------------------------------------------

.PHONY: pre-commit-install pre-commit-run

pre-commit-install:
	cd $(BACKEND_DIR) && uv run pre-commit install --install-hooks

pre-commit-run:
	cd $(BACKEND_DIR) && uv run pre-commit run --all-files


# ============================================================
# 🧼 CLEANUP
# ============================================================

.PHONY: clean install

install: backend-install frontend-install pre-commit-install

clean:
	make backend-clean
	make frontend-clean

# ============================================================
# 🧑‍💻 BACKEND COMMANDS
# ============================================================

.PHONY: backend-install backend-clean backend-run backend-migrate backend-upgrade backend-downgrade backend-test

backend-install:
	cd $(BACKEND_DIR) && if [ ! -d .venv ]; then uv venv .venv; fi && uv sync --all-groups

backend-reset:
	cd $(BACKEND_DIR) && rm -rf .venv && uv venv .venv && uv sync --all-groups

backend-clean:
	cd $(BACKEND_DIR) && find . -type d -name "__pycache__" -exec rm -rf {} + && rm -rf .pytest_cache .ruff_cache build dist .mypy_cache

backend-run:
	cd $(BACKEND_DIR) && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 \
		--ssl-keyfile ../certs/local.key --ssl-certfile ../certs/local.crt

backend-migrate:
	cd $(BACKEND_DIR) && uv run alembic revision --autogenerate -m "$(m)"

backend-upgrade:
	cd $(BACKEND_DIR) && uv run alembic upgrade head

backend-downgrade:
	cd $(BACKEND_DIR) && uv run alembic downgrade $(rev)

backend-test:
	cd $(BACKEND_DIR) && uv run pytest -q


# ============================================================
# 🧑‍💻 FRONTEND COMMANDS
# ============================================================

.PHONY: frontend-install frontend-clean frontend-local frontend-build frontend-preview frontend-lint frontend-fix

frontend-install:
	cd $(FRONTEND_DIR) && pnpm install

frontend-clean:
	cd $(FRONTEND_DIR) && rm -rf node_modules dist .turbo

frontend-local:
	cd $(FRONTEND_DIR) && pnpm dev

frontend-build:
	cd $(FRONTEND_DIR) && pnpm build

frontend-run:
	cd $(FRONTEND_DIR) && pnpm dev

frontend-preview:
	cd $(FRONTEND_DIR) && pnpm preview

frontend-lint:
	cd $(FRONTEND_DIR) && pnpm lint

frontend-fix:
	cd $(FRONTEND_DIR) && pnpm lint:fix


# ============================================================
# 🐳 DOCKER COMPOSE COMMANDS
# ============================================================

.PHONY: docker-help docker-build docker-rebuild docker-up docker-down docker-restart docker-logs docker-shell docker-ps docker-config

ENV_PROD := \
	--env-file .env \
	--env-file .envs/local/backend.production.env

COMPOSE := docker compose $(ENV_PROD) -f docker-compose.yml

docker-build:
	$(COMPOSE) build $(svc)

docker-rebuild:
	$(COMPOSE) build --no-cache $(svc)

docker-up:
	$(COMPOSE) up $(svc)

docker-up-detached:
	$(COMPOSE) up -d $(svc)

docker-down:
	$(COMPOSE) down

docker-restart:
	$(COMPOSE) restart $(svc)

docker-logs:
	$(COMPOSE) logs -f $(svc)

docker-shell:
	$(COMPOSE) exec $(svc) bash

docker-ps:
	$(COMPOSE) ps

docker-config:
	$(COMPOSE) config
