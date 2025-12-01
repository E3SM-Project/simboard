# SimBoard

SimBoard is a platform for managing and comparing Earth system simulation metadata, with a focus on **E3SM** (Energy Exascale Earth System Model) reference simulations.

The goal of SimBoard is to provide researchers with tools to:

- Store and organize simulation metadata
- Browse and visualize simulation details
- Compare runs side-by-side
- Surface diagnostics and key information for analysis

---

## 🚀 Developer Quickstart

Get started in **five simple commands**:

```bash
# 1. Clone the repository
git clone https://github.com/<your-org>/simboard.git
cd simboard

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
- Use **[GitHub Issues](https://github.com/E3SM-Project/simboard/issues)** for feature requests and tracking.
- Contributions should include tests and documentation updates.

---

## 🧰 Project Makefile Commands

This repository includes a **top-level Makefile** that orchestrates both the backend and frontend.

Run `make help` to view all available commands.

## 🔐 Local HTTPS / Traefik Setup

SimBoard can be containerized with **Traefik** as a reverse proxy to handle HTTPS and routing between the frontend and backend.

### Why Traefik?

- Simplifies local HTTPS with self-signed or automatic certificates (via Let's Encrypt).
- Provides a unified entry point for multiple services (`frontend`, `backend`, etc.).
- Automatically handles routing and load balancing.

## License

TBD
