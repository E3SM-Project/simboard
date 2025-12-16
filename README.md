# SimBoard

SimBoard is a platform for managing and comparing Earth system simulation metadata, with a focus on **E3SM** (Energy Exascale Earth System Model) reference simulations.

SimBoard helps researchers:

- Store and organize simulation metadata
- Browse and visualize simulation details
- Compare runs side-by-side
- Surface diagnostics and metadata-driven insights

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Developer Quickstart (Bare-Metal)](#developer-quickstart-bare-metal)
- [Developer Quickstart (Docker)](#developer-quickstart-docker)
- [Environment System](#environment-system)
- [Repository Structure](#repository-structure)
- [Development Notes](#development-notes)
- [Makefile Overview](#makefile-overview)
- [Local HTTPS](#local-https)
- [License](#license)

---

## Prerequisites

### 1. Install Docker Desktop

[https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
Ensure it is running before any Docker-based commands.

---

### 2. Install uv (Python dependency manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
```

Verify:

```bash
uv --version
```

---

### 3. Install Node.js, npm, and pnpm

Install Node (LTS recommended): [https://nodejs.org](https://nodejs.org)

```bash
node --version
npm --version
```

Install pnpm:

```bash
npm install -g pnpm
pnpm --version
```

---

### 4. Clone the repository

```bash
git clone https://github.com/<your-org>/simboard.git
cd simboard
```

---

## Developer Quickstart (Bare-Metal)

This is the **recommended daily workflow**:

- Fastest hot reloads
- Best debugging experience
- No Docker overhead

> ⚠️ Bare-metal dev is _not production-accurate_ — it is optimized for speed.

### Commands

```bash
cd simboard

# 1. Setup development assets (env files + certs + deps)
make setup-dev env=local

# 2. Start backend (terminal 1)
make backend-reload env=local

# 3. Start frontend (terminal 2)
make frontend-dev env=local

# 4. Open API and UI
open https://127.0.0.1:8000/docs
open https://127.0.0.1:5173
```

Optional:

```bash
make lint
make type-check
make test
```

---

## Developer Quickstart (Docker)

Use this workflow when you need **production-like dev**:

- Same OS/runtime
- Validates Docker networking, build steps
- Ideal for integration testing

### Commands

```bash
cd simboard

# Build images, generate envs, run migrations, seed DB
make setup-dev-docker env=local_docker

# Start backend container
make docker-up env=local_docker svc=backend

# Start frontend container
make docker-up env=local_docker svc=frontend

# Open API and UI
open https://127.0.0.1:5173
open https://127.0.0.1:8000/docs
```

---

## Environment System

SimBoard uses a **multi-environment .env layout**:

```
.envs/
  local/
    backend.env
    frontend.env
  local_docker/
    backend.env
    frontend.env
  production/
    backend.env
    frontend.env
```

Environment selection is controlled by:

```
env=<name>
```

Example:

```bash
make backend-reload env=local
make frontend-dev env=local_docker
make docker-up env=production svc=backend
```

Under the hood, everything receives:

```
APP_ENV=$(env)
```

Backend and frontend automatically load:

```
.envs/<env>/backend.env
.envs/<env>/frontend.env
```

---

## GitHub OAuth Configuration

Set these in the appropriate environment folder, e.g.:

```
.envs/local/backend.env
```

```env
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret

# Must match GitHub OAuth config
GITHUB_REDIRECT_URL=https://127.0.0.1:8000/auth/github/callback

# Generate securely:
# python -c "import secrets; print(secrets.token_urlsafe(64))"
GITHUB_STATE_SECRET_KEY=your_secret
```

---

## Repository Structure

```
simboard/
├── backend/        # FastAPI, SQLAlchemy, Alembic, OAuth, metadata ingestion
├── frontend/       # Vite + React + Tailwind + shadcn
├── .envs/          # local / local_docker / production environment sets
├── docker-compose.dev.yml
├── docker-compose.yml
├── Makefile        # unified monorepo automation
└── certs/          # dev HTTPS certificates
```

---

## Development Notes

- Backend dependencies managed using **uv**
- Frontend dependencies managed using **pnpm**
- Environment switching handled automatically via `APP_ENV`
- `.envs/<env>` contains all environment-specific configs
- Docker Compose uses `.envs/local_docker/*` when running containers

Use GitHub Issues to report bugs or propose features.
Pull requests should include tests + documentation updates.

---

## Makefile Overview

The Makefile provides **unified commands** for backend, frontend, Docker, DB, and environment management.

### Examples

#### Backend

```
make backend-install
make backend-reload env=local
make backend-migrate m="msg"
make backend-test
```

#### Frontend

```
make frontend-dev env=local
make frontend-build
make frontend-lint
```

#### Docker

```
make docker-up env=local_docker svc=backend
make docker-up env=local_docker svc=frontend
```

#### Database

```
make db-init env=local
make db-upgrade env=local_docker
```

View full list:

```bash
make help
```

---

## Local HTTPS

SimBoard uses **local HTTPS** with development certificates:

```
certs/dev.crt
certs/dev.key
```

Generated via:

```bash
make gen-certs
```

Used automatically by:

- FastAPI (Uvicorn SSL)
- Vite (via VITE_SSL_CERT and VITE_SSL_KEY)

---

## License

TBD
