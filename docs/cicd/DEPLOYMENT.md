# Deployment Guide

Complete reference for CI/CD pipelines and NERSC Spin deployments.

## Table of Contents

- [Overview](#overview)
- [Environment Architecture](#environment-architecture)
- [CI/CD Workflows](#cicd-workflows)
- [GitHub Secrets Setup](#github-secrets-setup)
- [Image Tagging Strategy](#image-tagging-strategy)
- [Development Deployment](#development-deployment)
- [Production Release Process](#production-release-process)
- [Database Migrations](#database-migrations)
- [Network and Firewall Requirements](#network-and-firewall-requirements)
- [Rollback Procedure](#rollback-procedure)
- [Manual Builds](#manual-builds)
- [Troubleshooting](#troubleshooting)

## Overview

SimBoard uses **GitHub Actions** to automatically build and publish container images to the **NERSC container registry** (`registry.nersc.gov/e3sm/simboard/`).

**Key Features:**

- ✅ Automated dev builds from `main` branch
- ✅ Component-level production releases via GitHub Releases
- ✅ Independent frontend and backend versioning
- ✅ linux/amd64 architecture support
- ✅ Semantic versioning for production
- ✅ Docker Buildx with layer caching
- ✅ Separation via image tags and K8s namespaces

## Environment Architecture

### Development

| Component | Hosting          | Image          | Pull Policy |
| --------- | ---------------- | -------------- | ----------- |
| Backend   | NERSC Spin (dev) | `backend:dev`  | Always      |
| Frontend  | NERSC Spin (dev) | `frontend:dev` | Always      |

**Trigger:** Automatic on push to `main`

### Production

| Component | Hosting           | Image            | Pull Policy  |
| --------- | ----------------- | ---------------- | ------------ |
| Backend   | NERSC Spin (prod) | `backend:1.0.0`  | IfNotPresent |
| Frontend  | NERSC Spin (prod) | `frontend:2.1.0` | IfNotPresent |

**Trigger:** Component-scoped GitHub Release tag (e.g., `backend-v1.0.0`, `frontend-v2.1.0`)

> **Note:** Frontend and backend are versioned independently. Each component can be released on its own schedule without affecting the other.

## CI/CD Workflows

### Dev Builds (push to `main`)

Dev workflows build and push images tagged with `:dev` and `:sha-<commit>` whenever changes are pushed to `main`. These do **not** affect production images.

#### Backend Dev (`build-backend-dev.yml`)

**Triggers:** Push to `main` (backend changes) or manual dispatch

**Tags:** `:dev`, `:sha-<commit>`

**Registry:** `registry.nersc.gov/e3sm/simboard/backend`

#### Frontend Dev (`build-frontend-dev.yml`)

**Triggers:** Push to `main` (frontend changes) or manual dispatch

**Tags:** `:dev`, `:sha-<commit>`

**Build args:**

- `VITE_API_BASE_URL`: `https://simboard-dev-api.e3sm.org` (default)

**Registry:** `registry.nersc.gov/e3sm/simboard/frontend`

### Release Builds (component-scoped tags)

Release workflows are triggered by component-scoped Git tags created through GitHub Releases. Each component has its own workflow and tag namespace. Release builds do **not** modify the `:dev` image.

#### Backend Prod (`build-backend-prod.yml`)

**Triggers:** Tag push matching `backend-v*`

**Tags:** `:X.Y.Z`, `:sha-<commit>`, `:latest`

**Registry:** `registry.nersc.gov/e3sm/simboard/backend`

#### Frontend Prod (`build-frontend-prod.yml`)

**Triggers:** Tag push matching `frontend-v*`

**Tags:** `:X.Y.Z`, `:sha-<commit>`, `:latest`

**Build args:**

- `VITE_API_BASE_URL`: `https://simboard-api.e3sm.org` (default, override in manual dispatch)

**Registry:** `registry.nersc.gov/e3sm/simboard/frontend`

### Build Flow Summary

```
Dev builds:     push to main     → :dev, :sha-<short>
Release builds: component tag    → :X.Y.Z, :sha-<short>, :latest
```

## GitHub Secrets Setup

**Required secrets:** Configure in [repository settings](https://github.com/E3SM-Project/simboard/settings/secrets/actions)

1. **NERSC_REGISTRY_USERNAME**
   - Your NERSC username
   - Used for `docker login registry.nersc.gov`

2. **NERSC_REGISTRY_PASSWORD**
   - Your NERSC password or access token
   - Used for `docker login registry.nersc.gov`

**Test locally:**

```bash
docker login registry.nersc.gov
# Use the same credentials
```

**Security:**

- Use service account tokens when available
- Rotate credentials every 90 days
- Never commit credentials to source code

## Image Tagging Strategy

### Development Images

| Tag            | Description        | Use Case               |
| -------------- | ------------------ | ---------------------- |
| `:dev`         | Latest from `main` | Primary dev deployment |
| `:sha-a1b2c3d` | Specific commit    | Debugging, rollback    |

### Production Images

| Tag       | Description    | Use Case                 |
| --------- | -------------- | ------------------------ |
| `:1.2.0`  | Full version   | Production (recommended) |
| `:latest` | Latest release | Reference only           |

**Best practice:** Use full semantic versions (`:X.Y.Z`) in production for reproducibility.

### Tag Convention

| Git Tag           | Component | Docker Image Tag                                  |
| ----------------- | --------- | ------------------------------------------------- |
| `backend-v1.0.0`  | Backend   | `registry.nersc.gov/e3sm/simboard/backend:1.0.0`  |
| `frontend-v2.1.0` | Frontend  | `registry.nersc.gov/e3sm/simboard/frontend:2.1.0` |

## Development Deployment

### Update Dev Environment

Development images are automatically built and pushed when you push to `main`. To deploy the updated images on NERSC Spin, use the [Rancher UI](https://rancher2.spin.nersc.gov/dashboard/home):

1. Navigate to **Workloads → Deployments** in the dev namespace
2. Find the backend or frontend deployment
3. Click **⋮ → Redeploy** to pull the latest `:dev` image
4. Verify pods restart successfully in the **Pods** tab

### Image Configuration

When creating or editing a workload in Rancher, set these values:

**Dev backend:**

- **Image:** `registry.nersc.gov/e3sm/simboard/backend:dev`
- **Pull Policy:** Always

**Dev frontend:**

- **Image:** `registry.nersc.gov/e3sm/simboard/frontend:dev`
- **Pull Policy:** Always

## Production Release Process

Frontend and backend are released independently using component-scoped tags. Creating a GitHub Release with the appropriate tag triggers the corresponding CI workflow.

### Step 1: Prepare Release

```bash
# Ensure main is up to date
git checkout main && git pull

# Run tests
make backend-test
make frontend-lint
```

### Step 2a: Create GitHub Release (Frontend)

1. Navigate to [Releases](https://github.com/E3SM-Project/simboard/releases/new)
2. Click **Draft a new release**
3. In **Choose a tag**, enter a new tag following the convention:
   ```
   frontend-v1.2.0
   ```
4. Ensure the **Target** branch is `main`
5. Set the release title (e.g., `Frontend v1.2.0`)
6. Add release notes summarizing the changes
7. Click **Publish release**

Publishing the release creates the Git tag, which:

- Triggers the `frontend-v*` workflow (`build-frontend-prod.yml`)
- Builds the Docker image
- Pushes versioned tags (`:1.2.0`, `:sha-<short>`, `:latest`) to the registry
- Does **not** modify the `:dev` image

### Step 2b: Create GitHub Release (Backend)

Follow the same steps as above, but use a backend-scoped tag:

```
backend-v1.0.0
```

This triggers `build-backend-prod.yml` and pushes backend-specific versioned tags.

### Step 3: Monitor Builds

Check the [Actions tab](https://github.com/E3SM-Project/simboard/actions) — only the workflow matching the component tag will trigger. Build typically completes in ~10-15 minutes.

### Step 4: Deploy to Production

Update the image tags in the [Rancher UI](https://rancher2.spin.nersc.gov/dashboard/home):

1. Navigate to **Workloads → Deployments** in the prod namespace
2. Click the target deployment → **⋮ → Edit Config**
3. Update the **Image** field to the new versioned image, e.g.:
   - Backend: `registry.nersc.gov/e3sm/simboard/backend:1.0.0`
   - Frontend: `registry.nersc.gov/e3sm/simboard/frontend:1.2.0`
4. Set **Pull Policy** to `IfNotPresent`
5. Click **Save** — Rancher will roll out the new version

### Step 5: Verify Production

1. In Rancher, check that pods are **Running** under **Workloads → Pods** in the prod namespace
2. Review pod logs via the **⋮ → View Logs** action in Rancher
3. Test endpoints:
   - `https://simboard-api.e3sm.org/api/v1/health`
   - `https://simboard.e3sm.org/health`

## Database Migrations

### Strategy Overview

Database migrations are decoupled from application startup to support
multi-replica and rolling deployments. The recommended deployment flow
is:

```
build image → run migration Job → deploy/scale application
```

Migrations are executed via a **dedicated Kubernetes Job** in Rancher
that runs `alembic upgrade head` exactly once, before the application
Deployment is updated or scaled.

### How It Works

The backend image ships two entrypoints:

| Script           | Purpose                            |
| ---------------- | ---------------------------------- |
| `entrypoint.sh`  | Application startup (Uvicorn)      |
| `migrate.sh`     | Standalone Alembic migration runner |

Migrations are **not** run during application startup.
`entrypoint.sh` only waits for the database to be reachable and then
starts Uvicorn. All schema changes are applied via `migrate.sh`,
either as a Kubernetes Job or manually.

### Production Deployment Flow

1. **Build** — CI pushes a new image to the registry.
2. **Migrate** — Create a one-off Kubernetes Job in Rancher that runs
   `migrate.sh` against the production database.
3. **Deploy** — Update the Deployment image tag; pods start without
   running migrations.
4. **Verify** — Confirm pods are healthy and the migration Job
   completed successfully.

#### Step 2 Detail: Running a Migration Job in Rancher

1. Open the [Rancher UI](https://rancher2.spin.nersc.gov/dashboard/home)
2. Navigate to **Workloads → Jobs** in the prod namespace
3. Click **Create** and configure:

   | Field               | Value |
   | ------------------- | ----- |
   | **Name**            | `simboard-migrate-<version>` (e.g., `simboard-migrate-1-1-0`) |
   | **Image**           | `registry.nersc.gov/e3sm/simboard/backend:<version>` |
   | **Command**          | `/app/migrate.sh` |
   | **Environment**     | `DATABASE_URL` — same value used by the backend Deployment |
   | **Restart Policy**  | `Never` |
   | **Completions**     | `1` |
   | **Back Off Limit**  | `1` |

4. Click **Create** and monitor the Job logs in Rancher
5. Once the Job shows **Succeeded**, proceed with the Deployment
   update

### Startup Sequence (entrypoint.sh)

1. **Database readiness check** — waits up to 30 seconds for
   PostgreSQL to accept connections via `pg_isready`.
2. **Application start** — Uvicorn launches only after the database
   is reachable.

If the database readiness check fails, the container exits immediately
and does **not** start the application.

### migrate.sh Reference

The `migrate.sh` script provides a standalone migration runner:

```bash
# Apply all pending migrations (default)
./migrate.sh

# Show current migration revision
./migrate.sh current

# Show migration history
./migrate.sh history

# Downgrade by one revision
./migrate.sh downgrade -1
```

The script waits for database readiness before executing any Alembic
command and exits with a non-zero status on failure.

### Scaling Constraints

Migrations are fully decoupled from application startup. The backend
Deployment can be scaled to any number of replicas without risk of
concurrent migration execution.

Always run the migration Job **before** deploying a new image version
that includes schema changes.

### Migration Rollback

If a migration must be reverted:

1. Create a new Job in Rancher with the **previous** backend image
   version.
2. Set the command to `/app/migrate.sh downgrade -1` (or the
   appropriate Alembic target revision).
3. Monitor the Job until it completes.
4. Roll back the backend Deployment to the previous image tag.

> **Note:** Downgrade migrations must be implemented in the Alembic
> revision files. Always verify that downgrade paths exist before
> relying on them.

## Network and Firewall Requirements

### Database Connectivity from Spin

Backend pods and migration Jobs running in NERSC Spin connect to
PostgreSQL using the `DATABASE_URL` environment variable.

| Setting            | Value                              |
| ------------------ | ---------------------------------- |
| **Host**           | Configured via `DATABASE_URL`      |
| **Port**           | `5432` (default PostgreSQL port)   |
| **Protocol**       | TCP                                |
| **Authentication** | Username/password in `DATABASE_URL`|

### Firewall / Network Policy

- The PostgreSQL instance must allow inbound connections from the Spin
  namespace where SimBoard runs.
- If the database is hosted outside Spin (e.g., on a NERSC-managed
  database service), a firewall rule or network policy must permit
  traffic from the Spin pod CIDR to the database host on port 5432.
- Migration Jobs run in the **same namespace** as the backend
  Deployment. No additional service account or network policy is
  required beyond what the Deployment already uses.
- If the database is deployed as a Spin workload in the same
  namespace, connectivity works via the Kubernetes service name
  (e.g., `db:5432`) without additional firewall rules.

### Verifying Connectivity

From a running pod or Job in Rancher, use the container shell
(**⋮ → Execute Shell**):

```bash
pg_isready -d "$DATABASE_URL"
```

If this fails, verify:

1. The `DATABASE_URL` is correct (host, port, credentials)
2. Firewall rules allow traffic from the Spin namespace
3. The PostgreSQL service is running and healthy

## Rollback Procedure

Version-tagged images are **immutable** — once published, a version tag (e.g., `:1.0.0`) always refers to the same image. This makes rollbacks safe and predictable.

### Rolling Back via Rancher

1. Open the [Rancher UI](https://rancher2.spin.nersc.gov/dashboard/home)
2. Navigate to **Workloads → Deployments** in the prod namespace
3. Click the deployment to roll back → **⋮ → Edit Config**
4. Change the **Image** tag to the previous known-good version, e.g.:
   - `registry.nersc.gov/e3sm/simboard/backend:0.9.0`
   - `registry.nersc.gov/e3sm/simboard/frontend:1.1.0`
5. Click **Save** to trigger the rollout

Alternatively, use the built-in Rancher rollback:

1. Navigate to the deployment → **⋮ → Rollback**
2. Select the previous revision and confirm

### Key Rollback Principles

- **Version tags are immutable:** `:1.0.0` always points to the same image digest. You can safely redeploy any previously released version.
- **Components are independent:** Rolling back the frontend does not require rolling back the backend, and vice versa.
- **`:dev` is unaffected:** Release rollbacks have no impact on the dev environment.
- **Use commit-based tags for precision:** If you need to deploy a specific build, use the `:sha-<short>` tag from the GitHub Actions build log.

## Manual Builds

For testing or emergency builds:

```bash
# Login
docker login registry.nersc.gov

# Backend
cd backend
docker buildx build \
  --platform=linux/amd64,linux/arm64 \
  --build-arg ENV=production \
  -t registry.nersc.gov/e3sm/simboard/backend:manual \
  --push \
  .

# Frontend
cd frontend
docker buildx build \
  --platform=linux/amd64,linux/arm64 \
  --build-arg VITE_API_BASE_URL=https://simboard-api.e3sm.org \
  -t registry.nersc.gov/e3sm/simboard/frontend:manual \
  --push \
  .
```

## Troubleshooting

### Authentication Failures

**Issue:** `denied: requested access to the resource is denied`

**Solutions:**

1. Verify GitHub Secrets are configured
2. Test credentials: `docker login registry.nersc.gov`
3. Check NERSC account has push permissions to `e3sm/simboard/` namespace

### Build Failures

**Issue:** Workflow fails during build

**Solutions:**

1. Check workflow logs in Actions tab
2. Test Dockerfile locally:
   ```bash
   cd backend && docker build .
   cd frontend && docker build --build-arg VITE_API_BASE_URL=https://example.com .
   ```
3. Verify all dependencies are pinned

### Dev Image Not Updating

**Issue:** NERSC Spin not pulling latest `:dev`

**Solutions:**

1. Verify image was built (check GitHub Actions)
2. In [Rancher](https://rancher2.spin.nersc.gov/dashboard/home), redeploy the workload: **Workloads → Deployments → ⋮ → Redeploy**
3. Check that **Pull Policy** is set to `Always` for `:dev` tags

### Wrong API URL in Frontend

**Issue:** Frontend connecting to wrong backend

**Solutions:**

1. Check `VITE_API_BASE_URL` in workflow file
2. Rebuild with manual dispatch and correct URL
3. Verify environment-specific URLs:
   - Dev: `https://simboard-dev-api.e3sm.org`
   - Prod: `https://simboard-api.e3sm.org`

### Workflow Not Triggering

**Issue:** Push to main doesn't trigger build

**Solutions:**

1. Verify changes are in watched paths:
   - Backend: `backend/**`
   - Frontend: `frontend/**`
2. Check workflow files exist and are on `main` branch
3. Verify Actions are enabled in repository settings

**Issue:** Release tag doesn't trigger prod build

**Solutions:**

1. Verify the tag follows the component convention:
   - Backend: `backend-vX.Y.Z` (e.g., `backend-v1.0.0`)
   - Frontend: `frontend-vX.Y.Z` (e.g., `frontend-v1.2.0`)
2. Ensure the tag was created via a published GitHub Release (draft releases do not create tags)
3. Check the [Actions tab](https://github.com/E3SM-Project/simboard/actions) for the corresponding workflow

## Additional Resources

- [NERSC Container Registry Docs](https://docs.nersc.gov/development/containers/registry/)
- [NERSC Spin Docs](https://docs.nersc.gov/services/spin/)
- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Docker Buildx Docs](https://docs.docker.com/buildx/working-with-buildx/)
- [Semantic Versioning](https://semver.org/)

## Support

- **GitHub Issues:** [Open an issue](https://github.com/E3SM-Project/simboard/issues)
- **Workflow Logs:** [Actions tab](https://github.com/E3SM-Project/simboard/actions)
