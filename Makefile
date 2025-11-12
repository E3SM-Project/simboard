# ============================================================
#  🌍 EarthFrame Project Makefile
#  Unified project-level commands for backend & frontend
# ============================================================

# Colors
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m

# Directories
BACKEND_DIR  := backend
FRONTEND_DIR := frontend

# ============================================================
# 🐳 Docker & Container Commands
# ============================================================

# Compose files
COMPOSE_FILE_DEV  := docker-compose.dev.yml
COMPOSE_FILE_PROD := docker-compose.yml

# Default goal
.DEFAULT_GOAL := docker-help

# Unified environment selector
COMPOSE_FILE := $(if $(filter prod,$(e)),$(COMPOSE_FILE_PROD),$(COMPOSE_FILE_DEV))
ENV_TYPE     := $(if $(filter prod,$(e)),production,development)

# Guard for required service
require-svc:
	@if [ -z "$(svc)" ]; then echo "$(RED)❌ Please specify -svc=<service>$(NC)"; exit 1; fi

# Docker commands
.PHONY: docker-help docker-build docker-rebuild docker-up docker-down docker-restart docker-logs docker-shell docker-ps docker-config docker-prune docker-clean-volumes

docker-help:
	@echo "$(YELLOW)Available Docker commands:$(NC)"
	@printf "  %-45s %s\n" "make docker-build e=<type> svc=<service>" "Build images (dev/prod)"
	@printf "  %-45s %s\n" "make docker-rebuild e=<type> svc=<service>" "Rebuild images (no cache)"
	@printf "  %-45s %s\n" "make docker-up e=<type> svc=<service>" "Start containers (detached)"
	@printf "  %-45s %s\n" "make docker-down e=<type>" "Stop and remove containers"
	@printf "  %-45s %s\n" "make docker-restart svc=<service>" "Restart a specific container"
	@printf "  %-45s %s\n" "make docker-logs e=<type> svc=<service>" "Tail container logs"
	@printf "  %-45s %s\n" "make docker-shell e=<type> svc=<service>" "Open bash shell inside container"
	@printf "  %-45s %s\n" "make docker-ps" "List running containers"
	@printf "  %-45s %s\n" "make docker-config" "View merged Compose configuration"
	@printf "  %-45s %s\n" "make docker-prune" "Clean up unused Docker resources"
	@printf "  %-45s %s\n" "make docker-clean-volumes" "Remove all volumes (use with caution)"

docker-build:
	docker compose -f $(COMPOSE_FILE) build --build-arg ENV=$(ENV_TYPE) $(svc)

docker-rebuild:
	docker compose -f $(COMPOSE_FILE) build --build-arg ENV=$(ENV_TYPE) --no-cache $(svc)

docker-up:
	ifeq ($(e),dev)
		docker compose -f $(COMPOSE_FILE) up --watch $(svc)
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
	@echo "$(RED)⚠️  Warning: This will remove all unused Docker resources, including stopped containers, dangling images, and unused networks!$(NC)"
	@read -p "Are you sure you want to proceed? (y/N): " confirm && [ "$$confirm" = "y" ]
	docker system prune -f

docker-clean-volumes:
	@echo "$(RED)⚠️  Warning: This will remove all volumes, including database data!$(NC)"
	@read -p "Are you sure you want to proceed? (y/N): " confirm && [ "$$confirm" = "y" ]
	docker compose -f $(COMPOSE_FILE) down -v

# ============================================================
# ⚙️ Setup & Environment
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
# 🧑‍💻 Development
# ============================================================

.PHONY: start backend frontend stop

start:
	@echo "$(GREEN)Starting backend and frontend concurrently...$(NC)"
	cd $(BACKEND_DIR) && make reload &
	BACK_PID=$$!
	cd $(FRONTEND_DIR) && make dev
	@echo "$(YELLOW)Stopping backend...$(NC)"
	@kill $$BACK_PID || true

backend:
	@echo "$(GREEN)Starting backend...$(NC)"
	cd $(BACKEND_DIR) && make reload

frontend:
	@echo "$(GREEN)Starting frontend...$(NC)"
	cd $(FRONTEND_DIR) && make dev

stop:
	@echo "$(GREEN)Stopping backend and frontend dev servers...$(NC)"
	@pkill -f "uvicorn" || true
	@pkill -f "vite" || true


# ============================================================
# 🗃️ Database & Migrations
# ============================================================

.PHONY: migrate upgrade

migrate:
	@echo "$(GREEN)Generating new Alembic migration...$(NC)"
	cd $(BACKEND_DIR) && make migrate m="$(m)"

upgrade:
	@echo "$(GREEN)Applying Alembic migrations...$(NC)"
	cd $(BACKEND_DIR) && make upgrade


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
	@printf "  %-25s %s\n" "make install" "Install all dependencies (backend + frontend)"
	@printf "  %-25s %s\n" "make clean" "Clean build and cache files"
	@printf "  %-25s %s\n" "make start" "Run backend and frontend concurrently"
	@printf "  %-25s %s\n" "make backend" "Run backend server only"
	@printf "  %-25s %s\n" "make frontend" "Run frontend dev server only"
	@printf "  %-25s %s\n" "make stop" "Stop any running dev servers"
	@printf "  %-25s %s\n" "make migrate m='msg'" "Generate Alembic migration"
	@printf "  %-25s %s\n" "make upgrade" "Apply DB migrations"
	@printf "  %-25s %s\n" "make lint" "Lint both backend and frontend"
	@printf "  %-25s %s\n" "make format" "Auto-fix code style issues"
	@printf "  %-25s %s\n" "make type-check" "Run type checks (Python + TypeScript)"
	@printf "  %-25s %s\n" "make test" "Run backend and frontend tests"
	@printf "  %-25s %s\n" "make build" "Build frontend for production"
	@printf "  %-25s %s\n" "make preview" "Preview production build"
	@printf "  %-25s %s\n" "make docker-help" "List Docker management commands"
