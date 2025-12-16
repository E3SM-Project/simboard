# SimBoard

SimBoard is a platform for managing and comparing Earth system simulation metadata, with a focus on **E3SM** (Energy Exascale Earth System Model) reference simulations.

SimBoard helps researchers:

- Store and organize simulation metadata
- Browse and visualize simulation details
- Compare runs side-by-side
- Surface diagnostics and key metadata-driven insights

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Developer Quickstart (Bare-Metal)](#developer-quickstart-bare-metal)
- [Developer Quickstart (Docker)](#developer-quickstart-docker)
- [Environment Variables](#environment-variables)
- [Repository Structure](#repository-structure)
- [Development Notes](#development-notes)
- [Makefile Commands](#makefile-commands)
- [Local HTTPS / Traefik](#local-https--traefik)
- [License](#license)

---

## Prerequisites

### 1. Install **Docker Desktop**

Download: https://www.docker.com/products/docker-desktop  
Ensure it is running before using Docker commands.

---

### 2. Install **uv** (Python dependency manager)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify:

```bash
uv --version
```

---

### 3. Install **Node.js**, **npm**, and **pnpm**

Install Node.js (LTS recommended): https://nodejs.org

Verify:

```bash
node --version
npm --version
```

Install pnpm:

```bash
npm install -g pnpm
```

Verify:

```bash
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

This is the **recommended workflow for daily development**:

- Fastest reloads
- Best debugging experience
- Fastest pytest runs
- Uses your native Python/Node installations

> ⚠️ **Not production-accurate.** Do not use bare-metal configs in actual deployments.

### Commands

```bash
# 1. Enter repository
cd simboard

# 2. Setup the development environment (installs deps + copies .env files)
make setup-dev

# 3. Start backend + frontend (run in separate terminals)
make backend
make frontend

# 4. Open API and UI
open https://127.0.0.1:8000/docs
open https://127.0.0.1:5173

# 5. Optional: linting & type checks
make lint
make type-check
```

---

## Developer Quickstart (Docker)

Use this environment to validate that SimBoard works **inside containers**, similar to production:

- Matches production OS + Python runtime
- Catches Dockerfile or networking issues early
- Ideal for integration testing (frontend ↔ backend ↔ database)

Slightly slower than bare-metal—use only when you need container parity.

### Commands

```bash
# 1. Enter repository
cd simboard

# 2. Build + start Docker dev environment (automatically runs migrations & seeds DB)
make setup-dev-docker

# 3. Start backend & frontend containers (separate terminals)
make docker-up svc=backend
make docker-up svc=frontend

# 4. Open API and UI
open https://127.0.0.1:8000/docs
open https://127.0.0.1:5173

# 5. Optional checks
make lint
make type-check
```

---

## Environment Variables

Both:

- `make setup-dev`
- `make setup-dev-docker`

automatically copy all required `.env` files for you.

You **do not need to manually copy them** — simply **edit the values** as needed.

The primary customization developers must provide is the **GitHub OAuth configuration** in:

```
backend/.env
```

### Backend GitHub OAuth Variables

```env
# These come from your GitHub OAuth App (GitHub → Settings → Developer settings → OAuth Apps)
GITHUB_CLIENT_ID=your_github_oauth_app_client_id
GITHUB_CLIENT_SECRET=your_github_oauth_app_client_secret

# Must match the callback URL in your GitHub App configuration
# This is the backend OAuth callback endpoint that GitHub calls with the authorization code.
GITHUB_REDIRECT_URL=https://127.0.0.1/auth/github/callback
# For production, this must also point to the backend's OAuth callback endpoint
# GITHUB_REDIRECT_URL=https://app.${DOMAIN}/auth/callback

# Secret used to sign OAuth "state" parameter (prevents CSRF)
# Generate securely with:
#   python -c "import secrets; print(secrets.token_urlsafe(64))"
GITHUB_STATE_SECRET_KEY=superlongrandomsecretforoauthstate
```

No other environment variables typically need modification during development.

---

## Repository Structure

```bash
.
├── backend/     # FastAPI, Postgres, SQLAlchemy, Alembic, Pydantic
├── frontend/    # Vite + React + Tailwind + shadcn
└── README.md    # This file
```

Each component provides more details:

- **Backend:** [./backend/README.md](./backend/README.md)
- **Frontend:** [./frontend/README.md](./frontend/README.md)

---

## Development Notes

- Backend dependencies are managed using **uv** (`pyproject.toml`).
- Frontend dependencies use **pnpm**.
- Docker is used for both dev containers and production images.
- Ensure Docker Desktop is running before executing any Docker-based Make commands.

Use [GitHub Issues](https://github.com/E3SM-Project/simboard/issues/new/choose) for reporting bugs and proposing features.

Contributions should include tests and documentation updates.

---

## Makefile Commands

SimBoard includes a **top-level Makefile** that orchestrates:

- Backend commands (proxied into `backend/Makefile`)
- Frontend commands (proxied into `frontend/Makefile`)
- Docker orchestration
- Developer utilities (linting, formatting, type checking)

View all available commands:

```bash
make help
```

---

## Local HTTPS / Traefik

SimBoard uses **Traefik** to provide:

- Simple local HTTPS
- Reverse proxy routing between services
- Automatic certificate handling
- Production-like request flow during local development

Traefik is automatically configured when using:

```bash
make setup-dev-docker
```

---

## License

TBD
