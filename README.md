# SimBoard

SimBoard is a platform for managing and comparing Earth system simulation metadata, with a focus on **E3SM** (Energy Exascale Earth System Model) reference simulations.

The goal of SimBoard is to provide researchers with tools to:

- Store and organize simulation metadata
- Browse and visualize simulation details
- Compare runs side-by-side
- Surface diagnostics and key information for analysis

---

## 🚀 Prerequisites

1. Install **Docker Desktop**: [Download here](https://www.docker.com/products/docker-desktop) and ensure it's running.

2. Install **uv** (Python package/dependency manager):

   ```bash
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Windows (PowerShell)
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Verify the installation:

   ```bash
   uv --version
   ```

3. Install **Node.js**, **npm**, and **pnpm**:

   Install Node.js (which includes npm):

   - Download and install from the official site: https://nodejs.org
     - Recommended: **LTS** version

   Verify the installation:

   ```bash
   node --version
   npm --version
   ```

   Install **pnpm** globally using npm:

   ```bash
   npm install -g pnpm
   ```

   Verify the pnpm installation:

   ```bash
   pnpm --version
   ```

4. Clone the repository:

   ```bash
   git clone https://github.com/<your-org>/simboard.git
   ```

## 🚀 Developer Quickstart with Local Development Environments (Bare-Metal)

The bare-metal local development environments are ideal for rapid development and testing of
code. **It is the suggested choice of day-to-day coding.**

- Instant reloads, best debugging, quickest pytest runs
- Use your machine's Python/Node installations
  > ⚠️ **Warning:** This setup is for local development only and is **not production-accurate**. Do **not** use these configurations as-is for any production environment.

Commands:

```bash
# 1. Enter the repository
cd simboard

# 2. Create .env files and configure as needed
# After running `make copy-env`, open `backend/.env` and configure these settings
# using the bare-metal variables.
#   - POSTGRES_SERVER: The hostname or IP address of your PostgreSQL server (e.g., localhost)
#   - DATABASE_URL: The connection string for your main development database
#   - TEST_DATABASE_URL: The connection string for your test database
make copy-env

# 3. Build and install the environments for frontend and backend
make install

# 4. Build the database container using Docker
make docker-up e=dev svc=db

# 5. Apply database migrations and seed the database
make db-upgrade
make db-seed

# 6. Start backend.
make backend

# 7. Start frontend.
make frontend

# 8. Open the API and UI
open http://127.0.0.1:8000/docs       # Backend Swagger UI
open http://127.0.0.1:5173            # Frontend web app

# 9. Run linters and type checks (optional)
make lint
make type-check
```

## 🚀 Developer Quickstart with Docker Development Environments

The Docker Development Environments are ideal for validating that SimBoard works
inside Docker before deploying.

- Matches production environment (Python version, OS libs, networking)
- Catches Dockerfile issues early
- Lets you test the full stack together (frontend ↔ backend ↔ DB)
- Slower than bare-metal, used for integration validation
- Great for team onboarding

Commands:

```bash
# 1. Enter the repository
cd simboard

# 2. Create .env files and configure as needed
make copy-env

# 2. Build docker containers
make docker-build e=dev

# 3. Start docker containers (database, backend, frontend)
make docker-up e=dev

# 4. Apply database migrations and seed the database
make db-upgrade
make db-seed

# 5. Open the API and UI
open http://127.0.0.1:8000/docs       # Backend Swagger UI
open http://127.0.0.1:5173            # Frontend web app

# 6. Run linters and type checks (optional)
make lint
make type-check
```

---

## Table of Contents

- [Repository Structure](#repository-structure)
- [Development](#development)
- [🧰 Project Makefile Commands](#-project-makefile-commands)
- [🔐 Local HTTPS / Traefik Setup](#-local-https--traefik-setup)
- [License](#license)

---

## Repository Structure

```bash
.
├── backend/     # FastAPI, PostgreSQL, SQLAlchemy, Alembic, Pydantic
├── frontend/    # Web app (Vite/React + Tailwind + shadcn)
└── README.md    # This file
```

Each component has its own README with setup instructions:

- [Backend README](./backend/README.md)
- [Frontend README](./frontend/README.md)

---

## Development

- Docker is used for containerized development and deployment.
  - Run `make docker-help` to view all available Docker commands.
  - Ensure Docker Desktop is running before executing these commands.
- Backend dependencies are managed with **Poetry**.
- Frontend dependencies are managed with **pnpm**.
- Use **[GitHub Issues](https://github.com/E3SM-Project/simboard/issues)** for feature requests and tracking.
- Contributions should include tests and documentation updates.

---

## 🧰 Project Makefile Commands

This repository includes a **top-level Makefile** that orchestrates both the backend and frontend.

Run `make help` to view all available commands.

## 🔐 Local HTTPS / Traefik Setup

SimBoard uses **Traefik** as a reverse proxy to handle HTTPS and routing between the frontend and backend.

### Why Traefik?

- Simplifies local HTTPS with self-signed or automatic certificates (via Let's Encrypt).
- Provides a unified entry point for multiple services (`frontend`, `backend`, etc.).
- Automatically handles routing and load balancing.

## License

TBD
