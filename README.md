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

2. Clone the repository:

   ```bash
   git clone https://github.com/<your-org>/simboard.git
   ```

3. Configure `.env` files: Update the root, `/backend`, and `/frontend` `.env` files with required values.

## 🚀 Developer Quickstart with Docker

Get started in **six simple commands**:

```bash
# 1. Enter the repository
cd simboard

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
