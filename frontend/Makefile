# ============================================================
#  SimBoard Frontend Makefile
#  Description: Common developer commands for local use
# ============================================================

# Colors
GREEN=\033[0;32m
NC=\033[0m

# ============================================================
#  Setup & Environment
# ============================================================

.PHONY: install clean

install:
	@echo "$(GREEN)Installing dependencies with pnpm...$(NC)"
	pnpm install

clean:
	@echo "$(GREEN)Cleaning build artifacts and node_modules...$(NC)"
	rm -rf node_modules dist .turbo

# ============================================================
#  Development & Build
# ============================================================

.PHONY: dev build preview type-check

dev:
	@echo "$(GREEN)Starting Vite development server...$(NC)"
	pnpm dev

build:
	@echo "$(GREEN)Building TypeScript and Vite project...$(NC)"
	pnpm build

preview:
	@echo "$(GREEN)Previewing production build...$(NC)"
	pnpm preview

type-check:
	@echo "$(GREEN)Running TypeScript type check...$(NC)"
	pnpm type-check

# ============================================================
#  Code Quality
# ============================================================

.PHONY: lint fix ci pre-commit

lint:
	@echo "$(GREEN)Linting codebase with ESLint...$(NC)"
	pnpm lint

fix:
	@echo "$(GREEN)Auto-fixing lint issues...$(NC)"
	pnpm lint:fix

ci:
	@echo "$(GREEN)Running CI checks (lint + type-check)...$(NC)"
	pnpm ci

pre-commit:
	@echo "$(GREEN)Running pre-commit checks (lint:fix + type-check)...$(NC)"
	pnpm pre-commit

# ============================================================
#  Misc
# ============================================================

.PHONY: help

help:
	@echo "$(GREEN)Available commands:$(NC)"
	@echo "  make install      - Install dependencies (pnpm install)"
	@echo "  make clean        - Remove node_modules, dist, and .turbo"
	@echo "  make dev          - Start Vite development server"
	@echo "  make build        - Build TypeScript and Vite project"
	@echo "  make preview      - Preview production build"
	@echo "  make type-check   - Run TypeScript type check"
	@echo "  make lint         - Lint codebase with ESLint"
	@echo "  make fix          - Auto-fix lint issues"
	@echo "  make ci           - Run CI checks (lint + type-check)"
	@echo "  make pre-commit   - Run pre-commit checks (lint:fix + type-check)"
