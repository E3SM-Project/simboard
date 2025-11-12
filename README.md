# EarthFrame

EarthFrame is a platform for managing and comparing Earth system simulation metadata, with a focus on **E3SM** (Energy Exascale Earth System Model) reference simulations.

The goal of EarthFrame is to provide researchers with tools to:

- Store and organize simulation metadata
- Browse and visualize simulation details
- Compare runs side-by-side
- Surface diagnostics and key information for analysis

---

## 🚀 Developer Quickstart

Get started in **five simple commands**:

```bash
# 1. Clone the repository
git clone https://github.com/<your-org>/earthframe.git
cd earthframe

# 2. Install dependencies for backend and frontend
make install

# 3. Start both services (backend + frontend)
make start

# 4. Open the API and UI
open http://127.0.0.1:8000/docs       # Backend Swagger UI
open http://127.0.0.1:5173            # Frontend web app

# 5. Run linters and type checks (optional)
make lint
make type-check
```

---

## Table of Contents

- [Repository Structure](#repository-structure)
- [Development](#development)
- [🧰 Project Makefile Commands](#-project-makefile-commands)
  - [Setup & Environment](#setup--environment)
  - [Development](#development-1)
  - [Database & Migrations](#database--migrations)
  - [Code Quality](#code-quality)
  - [Build & Preview](#build--preview)
  - [Example Workflow](#example-workflow)
- [🐳 Docker & Docker Compose Commands](#-docker--docker-compose-commands)
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

- Backend dependencies are managed with **Poetry**.
- Frontend dependencies are managed with **pnpm**.
- Use **[GitHub Issues](https://github.com/E3SM-Project/earthframe/issues)** for feature requests and tracking.
- Contributions should include tests and documentation updates.

---

## 🧰 Project Makefile Commands

This repository includes a **top-level Makefile** that orchestrates both the backend and frontend.

Run `make help` to view all available commands.

### Setup & Environment

| Command        | Description                                    | Equivalent Command                                             |
| -------------- | ---------------------------------------------- | -------------------------------------------------------------- |
| `make install` | Install dependencies for backend and frontend. | `cd backend && ruff install && cd ../frontend && pnpm install` |
| `make clean`   | Remove build artifacts and node_modules.       | `cd backend && make clean && cd ../frontend && make clean`     |

---

### Development

| Command         | Description                               | Equivalent Command                                     |
| --------------- | ----------------------------------------- | ------------------------------------------------------ |
| `make start`    | Start backend and frontend concurrently.  | `make reload` (backend) + `make dev` (frontend)        |
| `make backend`  | Run backend (FastAPI) development server. | `cd backend && ruff run uvicorn app.main:app --reload` |
| `make frontend` | Run frontend (Vite) development server.   | `cd frontend && pnpm dev`                              |

---

### Database & Migrations

| Command                | Description                       | Equivalent Command                                                |
| ---------------------- | --------------------------------- | ----------------------------------------------------------------- |
| `make migrate m="msg"` | Generate a new Alembic migration. | `cd backend && ruff run alembic revision --autogenerate -m "msg"` |
| `make upgrade`         | Apply all pending migrations.     | `cd backend && ruff run alembic upgrade head`                     |

---

### Code Quality

| Command           | Description                                 | Equivalent Command                                                    |
| ----------------- | ------------------------------------------- | --------------------------------------------------------------------- |
| `make lint`       | Run linters for both backend and frontend.  | `cd backend && ruff check . && cd ../frontend && pnpm lint`           |
| `make format`     | Auto-fix code style issues.                 | `cd backend && ruff check . --fix && cd ../frontend && pnpm lint:fix` |
| `make type-check` | Run TypeScript type checks (frontend only). | `cd frontend && pnpm type-check`                                      |

---

### Build & Preview

| Command        | Description                                | Equivalent Command            |
| -------------- | ------------------------------------------ | ----------------------------- |
| `make build`   | Build frontend for production.             | `cd frontend && pnpm build`   |
| `make preview` | Preview frontend production build locally. | `cd frontend && pnpm preview` |

---

### Example Workflow

```bash
# 1. Install everything
make install

# 2. Run both backend and frontend
make start

# 3. Generate and apply a new database migration
make migrate m="Add user table"
make upgrade

# 4. Lint and fix code
make lint
make format
```

## 🐳 Docker & Docker Compose Commands

Useful commands for building, running, and debugging containers.

This table is equivalent to `make docker-help`.

| Command                                      | Equivalent Command                                                                      | Description                            |
| -------------------------------------------- | --------------------------------------------------------------------------------------- | -------------------------------------- |
| `make docker-build e=<type> svc=<service>`   | `docker compose -f $(COMPOSE_FILE) build --build-arg ENV=$(ENV_TYPE) $(svc)`            | Build images (dev/prod).               |
| `make docker-rebuild e=<type> svc=<service>` | `docker compose -f $(COMPOSE_FILE) build --build-arg ENV=$(ENV_TYPE) --no-cache $(svc)` | Rebuild images (no cache).             |
| `make docker-up e=<type> svc=<service>`      | `docker compose -f $(COMPOSE_FILE) up -d $(svc)` (or `--watch` for dev)                 | Start containers (detached).           |
| `make docker-down e=<type>`                  | `docker compose -f $(COMPOSE_FILE) down`                                                | Stop and remove containers.            |
| `make docker-logs e=<type> svc=<service>`    | `docker compose -f $(COMPOSE_FILE) logs -f $(svc)`                                      | Tail container logs.                   |
| `make docker-shell e=<type> svc=<service>`   | `docker compose -f $(COMPOSE_FILE) exec $(svc) bash`                                    | Open bash shell inside container.      |
| `make docker-prune`                          | `docker system prune -f`                                                                | Clean up unused Docker resources.      |
| `make docker-ps`                             | `docker compose -f $(COMPOSE_FILE) ps`                                                  | List running containers.               |
| `make docker-restart svc=<service>`          | `docker compose -f $(COMPOSE_FILE) restart $(svc)`                                      | Restart a specific container.          |
| `make docker-config`                         | `docker compose -f $(COMPOSE_FILE) config`                                              | View merged Compose configuration.     |
| `make docker-clean-volumes`                  | `docker compose -f $(COMPOSE_FILE) down -v`                                             | Remove all volumes (use with caution). |

## 🔐 Local HTTPS / Traefik Setup

EarthFrame can be containerized with **Traefik** as a reverse proxy to handle HTTPS and routing between the frontend and backend.

### Why Traefik?

- Simplifies local HTTPS with self-signed or automatic certificates (via Let's Encrypt).
- Provides a unified entry point for multiple services (`frontend`, `backend`, etc.).
- Automatically handles routing and load balancing.

## License

TBD
