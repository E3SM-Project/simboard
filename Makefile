# ============================================================
#  🌍 SimBoard Project Makefile
#  Unified project-level commands for backend & frontend
# ============================================================

# ------------------------------------------------------------
# Colors & Constants
# ------------------------------------------------------------
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m
BACKEND_DIR  := backend
FRONTEND_DIR := frontend

# ============================================================
# 🧭 Help
# ============================================================

.PHONY: help

help:
	@echo "$(YELLOW)Available top-level commands:$(NC)"
	@echo ""
	@echo "  $(YELLOW)🧭 Project Setup$(NC)"
	@printf "    %-23s %s\n" "make setup-dev" "Setup dev environment (local, DB, assets, install)"
	@printf "    %-23s %s\n" "make setup-dev-docker" "Setup dev environment fully in Docker"
	@printf "    %-23s %s\n" "make setup-dev-assets" "Prepare .env and dev SSL certs"
	@printf "    %-23s %s\n" "make copy-env" "Copy .env.example to .env for all projects"
	@printf "    %-23s %s\n" "make gen-certs" "Generate self-signed dev SSL certs"
	@printf "    %-23s %s\n" "make install" "Install local dependencies"
	@printf "    %-23s %s\n" "make clean" "Clean caches and build artifacts"
	@echo ""
	@echo "  $(YELLOW)🐳 Docker & Database$(NC)"
	@printf "    %-23s %s\n" "make docker-help" "List Docker management commands"
	@printf "    %-23s %s\n" "make db-migrate m='msg'" "Create Alembic migration (in Docker)"
	@printf "    %-23s %s\n" "make db-upgrade" "Apply Alembic migrations (in Docker)"
	@printf "    %-23s %s\n" "make db-rollback" "Rollback last Alembic migration (in Docker)"
	@printf "    %-23s %s\n" "make db-seed" "Seed dummy data (in Docker)"
	@printf "    %-23s %s\n" "make db-rollback-seed" "Rollback dummy data (in Docker)"
	@printf "    %-23s %s\n" "make db-init" "Migrate + seed database (in Docker)"
	@echo ""
	@echo "  $(YELLOW)🧑‍💻 Local Development$(NC)"
	@printf "    %-23s %s\n" "make backend" "Run backend locally only"
	@printf "    %-23s %s\n" "make frontend" "Run frontend locally only"
	@printf "    %-23s %s\n" "make start" "Run backend + frontend concurrently (local)"
	@printf "    %-23s %s\n" "make stop" "Stop local dev servers"
	@echo ""
	@echo "  $(YELLOW)🔍 Code Quality$(NC)"
	@printf "    %-23s %s\n" "make lint" "Lint backend + frontend"
	@printf "    %-23s %s\n" "make format" "Auto-fix code style issues"
	@printf "    %-23s %s\n" "make type-check" "Run Python + TypeScript type checks"
	@printf "    %-23s %s\n" "make test" "Run all tests"
	@echo ""
	@echo "  $(YELLOW)🚀 Build & Deploy$(NC)"
	@printf "    %-23s %s\n" "make build" "Build frontend + backend for production"
	@printf "    %-23s %s\n" "make preview" "Preview built frontend"

# ============================================================
# ⚙️ Development Environment Setup
# ============================================================

.PHONY: setup-dev setup-dev-assets copy-env gen-certs

setup-dev: setup-dev-assets install
	@echo "$(GREEN)🚀 Starting Postgres (detached)...$(NC)"
	@docker compose -f $(COMPOSE_FILE_DEV) up -d db

	@echo "$(GREEN)⏳ Waiting for Postgres to become ready...$(NC)"
	@until docker compose -f $(COMPOSE_FILE_DEV) exec db pg_isready -U simboard -d simboard > /dev/null 2>&1; do \
		printf "."; \
		sleep 1; \
	done
	@echo "$(GREEN)\n✅ Postgres is ready!$(NC)"

	@echo "$(GREEN)📜 Applying migrations + seeding database...$(NC)"
	cd $(BACKEND_DIR) && make db-init

	@echo "$(GREEN)✨ Development environment is ready!$(NC)"
	@echo "$(GREEN)➡️  Run 'make backend' and 'make frontend' in separate terminals$(NC)"

