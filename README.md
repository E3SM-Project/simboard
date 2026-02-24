# SimBoard

SimBoard is a platform for managing and comparing Earth system simulation metadata, with a focus on **E3SM** (Energy Exascale Earth System Model) reference simulations.

SimBoard helps researchers:

- Store and organize simulation metadata
- Browse and visualize simulation details
- Compare runs side-by-side
- Surface diagnostics and metadata-driven insights

AI-assisted capabilities are being explored to supplement these features, including automated metadata summarization, simulation comparison analysis, and intelligent discovery of patterns across runs.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Developer Quickstart](#developer-quickstart)
   - [1. Commands](#1-commands)
   - [2. Setup GitHub OAuth Authentication](#2-setup-github-oauth-authentication)
   - [3. Local HTTPS](#3-local-https)

3. [Repository Structure](#repository-structure)
4. [Development Notes](#development-notes)
   - [Pre-commit Hooks](#pre-commit-hooks)

5. [Staging and Production Environments](#staging-and-production-environments)
   - [Building and Deploying Docker Containers for NERSC Spin (Manual)](#building-and-deploying-docker-containers-for-nersc-spin-manual)
   - [Provisioning a Service Account for HPC (NERSC Spin)](#provisioning-a-service-account-for-hpc-nersc-spin)
   - [Helpful Docker Commands](#helpful-docker-commands)

6. [License](#license)

---

## Prerequisites

1. **Install Docker Desktop**
   - Download and install: [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
   - Ensure Docker Desktop is running before using any Docker-based commands.

2. **Install uv (Python dependency manager)**
   - macOS/Linux:

     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```

   - Windows:

     ```bash
     powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```

   - Verify installation:

     ```bash
     uv --version
     ```

3. **Install Node.js, npm, and pnpm**
   - Install Node.js (LTS recommended): [https://nodejs.org](https://nodejs.org)
   - Verify Node and npm:

     ```bash
     node --version
     npm --version
     ```

   - Install pnpm:

     ```bash
     npm install -g pnpm
     pnpm --version
     ```

4. **Clone the repository**

   ```bash
   git clone https://github.com/E3SM-Project/simboard.git
   cd simboard
   ```

## Developer Quickstart

> ⚠️ This is a bare-metal development environment and is _not production-accurate_ — it is optimized for speed.

This is the **recommended daily workflow**:

- Fastest hot reloads
- Best debugging experience
- No Docker overhead

### 1. Commands

```bash
cd simboard

# 1. Setup development assets (env files + certs + DB + deps)
make setup-local

# 2. (First time only) Create an admin account
make backend-create-admin email=admin@example.com password=yourpassword
# or, if interactive:
# make backend-create-admin

# 3. Start backend (terminal 1)
make backend-run

# 4. Start frontend (terminal 2)
make frontend-run

# 5. Open API and UI
open https://127.0.0.1:8000/docs
open https://127.0.0.1:5173
```

### 2. Setup GitHub OAuth Authentication

#### 1. Create a GitHub OAuth App

1. Go to: https://github.com/settings/developers
2. Click **“New OAuth App”**.
3. Fill in:
   - **Application name:** SimBoard (local)
   - **Homepage URL:** https://127.0.0.1:5173
   - **Authorization callback URL:**

     ```bash
     https://127.0.0.1:8000/api/v1/auth/github/callback
     ```

4. Click **Register application**.
5. Copy the generated:
   - **Client ID**
   - **Client Secret**

#### 2. Configure local environment variables

Add the credentials to:

```bash
.envs/local/backend.env
```

Example:

```env
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret

# Must match GitHub OAuth callback URL exactly
GITHUB_REDIRECT_URL=https://127.0.0.1:8000/auth/github/callback

# Generate securely:
# python -c "import secrets; print(secrets.token_urlsafe(64))"
GITHUB_STATE_SECRET_KEY=your_secret
```

Restart the backend after updating environment variables.

#### 3. Local HTTPS

For local development, SimBoard uses **local HTTPS** with development certificates:

```bash
certs/local.crt
certs/local.key
```

These files are generated automatically with `make install`. To re-generate, run:

```bash
make gen-certs
```

Used automatically by:

- FastAPI (Uvicorn SSL)
- Vite (via `VITE_SSL_CERT`, `VITE_SSL_KEY`)

## Development Notes

- Backend dependencies managed using **uv**
- Frontend dependencies managed using **pnpm**

Use [GitHub Issues](https://github.com/E3SM-Project/simboard/issues/new/choose) to report bugs or propose features.
Pull requests should include tests + documentation updates.

### Repository Structure

```bash
simboard/
├── backend/        # FastAPI, SQLAlchemy, Alembic, OAuth, metadata ingestion
├── frontend/       # Vite + React + Tailwind + shadcn
├── .envs/          # Env configs: example/ (templates, committed) + local/ (developer values, ignored)
├── docker-compose.local.yml
├── docker-compose.yml
├── Makefile        # unified monorepo automation
└── certs/          # dev HTTPS certificates
```

### Pre-commit Hooks

This repository uses **pre-commit** to enforce consistent checks for both the backend (Python) and frontend (TypeScript).

Pre-commit runs automatically on `git commit` and will block commits if checks fail.

#### 1. Where to Run It

Always run pre-commit from the **repository root**.

Some hooks (e.g., `mypy`) rely on config paths like `backend/pyproject.toml`. Running from a subdirectory can cause incorrect or inconsistent results.

✅ Correct:

```bash
pre-commit run --all-files
```

❌ Incorrect:

```bash
cd backend
pre-commit run --all-files
```

CI also runs pre-commit from the repo root.

#### 2. What It Checks

**Backend**

- Ruff (lint + format)
- mypy (type checking)

**Frontend**

- ESLint
- Prettier

All hooks are configured in the root `.pre-commit-config.yaml`.

#### 3. Installation

After cloning:

```bash
make install
```

This will:

- Create the backend `uv` environment (if missing)
- Install dependencies
- Install git hooks

To reinstall hooks only:

```bash
make pre-commit-install
```

#### 4. Run Manually

```bash
make pre-commit-run
```

Or:

```bash
uv run pre-commit run --all-files
```

#### 5. Notes

- Python hooks run via `uv`
- Frontend hooks run via `pnpm`
- Required tools (`uv`, `pnpm`, `node`) must be available in your system `PATH`
- Hooks auto-fix most formatting issues; re-stage files and re-commit if needed

#### 5. Skipping Hooks (Not Recommended)

```bash
git commit --no-verify
```

Use only when absolutely necessary.

## Staging and Production Environments

### Building and Deploying Docker Containers for NERSC Spin (Manual)

Links:

- **Harbor Registry:** <https://registry.nersc.gov/harbor/projects>
- **Rancher Dashboard:** <https://rancher2.spin.nersc.gov/dashboard/c/c-fwj56/explorer/apps.deployment>

To build and push multi-architecture Docker images for deployment on NERSC Spin, run the
following commands from the repository root.

**Login to registry.nersc.gov using your NERSC credentials:**

```bash
# Source: https://docs.nersc.gov/development/containers/registry/
docker login registry.nersc.gov
```

**Backend:**

```bash
cd backend
docker buildx build \
  --platform=linux/amd64,linux/arm64 \
  -t registry.nersc.gov/e3sm/simboard/backend . \
  --push
```

**Frontend:**

```bash
cd frontend
docker buildx build \
  --platform=linux/amd64,linux/arm64 \
  --build-arg VITE_API_BASE_URL=https://simboard-dev-api.e3sm.org \
  -t registry.nersc.gov/e3sm/simboard/frontend . \
  --push
```

Note, automation of this process is being explored using GitHub Actions CI/CD.

### Provisioning a Service Account for HPC (NERSC Spin)

Service accounts are required when non-interactive systems (e.g., HPC ingestion jobs or automation) need to authenticate to the SimBoard API.

#### Steps

1. Ensure the backend is deployed and reachable (e.g., `https://simboard-dev-api.e3sm.org`).
2. Run the provisioning script from your local machine:

   ```bash
   cd backend

   uv run python -m app.scripts.users.provision_service_account \
     --service-name perlmutter-ingestion \
     --base-url https://simboard-dev-api.e3sm.org \
     --admin-email admin@simboard.org \
     --expires-in-days 365
   ```

3. Enter the admin password when prompted.
4. Copy the generated API token and store it securely (e.g., Kubernetes Secret).

#### Store as Kubernetes Secret

```bash
kubectl -n <namespace> create secret generic simboard-perlmutter-ingestion \
  --from-literal=api_token='<TOKEN>'
```

Use this secret in your HPC job or service configuration.

```bash
> The token is shown only once. Store it securely and rotate as needed.
```

#### Example: Ingest Using Service Account Token

Export the token:

```bash
export SIMBOARD_API_TOKEN=<TOKEN>
```

Submit an ingestion request:

```bash
curl -X POST https://simboard-dev-api.e3sm.org/api/v1/ingestions/from-path \
  -H "Authorization: Bearer $SIMBOARD_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "archive_path": "/global/cfs/cdirs/e3sm/simulations/archive.tar.gz",
        "machine_name": "perlmutter",
        "hpc_username": "<your_hpc_username>"
      }'
```

Python example:

```python
import requests

API_BASE = "https://simboard-dev-api.e3sm.org/api/v1"
TOKEN = "<TOKEN>"

resp = requests.post(
  f"{API_BASE}/ingestions/from-path",
  json={
    "archive_path": "/global/cfs/cdirs/e3sm/simulations/archive.tar.gz",
    "machine_name": "perlmutter",
    "hpc_username": "<your_hpc_username>"
  },
  headers={"Authorization": f"Bearer {TOKEN}"},
)

print(resp.json())
```

### Helpful Docker Commands

```bash
docker container ls      # List running containers
docker image ls          # List local images
docker tag <src> <dest>  # Tag an image
```

---

## License

TBD
