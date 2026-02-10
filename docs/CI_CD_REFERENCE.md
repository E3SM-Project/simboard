# CI/CD Workflows Quick Reference

This document provides a quick reference for the automated CI/CD workflows in the SimBoard repository.

---

## Workflow Overview

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| **Backend CI** | `backend-ci.yml` | PR/Push to `main` | Linting, tests, validation |
| **Build Backend (Dev)** | `build-backend-dev.yml` | Push to `main` | Build & push dev backend image |
| **Build Frontend (Dev)** | `build-frontend-dev.yml` | Push to `main` | Build & push dev frontend image |
| **Build Backend (Prod)** | `build-backend-prod.yml` | Release/Tag | Build & push prod backend image |
| **Build Frontend (Prod)** | `build-frontend-prod.yml` | Release/Tag | Build & push prod frontend image |

---

## Workflow Details

### Backend CI (`backend-ci.yml`)

**Purpose:** Run quality checks and tests on backend code

**Triggers:**
- Pull requests to `main` (when `backend/**` changes)
- Push to `main` (when `backend/**` changes)
- Manual dispatch

**What it does:**
- Runs pre-commit hooks (linting, formatting)
- Executes pytest test suite
- Validates migrations

**Time:** ~5-10 minutes

**Status required for merge:** ✅ Yes

---

### Build Backend (Dev) (`build-backend-dev.yml`)

**Purpose:** Build development backend container image

**Triggers:**
- Push to `main` (when `backend/**` changes)
- Manual dispatch

**What it does:**
- Builds multi-arch Docker image (amd64, arm64)
- Tags with `:dev` and `:sha-<commit>`
- Pushes to NERSC registry

**Registry:** `registry.nersc.gov/e3sm/simboard/backend`

**Tags produced:**
- `backend:dev` (latest dev)
- `backend:sha-a1b2c3d` (specific commit)

**Time:** ~10-15 minutes

**Deployment:** NERSC Spin dev namespace

---

### Build Frontend (Dev) (`build-frontend-dev.yml`)

**Purpose:** Build development frontend container image

**Triggers:**
- Push to `main` (when `frontend/**` changes)
- Manual dispatch (with optional API URL override)

**What it does:**
- Builds multi-arch Docker image (amd64, arm64)
- Injects development API URL at build time
- Tags with `:dev` and `:sha-<commit>`
- Pushes to NERSC registry

**Registry:** `registry.nersc.gov/e3sm/simboard/frontend`

**Tags produced:**
- `frontend:dev` (latest dev)
- `frontend:sha-a1b2c3d` (specific commit)

**Build args:**
- `VITE_API_BASE_URL`: `https://simboard-dev-api.e3sm.org` (default)
- `NODE_ENV`: `production`

**Time:** ~10-15 minutes

**Deployment:** NERSC Spin dev namespace

---

### Build Backend (Prod) (`build-backend-prod.yml`)

**Purpose:** Build production backend container image

**Triggers:**
- GitHub Release published
- Push of version tag (e.g., `v0.3.0`)
- Manual dispatch

**What it does:**
- Builds multi-arch Docker image (amd64, arm64)
- Tags with semantic versions
- Pushes to NERSC registry

**Registry:** `registry.nersc.gov/e3sm/simboard/backend`

**Tags produced (for v0.3.0):**
- `backend:v0.3.0` (full version - immutable)
- `backend:v0.3` (minor version)
- `backend:v0` (major version)
- `backend:latest` (latest prod)

**Time:** ~10-15 minutes

**Deployment:** NERSC Spin prod namespace

---

### Build Frontend (Prod) (`build-frontend-prod.yml`)

**Purpose:** Build production frontend container image

**Triggers:**
- GitHub Release published
- Push of version tag (e.g., `v0.3.0`)
- Manual dispatch (with optional API URL override)

**What it does:**
- Builds multi-arch Docker image (amd64, arm64)
- Injects production API URL at build time
- Tags with semantic versions
- Pushes to NERSC registry

**Registry:** `registry.nersc.gov/e3sm/simboard/frontend`

**Tags produced (for v0.3.0):**
- `frontend:v0.3.0` (full version - immutable)
- `frontend:v0.3` (minor version)
- `frontend:v0` (major version)
- `frontend:latest` (latest prod)