setup-dev-docker: setup-dev-assets install
	@echo "$(GREEN)🚀 Building all Docker containers...$(NC)"
	make docker-build env=dev

	@echo "$(GREEN)🐳 Starting Postgres (detached)...$(NC)"
	docker compose -f $(COMPOSE_FILE_DEV) up -d db

	@echo "$(GREEN)⏳ Waiting for Postgres to be ready...$(NC)"
	@until docker compose -f $(COMPOSE_FILE_DEV) exec db pg_isready -U simboard -d simboard > /dev/null 2>&1; do \
		printf "."; \
		sleep 1; \
	done
	@echo "$(GREEN)\n✅ Postgres ready!$(NC)"

	@echo "$(GREEN)🐳 Starting backend container (detached, for migrations)...$(NC)"
	docker compose -f $(COMPOSE_FILE_DEV) up -d backend

	@echo "$(GREEN)⏳ Waiting for backend to start...$(NC)"
	@until docker compose -f $(COMPOSE_FILE_DEV) exec backend ls > /dev/null 2>&1; do \
		printf "."; \
		sleep 1; \
	done
	@echo "$(GREEN)\n✅ Backend started!$(NC)"

	@echo "$(GREEN)📜 Applying migrations + seeding database...$(NC)"
	make db-init

	@echo "$(GREEN)✨ Dev environment initialized inside Docker!$(NC)"
	@echo "$(YELLOW)➡️  Next steps:$(NC)"
	@echo "   Open two terminals and run:"
	@echo "     1️⃣  $(CYAN)make docker-up env=dev svc=backend$(NC)"
	@echo "     2️⃣  $(CYAN)make docker-up env=dev svc=frontend$(NC)"


setup-dev-assets: copy-env gen-certs
	@echo "$(GREEN)✨ Development environment assets are ready!$(NC)"

copy-env:
	@echo "$(GREEN)Copying .env.example → .env...$(NC)"
	@for dir in . $(BACKEND_DIR) $(FRONTEND_DIR); do \
		loc=$$([ "$$dir" = "." ] && echo "root" || echo "$$dir"); \
		src="$$dir/.env.example"; \
		dst="$$dir/.env"; \
		if [ -f "$$dst" ]; then \
			echo "$(YELLOW)⚠️  $$dst exists, skipping...$(NC)"; \
		elif [ -f "$$src" ]; then \
			cp "$$src" "$$dst"; \
			echo "$(GREEN)✅ Copied $$src → $$dst$(NC)"; \
		else \
			echo "$(YELLOW)⚠️  No .env.example in $$loc$(NC)"; \
		fi; \
	done

gen-certs:
	@echo "$(GREEN)🔐 Generating self-signed dev SSL certificates...$(NC)"
	@cd certs && ./generate-dev-certs.sh

# ============================================================
# 🐳 Docker & Container Commands
# ============================================================

COMPOSE_FILE_DEV  := docker-compose.dev.yml
COMPOSE_FILE_PROD := docker-compose.yml

.DEFAULT_GOAL := docker-help

# Default environment = dev
env ?= dev

COMPOSE_FILE := $(if $(filter prod,$(env)),$(COMPOSE_FILE_PROD),$(COMPOSE_FILE_DEV))
ENV_TYPE     := $(if $(filter prod,$(env)),production,development)

require-svc:
	@if [ -z "$(svc)" ]; then echo "$(RED)❌ Please specify -svc=<service>$(NC)"; exit 1; fi

.PHONY: docker-help docker-build docker-rebuild docker-up docker-up-detached docker-down docker-restart docker-logs docker-shell docker-ps docker-config docker-prune docker-clean-volumes

