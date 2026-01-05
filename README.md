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
git clone https://github.com/E3SM-Project/simboard.git
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
make setup-dev env=dev

# 2. Start backend (terminal 1)
make backend-reload env=dev

# 3. Start frontend (terminal 2)
make frontend-dev env=dev

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
- Validates Docker networking & build steps
- Ideal for integration testing

### Commands

```bash
cd simboard

# Build images, generate envs, run migrations, seed DB
make setup-dev-docker env=dev_docker

# Start backend container
make docker-up env=dev_docker svc=backend

# Start frontend container
make docker-up env=dev_docker svc=frontend

# Open API and UI
open https://127.0.0.1:5173
open https://127.0.0.1:8000/docs
```

---

## Environment System

SimBoard uses a **multi-environment .env layout**:

```bash
.envs/
  dev/
    backend.env
    frontend.env
  dev_docker/
    backend.env
    frontend.env
  prod/
    backend.env
    frontend.env
```

Environment selection is controlled by:

```bash
make <command> env=<env_name>
```

Examples:

```bash
make backend-reload env=dev
make frontend-dev env=dev
make docker-up env=prod svc=backend
```

Under the hood, every command receives:

```bash
APP_ENV=$(env)
```

Backend and frontend automatically load:

```
.envs/<env>/backend.env
.envs/<env>/frontend.env
```

---

## GitHub OAuth Configuration

Environment variables must be placed in the appropriate folder, e.g.:

```bash
.envs/dev/backend.env
.envs/dev_docker/backend.env
```

Example config:

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

```bash
simboard/
├── backend/        # FastAPI, SQLAlchemy, Alembic, OAuth, metadata ingestion
├── frontend/       # Vite + React + Tailwind + shadcn
├── .envs/          # dev / dev_docker / prod environment sets
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
- Docker Compose uses `.envs/dev_docker/*` when running containers

Use [GitHub Issues](https://github.com/E3SM-Project/simboard/issues/new/choose) to report bugs or propose features.
Pull requests should include tests + documentation updates.

---

## 🪝 Pre-commit Hooks

This repository uses **[pre-commit](https://pre-commit.com/)** to enforce consistent code quality checks for both the **backend (Python)** and **frontend (TypeScript)**.

Pre-commit runs automatically on `git commit` and will block commits if checks fail.

---

### ⚠️ Important: Where to run pre-commit

**Pre-commit must always be run from the repository root.**

Some hooks (notably `mypy`) reference configuration files using paths relative to the repo root (for example, `backend/pyproject.toml`). Running pre-commit from a subdirectory such as `backend/` can cause those configurations to be missed, leading to inconsistent or misleading results.

✅ Correct:

```bash
pre-commit run --all-files
```

❌ Incorrect:

```bash
cd backend
pre-commit run --all-files
```

In CI, pre-commit is also executed from the repository root for this reason.

> **Note:** When using `uv`, CI runs pre-commit via
> `uv run --project backend pre-commit run --all-files`.
> The `--project` flag selects the backend virtual environment, but **does not change the working directory**. Pre-commit itself must still be invoked from the repo root so configuration paths resolve correctly.

---

### What pre-commit checks

- **Backend**

  - Ruff linting and formatting
  - Python style and correctness checks (mypy)

- **Frontend**

  - ESLint (auto-fix on staged files)
  - Prettier formatting (staged files only)

All hooks are configured in the root `.pre-commit-config.yaml`.

> **Note:** Git hooks run in a non-interactive shell.
> Make sure that Node.js tools (such as `pnpm`) are available in your system `PATH` so frontend hooks can execute successfully.

---

### Installing pre-commit (recommended)

Pre-commit is installed **inside the backend uv environment** and wired up via the Makefile.

After cloning the repo, run:

```bash
make install
```

This will:

- Create the backend `uv` virtual environment (if missing)
- Install Python and frontend dependencies
- Install the git pre-commit hooks

If you only want to (re)install the hooks:

```bash
make pre-commit-install
```

---

### Running pre-commit manually

To run all hooks against all files (from the repo root):

```bash
make pre-commit-run
```

Or directly:

```bash
uv run pre-commit run --all-files
```

---

### Notes & expectations

- Pre-commit uses the **existing project environments**:
  - Python hooks run via `uv`
  - Frontend hooks run via `pnpm`
- The tools themselves (`uv`, `pnpm`, `node`) are expected to already be installed on your system
- Hooks are **fast** and only run on staged files by default
- Formatting issues are usually auto-fixed; re-stage files and retry the commit if needed

---

### Skipping hooks (not recommended)

If you must bypass pre-commit temporarily:

```bash
git commit --no-verify
```

Please only do this when absolutely necessary.

---

## Local HTTPS

SimBoard uses **local HTTPS** with development certificates:

```bash
certs/dev.crt
certs/dev.key
```

Generated via:

```bash
make gen-certs
```

Used automatically by:

- FastAPI (Uvicorn SSL)
- Vite (via `VITE_SSL_CERT`, `VITE_SSL_KEY`)

---

## License

TBD