**Build args:**
- `VITE_API_BASE_URL`: `https://simboard-api.e3sm.org` (default)
- `NODE_ENV`: `production`

**Time:** ~10-15 minutes

**Deployment:** NERSC Spin prod namespace

---

## Triggering Workflows

### Automatic Triggers

| Action | Workflows Triggered |
|--------|-------------------|
| Push to `main` (backend changes) | Backend CI, Build Backend (Dev) |
| Create PR to `main` | Backend CI (if backend changes) |
| Publish GitHub Release | Build Backend (Prod), Build Frontend (Prod) |
| Push version tag (`v*.*.*`) | Build Backend (Prod), Build Frontend (Prod) |

### Manual Triggers

All workflows support **manual dispatch** via the GitHub UI:

1. Go to **Actions** tab
2. Select the workflow
3. Click **Run workflow**
4. Select branch (usually `main` for dev, tag for prod)
5. Click **Run workflow**

---

## Monitoring Workflows

### View Running Workflows

1. Navigate to **Actions** tab
2. See list of recent workflow runs
3. Click on a run to view detailed logs

### Check Workflow Status

**Status badges** can be added to README.md:

```markdown
![Backend CI](https://github.com/E3SM-Project/simboard/actions/workflows/backend-ci.yml/badge.svg)
![Build Backend (Dev)](https://github.com/E3SM-Project/simboard/actions/workflows/build-backend-dev.yml/badge.svg)
```

### Notifications

Configure GitHub notifications:
- **Settings** → **Notifications**
- Enable/disable workflow run notifications

---

## Common Operations

### Release a New Version

```bash
# 1. Ensure main is up to date
git checkout main
git pull origin main

# 2. Run tests locally
make backend-test
make frontend-lint

# 3. Create and push tag
git tag v0.3.0
git push origin v0.3.0

# 4. Create GitHub Release (triggers workflows)
# - Go to https://github.com/E3SM-Project/simboard/releases/new
# - Select tag v0.3.0
# - Write release notes
# - Publish release
```

### Rebuild Development Backend

```bash
# Option 1: Make a change and push
git commit --allow-empty -m "Trigger dev backend rebuild"
git push origin main

# Option 2: Manual dispatch via GitHub UI
# - Go to Actions → Build Backend (Dev)
# - Click "Run workflow"
```

### Check Image in Registry

```bash
# Login
docker login registry.nersc.gov

# Pull and inspect
docker pull registry.nersc.gov/e3sm/simboard/backend:dev
docker inspect registry.nersc.gov/e3sm/simboard/backend:dev
```

---

## Workflow Permissions

### Required GitHub Secrets

- `NERSC_REGISTRY_USERNAME`: NERSC registry username
- `NERSC_REGISTRY_PASSWORD`: NERSC registry password/token

**Setup:** See [docs/GITHUB_SECRETS.md](GITHUB_SECRETS.md)

### Repository Permissions

Workflows require:
- `contents: read` - Read repository contents
- Push access to NERSC registry (via secrets)

---

## Troubleshooting

### Workflow Fails to Start

**Check:**
- Workflow file syntax (YAML validation)
- Trigger conditions match your action
- Required secrets are configured

### Build Fails

**Check:**
- Dockerfile syntax and build args
- Dependencies are available
- Previous builds succeeded (for cache)

### Authentication Fails

**Check:**
- GitHub Secrets are configured correctly
- NERSC credentials are valid
- Repository has push access to registry namespace

**Solutions:** See [docs/GITHUB_SECRETS.md](GITHUB_SECRETS.md) troubleshooting

### Image Not Available in Registry

**Check:**
- Workflow completed successfully
- Correct image name and tag
- Registry permissions

**Verify:**
```bash
docker login registry.nersc.gov
docker pull registry.nersc.gov/e3sm/simboard/backend:dev
```

---

## Additional Resources

- [Full Deployment Guide](DEPLOYMENT.md)
- [GitHub Secrets Configuration](GITHUB_SECRETS.md)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [NERSC Registry Documentation](https://docs.nersc.gov/development/containers/registry/)

---

## Support

For workflow issues:
1. Check workflow logs in GitHub Actions
2. See troubleshooting sections in this doc
3. Consult [docs/DEPLOYMENT.md](DEPLOYMENT.md)
4. Open an issue: [GitHub Issues](https://github.com/E3SM-Project/simboard/issues)