docker-help:
	@echo "$(YELLOW)Available Docker commands:$(NC)"
	@echo ""
	@echo "  $(YELLOW)🛠️  Build & Start$(NC)"
	@printf "    %-43s %s\n" "make docker-build env=<dev|prod> svc=<service>" "Build images"
	@printf "    %-43s %s\n" "make docker-rebuild env=<dev|prod> svc=<service>" "Rebuild images (no cache)"
	@printf "    %-43s %s\n" "make docker-up env=<dev|prod> svc=<service>" "Start containers"
	@printf "    %-43s %s\n" "make docker-up-detached env=<dev|prod> svc=<service>" "Start containers (detached)"
	@printf "    %-43s %s\n" "make docker-down env=<dev|prod>" "Stop and remove containers"
	@echo ""
	@echo "  $(YELLOW)🔄 Manage$(NC)"
	@printf "    %-43s %s\n" "make docker-restart env=<dev|prod> svc=<service>" "Restart a specific container"
	@printf "    %-43s %s\n" "make docker-ps env=<dev|prod>" "List running containers"
	@printf "    %-43s %s\n" "make docker-config env=<dev|prod>" "View merged Compose configuration"
	@echo ""
	@echo "  $(YELLOW)🔍 Inspect & Debug$(NC)"
	@printf "    %-43s %s\n" "make docker-logs env=<dev|prod> svc=<service>" "Tail container logs"
	@printf "    %-43s %s\n" "make docker-shell env=<dev|prod> svc=<service>" "Open bash shell inside a container"
	@echo ""
	@echo "  $(YELLOW)🧹 Clean$(NC)"
	@printf "    %-43s %s\n" "make docker-prune" "Clean unused Docker resources"
	@printf "    %-43s %s\n" "make docker-clean-volumes env=<dev|prod>" "Remove ALL Docker volumes (danger!)"

docker-build:
	docker compose -f $(COMPOSE_FILE) build --build-arg ENV=$(ENV_TYPE) $(svc)

docker-rebuild:
	docker compose -f $(COMPOSE_FILE) build --build-arg ENV=$(ENV_TYPE) --no-cache $(svc)

docker-up:
ifeq ($(env),dev)
ifeq ($(svc),backend)
	docker compose -f $(COMPOSE_FILE) up --watch backend
else
	docker compose -f $(COMPOSE_FILE) up $(svc)
endif
else
	docker compose -f $(COMPOSE_FILE) up -d $(svc)
endif

docker-up-detached:
ifeq ($(env),dev)
ifeq ($(svc),backend)
	docker compose -f $(COMPOSE_FILE) up -d --watch backend
else
	docker compose -f $(COMPOSE_FILE) up -d $(svc)
endif
else
	docker compose -f $(COMPOSE_FILE) up -d $(svc)
endif

docker-down:
	docker compose -f $(COMPOSE_FILE) down

docker-restart: require-svc
	docker compose -f $(COMPOSE_FILE) restart $(svc)

docker-logs: require-svc
	docker compose -f $(COMPOSE_FILE) logs -f $(svc)

docker-shell: require-svc
	docker compose -f $(COMPOSE_FILE) exec $(svc) bash

docker-ps:
	docker compose -f $(COMPOSE_FILE) ps

docker-config:
	docker compose -f $(COMPOSE_FILE) config

docker-prune:
	@echo "$(RED)⚠️  Warning: This will remove all unused Docker resources!$(NC)"
	@read -p "Are you sure you want to proceed? (y/N): " confirm && [ "$$confirm" = "y" ]
	docker system prune -f

docker-clean-volumes:
	@echo "$(RED)⚠️  Warning: This will remove ALL Docker volumes, including Postgres data!$(NC)"
	@read -p "Are you sure you want to proceed? (y/N): " confirm && [ "$$confirm" = "y" ]
	docker compose -f $(COMPOSE_FILE) down -v

# ============================================================
# 🗃️ Docker Database Commands
# ============================================================

.PHONY: db-migrate db-upgrade db-rollback db-seed db-rollback db-init

# Create new Alembic migration inside the backend container
db-migrate:
	@echo "$(GREEN)📜 Creating new Alembic migration...$(NC)"
	docker compose -f docker-compose.dev.yml exec backend uv run alembic revision --autogenerate -m "$(m)"

# Apply all Alembic migrations inside backend container
db-upgrade:
	@echo "$(GREEN)🚀 Applying Alembic migrations...$(NC)"
	docker compose -f docker-compose.dev.yml exec backend uv run alembic upgrade head

