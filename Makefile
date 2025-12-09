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
# ⚙️ Environment File Setup
# ============================================================

.PHONY: copy-env

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

.PHONY: docker-help docker-build docker-rebuild docker-up docker-down docker-restart docker-logs docker-shell docker-ps docker-config docker-prune docker-clean-volumes

docker-help:
	@echo "$(YELLOW)Available Docker commands:$(NC)"
	@printf "  %-45s %s\n" "make docker-build env=<dev|prod> svc=<service>" "Build images"
	@printf "  %-45s %s\n" "make docker-rebuild env=<dev|prod> svc=<service>" "Rebuild images (no cache)"
	@printf "  %-45s %s\n" "make docker-up env=<dev|prod> svc=<service>" "Start containers"
	@printf "  %-45s %s\n" "make docker-down env=<dev|prod>" "Stop and remove containers"
	@printf "  %-45s %s\n" "make docker-restart env=<dev|prod> svc=<service>" "Restart a specific container"
	@printf "  %-45s %s\n" "make docker-logs env=<dev|prod> svc=<service>" "Tail container logs"
	@printf "  %-45s %s\n" "make docker-shell env=<dev|prod> svc=<service>" "Open bash shell inside a container"
	@printf "  %-45s %s\n" "make docker-ps env=<dev|prod>" "List running containers"
	@printf "  %-45s %s\n" "make docker-config env=<dev|prod>" "View merged Compose configuration"
	@printf "  %-45s %s\n" "make docker-prune" "Clean unused Docker resources"
	@printf "  %-45s %s\n" "make docker-clean-volumes env=<dev|prod>" "Remove ALL Docker volumes (danger!)"

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
	@echo "$(GREEN)🚀 Initializing database (migrate + seed)...$(NC)"
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


# ============================================================
# 🧭 Help
# ============================================================

.PHONY: help

help:
	@echo "$(YELLOW)Available top-level commands:$(NC)"
	@printf "  %-25s %s\n" "make docker-help" "List Docker management commands"
	@printf "  %-25s %s\n" "make db-migrate m='msg'" "Create Alembic migration (in Docker)"
	@printf "  %-25s %s\n" "make db-upgrade" "Apply Alembic migrations (in Docker)"
	@printf "  %-25s %s\n" "make db-rollback" "Rollback last Alembic migration (in Docker)"
	@printf "  %-25s %s\n" "make db-seed" "Seed dummy data (in Docker)"
	@printf "  %-25s %s\n" "make db-rollback-seed" "Rollback dummy data (in Docker)"
	@printf "  %-25s %s\n" "make db-init" "Migrate + seed database (in Docker)"
	@printf "  %-25s %s\n" "make install" "Install local dependencies"
	@printf "  %-25s %s\n" "make clean" "Clean caches and build artifacts"
	@printf "  %-25s %s\n" "make start" "Run backend + frontend concurrently (local)"
	@printf "  %-25s %s\n" "make backend" "Run backend locally only"
	@printf "  %-25s %s\n" "make frontend" "Run frontend locally only"
	@printf "  %-25s %s\n" "make stop" "Stop local dev servers"
	@printf "  %-25s %s\n" "make lint" "Lint backend + frontend"
	@printf "  %-25s %s\n" "make format" "Auto-fix code style issues"
	@printf "  %-25s %s\n" "make type-check" "Run Python + TypeScript type checks"
	@printf "  %-25s %s\n" "make test" "Run all tests"
	@printf "  %-25s %s\n" "make build" "Build frontend + backend for production"
	@printf "  %-25s %s\n" "make preview" "Preview built frontend"
	@printf "  %-25s %s\n" "make copy-env" "Copy .env.example to .env for all projects"