# Roll back last Alembic migration inside backend container
db-rollback:
	@echo "$(YELLOW)⏪ Rolling back last Alembic migration...$(NC)"
	docker compose -f docker-compose.dev.yml exec backend uv run alembic downgrade -1

# Seed database with dummy data (safe for dev only)
db-seed:
	@if [ "$(e)" != "prod" ]; then \
		echo "$(GREEN)🌱 Seeding dummy data into Postgres...$(NC)"; \
		docker compose -f docker-compose.dev.yml exec backend uv run python app/scripts/seed.py; \
	else \
		echo "⚠️  Seeding disabled in production environment"; \
	fi

# Roll back dummy data (optional)
db-rollback-seed:
	@if [ "$(e)" != "prod" ]; then \
		echo "$(YELLOW)Rolling back dummy data...$(NC)"; \
		docker compose -f docker-compose.dev.yml exec backend uv run python app/scripts/rollback_seed.py; \
	else \
		echo "⚠️  Rolling back dummy data disabled in production"; \
	fi

# Initialize database (migrate + seed)
db-init:
	@echo "$(GREEN)🚀 Initializing database (apply migrations + seed)...$(NC)"
	make e=$(e) db-upgrade
	make e=$(e) db-seed

# ============================================================
# ⚙️ Local Environment Setup
# ============================================================

.PHONY: install clean

install:
	@test -d $(BACKEND_DIR) || (echo "$(RED)❌ Missing backend directory$(NC)" && exit 1)
	@test -d $(FRONTEND_DIR) || (echo "$(RED)❌ Missing frontend directory$(NC)" && exit 1)
	@echo "$(GREEN)Installing dependencies for backend and frontend...$(NC)"
	cd $(BACKEND_DIR) && make install
	cd $(FRONTEND_DIR) && make install

clean:
	@echo "$(GREEN)Cleaning build artifacts and node_modules...$(NC)"
	cd $(BACKEND_DIR) && make clean
	cd $(FRONTEND_DIR) && make clean


# ============================================================
# 🧑‍💻 Local Development Utilities
# ============================================================

.PHONY: backend frontend start stop

backend:
	@echo "$(GREEN)Starting backend locally...$(NC)"
	cd $(BACKEND_DIR) && make reload

frontend:
	@echo "$(GREEN)Starting frontend locally...$(NC)"
	cd $(FRONTEND_DIR) && make dev

start:
	@echo "$(GREEN)Starting backend and frontend concurrently...$(NC)"
	@{ \
		cd $(BACKEND_DIR) && make reload & \
		BACK_PID=$$!; \
		cd $(FRONTEND_DIR) && make dev; \
		echo "$(YELLOW)Stopping backend...$(NC)"; \
		kill $$BACK_PID || true; \
	}

stop:
	@echo "$(YELLOW)Stopping local backend and frontend...$(NC)"
	@pkill -f "uvicorn" || true
	@pkill -f "vite" || true


# ============================================================
# 🔍 Code Quality
# ============================================================

.PHONY: lint format type-check test

lint:
	@echo "$(GREEN)Linting backend and frontend...$(NC)"
	cd $(BACKEND_DIR) && make lint
	cd $(FRONTEND_DIR) && make lint

format:
	@echo "$(GREEN)Formatting backend and frontend code...$(NC)"
	cd $(BACKEND_DIR) && make format
	cd $(FRONTEND_DIR) && make format

type-check:
	@echo "$(GREEN)Running type checks...$(NC)"
	cd $(BACKEND_DIR) && make type-check || true
	cd $(FRONTEND_DIR) && make type-check

test:
	@echo "$(GREEN)Running backend and frontend tests...$(NC)"
	cd $(BACKEND_DIR) && make test
	cd $(FRONTEND_DIR) && make test


# ============================================================
# 🚀 Build & Deploy
# ============================================================

.PHONY: build preview

build:
	@echo "$(GREEN)Building backend and frontend...$(NC)"
	cd $(BACKEND_DIR) && make build || true
	cd $(FRONTEND_DIR) && make build

preview:
	@echo "$(GREEN)Previewing frontend build...$(NC)"
	cd $(FRONTEND_DIR) && make preview


