# Deployment Guide

This document describes the CI/CD pipeline for building and deploying SimBoard containers to NERSC Spin.

> **🚀 New to CI/CD setup?** Start with the [Quick Start Guide](QUICKSTART.md) for step-by-step instructions.

---

## Table of Contents

- [Overview](#overview)
- [Environment Architecture](#environment-architecture)
- [Container Registry](#container-registry)
- [CI/CD Workflows](#cicd-workflows)
- [Image Naming and Tagging](#image-naming-and-tagging)
- [GitHub Secrets Configuration](#github-secrets-configuration)
- [Development Deployment](#development-deployment)
- [Production Release Process](#production-release-process)
- [Manual Builds (Local)](#manual-builds-local)
- [Troubleshooting](#troubleshooting)

---

## Overview

SimBoard uses **GitHub Actions** to automatically build and publish container images to the **NERSC container registry** (`registry.nersc.gov`). The pipeline enforces a clear separation between development and production environments.

### Key Principles

- ✅ **Development builds** are triggered automatically on every push to `main`
- ✅ **Production builds** are triggered only on GitHub Releases or version tags
- ✅ Development and production environments are separated by **image tags** and **Kubernetes namespaces**
- ✅ All images are multi-architecture (linux/amd64, linux/arm64)
- ✅ Production deployments are **immutable**, **traceable**, and **explicitly promoted**

---

## Environment Architecture

### Development Environment

| Component | Hosting | Image Source | Namespace |
|-----------|---------|--------------|-----------|
| **Frontend** | NERSC Spin | `main` branch → `:dev` tag | `dev` |
| **Backend** | NERSC Spin | `main` branch → `:dev` tag | `dev` |

**Purpose:** Rapid iteration and testing. Both dev frontend and backend run on NERSC Spin with automatic builds from `main`.

**Note:** A Vercel-hosted dev frontend is also available for rapid UX prototyping, but the primary dev frontend deployment is on NERSC Spin.

### Production Environment

| Component | Hosting | Image Source | Namespace |
|-----------|---------|--------------|-----------|
| **Frontend** | NERSC Spin | GitHub Release → `:vX.Y.Z` | `prod` |
| **Backend** | NERSC Spin | GitHub Release → `:vX.Y.Z` | `prod` |

**Purpose:** Stable, versioned releases. Both frontend and backend run on NERSC Spin with explicit version tags.

---

## Container Registry

**Registry:** `registry.nersc.gov`

**Images:**
- Backend: `registry.nersc.gov/e3sm/simboard/backend`
- Frontend: `registry.nersc.gov/e3sm/simboard/frontend`

**Access:**
- Authenticate using NERSC credentials: `docker login registry.nersc.gov`
- CI/CD uses GitHub Secrets for automated access

---

## CI/CD Workflows

### 1. Backend Development Builds

**Workflow:** `.github/workflows/build-backend-dev.yml`

**Triggers:**
- Push to `main` branch (only when `backend/**` changes)
- Manual dispatch via GitHub UI

**Actions:**
1. Checkout code
2. Set up Docker Buildx for multi-arch builds
3. Authenticate to NERSC registry
4. Build backend image with `ENV=production`
5. Tag with `:dev` and `:sha-<commit>`
6. Push to registry

**Deployment:** Dev backend on NERSC Spin automatically pulls `:dev` tag (or can be configured for specific SHA tags)

---

### 2. Backend Production Builds

**Workflow:** `.github/workflows/build-backend-prod.yml`

**Triggers:**
- GitHub Release published
- Git tag matching `v*.*.*` pattern (e.g., `v0.3.0`)
- Manual dispatch via GitHub UI

**Actions:**
1. Checkout code at tag/release
2. Set up Docker Buildx
3. Authenticate to NERSC registry
4. Build backend image with `ENV=production`
5. Tag with `:vX.Y.Z`, `:vX.Y`, `:vX`, and `:latest`
6. Push to registry

**Deployment:** Production backend deployment manifests reference explicit version tags (e.g., `:v0.3.0`)

---

### 3. Frontend Development Builds

**Workflow:** `.github/workflows/build-frontend-dev.yml`

**Triggers:**
- Push to `main` branch (only when `frontend/**` changes)
- Manual dispatch with optional `VITE_API_BASE_URL` override

**Actions:**
1. Checkout code
2. Set up Docker Buildx for multi-arch builds
3. Authenticate to NERSC registry
4. Build frontend image with development API URL
5. Tag with `:dev` and `:sha-<commit>`
6. Push to registry

**Build Args:**
- `VITE_API_BASE_URL`: Development API endpoint (default: `https://simboard-dev-api.e3sm.org`)
- `NODE_ENV`: Set to `production`

**Deployment:** Dev frontend on NERSC Spin automatically pulls `:dev` tag (or can be configured for specific SHA tags)

---

### 4. Frontend Production Builds

**Workflow:** `.github/workflows/build-frontend-prod.yml`

**Triggers:**
- GitHub Release published
- Git tag matching `v*.*.*` pattern
- Manual dispatch with optional `VITE_API_BASE_URL` override

**Actions:**
1. Checkout code at tag/release
2. Set up Docker Buildx
3. Authenticate to NERSC registry
4. Build frontend image with production API URL
5. Tag with `:vX.Y.Z`, `:vX.Y`, `:vX`, and `:latest`
6. Push to registry

**Build Args:**
- `VITE_API_BASE_URL`: Production API endpoint (default: `https://simboard-api.e3sm.org`)
- `NODE_ENV`: Set to `production`

**Deployment:** Production frontend on NERSC Spin references explicit version tags

---

## Image Naming and Tagging

### Development Backend

| Tag | Description | Example |
|-----|-------------|---------|
| `:dev` | Latest development build from `main` | `backend:dev` |
| `:sha-<commit>` | Specific commit SHA (short) | `backend:sha-a1b2c3d` |

### Development Frontend

| Tag | Description | Example |
|-----|-------------|---------|
| `:dev` | Latest development build from `main` | `frontend:dev` |
| `:sha-<commit>` | Specific commit SHA (short) | `frontend:sha-a1b2c3d` |

### Production Backend

| Tag | Description | Example |
|-----|-------------|---------|
| `:vX.Y.Z` | Semantic version (immutable) | `backend:v0.3.0` |
| `:vX.Y` | Minor version (mutable) | `backend:v0.3` |
| `:vX` | Major version (mutable) | `backend:v0` |
| `:latest` | Latest production release | `backend:latest` |

### Production Frontend

| Tag | Description | Example |
|-----|-------------|---------|
| `:vX.Y.Z` | Semantic version (immutable) | `frontend:v0.3.0` |
| `:vX.Y` | Minor version (mutable) | `frontend:v0.3` |
| `:vX` | Major version (mutable) | `frontend:v0` |
| `:latest` | Latest production release | `frontend:latest` |

**Best Practice:** Always reference **full semantic versions** (`:vX.Y.Z`) in production Kubernetes manifests for reproducibility and rollback safety.

---

## GitHub Secrets Configuration

The following secrets must be configured in the GitHub repository settings:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `NERSC_REGISTRY_USERNAME` | NERSC registry username | `your-nersc-username` |
| `NERSC_REGISTRY_PASSWORD` | NERSC registry password/token | `your-nersc-password` |

**To configure secrets:**
1. Navigate to repository **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add each secret with the appropriate value

**Security Notes:**
- Use a dedicated service account or token if available
- Rotate credentials periodically
- Never commit credentials to source code

---

## Development Deployment

### Backend (NERSC Spin)

**Image:** `registry.nersc.gov/e3sm/simboard/backend:dev`

**Update Strategy:**
1. Push changes to `main` branch
2. GitHub Actions automatically builds and pushes `:dev` image
3. NERSC Spin deployment pulls latest `:dev` tag (manual or automated via CD tool)

**Kubernetes Deployment Example:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: simboard-backend-dev
  namespace: simboard-dev
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: backend
        image: registry.nersc.gov/e3sm/simboard/backend:dev
        imagePullPolicy: Always  # Always pull latest :dev
        ports:
        - containerPort: 8000
```

**Rolling Restart Command:**
```bash
kubectl rollout restart deployment/simboard-backend-dev -n simboard-dev
```

### Frontend (NERSC Spin)

**Image:** `registry.nersc.gov/e3sm/simboard/frontend:dev`

**Update Strategy:**
1. Push changes to `main` branch
2. GitHub Actions automatically builds and pushes `:dev` image
3. NERSC Spin deployment pulls latest `:dev` tag (manual or automated via CD tool)

**Kubernetes Deployment Example:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: simboard-frontend-dev
  namespace: simboard-dev
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: frontend
        image: registry.nersc.gov/e3sm/simboard/frontend:dev
        imagePullPolicy: Always  # Always pull latest :dev
        ports:
        - containerPort: 80
```

**Rolling Restart Command:**
```bash
kubectl rollout restart deployment/simboard-frontend-dev -n simboard-dev
```

**Note:** A Vercel-hosted dev frontend is also available for rapid prototyping. Vercel deployment is managed automatically on push to `main`.

---

## Production Release Process

### Step 1: Prepare Release

1. **Merge all changes to `main`**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Run full test suite locally**
   ```bash
   make backend-test
   make frontend-lint
   ```

3. **Update version in documentation** (if applicable)

### Step 2: Create GitHub Release

1. **Navigate to GitHub Releases page:**
   ```
   https://github.com/E3SM-Project/simboard/releases/new
   ```

2. **Create a new tag** following semantic versioning:
   - Tag: `v0.3.0` (or appropriate version)
   - Target: `main` branch

3. **Write release notes:**
   - Summarize new features
   - Document breaking changes
   - List bug fixes

4. **Publish release**

### Step 3: Monitor CI/CD

1. **Check GitHub Actions:**
   - Navigate to **Actions** tab
   - Verify `Build Backend (Prod)` and `Build Frontend (Prod)` workflows succeed

2. **Verify images are pushed:**
   ```bash
   # Login to NERSC registry
   docker login registry.nersc.gov
   
   # Pull and verify images
   docker pull registry.nersc.gov/e3sm/simboard/backend:v0.3.0
   docker pull registry.nersc.gov/e3sm/simboard/frontend:v0.3.0
   ```

### Step 4: Deploy to Production (NERSC Spin)

#### Option A: Update Kubernetes Manifests (GitOps)

```yaml
# backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: simboard-backend-prod
  namespace: simboard-prod
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: backend
        image: registry.nersc.gov/e3sm/simboard/backend:v0.3.0  # Update version
        imagePullPolicy: IfNotPresent
```

```yaml
# frontend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: simboard-frontend-prod
  namespace: simboard-prod
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: frontend
        image: registry.nersc.gov/e3sm/simboard/frontend:v0.3.0  # Update version
        imagePullPolicy: IfNotPresent
```

Commit and push changes to trigger deployment (if using ArgoCD or Flux).

#### Option B: Direct kubectl Update

```bash
# Update backend
kubectl set image deployment/simboard-backend-prod \
  backend=registry.nersc.gov/e3sm/simboard/backend:v0.3.0 \
  -n simboard-prod

# Update frontend
kubectl set image deployment/simboard-frontend-prod \
  frontend=registry.nersc.gov/e3sm/simboard/frontend:v0.3.0 \
  -n simboard-prod

# Watch rollout
kubectl rollout status deployment/simboard-backend-prod -n simboard-prod
kubectl rollout status deployment/simboard-frontend-prod -n simboard-prod
```

### Step 5: Verify Production Deployment

1. **Check pod status:**
   ```bash
   kubectl get pods -n simboard-prod
   ```

2. **Check application logs:**
   ```bash
   kubectl logs -l app=simboard-backend -n simboard-prod --tail=50
   kubectl logs -l app=simboard-frontend -n simboard-prod --tail=50
   ```

3. **Test production endpoints:**
   ```bash
   curl https://simboard-api.e3sm.org/api/v1/health
   curl https://simboard.e3sm.org/health
   ```

4. **Smoke test in browser:**
   - Open production URL
   - Verify login works
   - Check key features

### Step 6: Rollback (if needed)

If issues are detected, rollback to previous version:

```bash
# Rollback backend
kubectl rollout undo deployment/simboard-backend-prod -n simboard-prod

# Rollback frontend
kubectl rollout undo deployment/simboard-frontend-prod -n simboard-prod

# Or rollback to specific revision
kubectl rollout undo deployment/simboard-backend-prod --to-revision=2 -n simboard-prod
```

---

## Manual Builds (Local)

For testing or emergency builds, you can manually build and push images.

### Prerequisites

```bash
# Login to NERSC registry
docker login registry.nersc.gov
```

### Backend

```bash
cd backend
docker buildx build \
  --platform=linux/amd64,linux/arm64 \
  --build-arg ENV=production \
  -t registry.nersc.gov/e3sm/simboard/backend:manual-$(date +%Y%m%d) \
  --push \
  .
```

### Frontend

```bash
cd frontend
docker buildx build \
  --platform=linux/amd64,linux/arm64 \
  --build-arg VITE_API_BASE_URL=https://simboard-api.e3sm.org \
  --build-arg NODE_ENV=production \
  -t registry.nersc.gov/e3sm/simboard/frontend:manual-$(date +%Y%m%d) \
  --push \
  .
```

---

## Troubleshooting

### Build Failures

**Issue:** GitHub Actions workflow fails during build

**Solutions:**
1. Check workflow logs in GitHub Actions tab
2. Verify Dockerfiles build locally:
   ```bash
   cd backend && docker build .
   cd frontend && docker build --build-arg VITE_API_BASE_URL=https://example.com .
   ```
3. Ensure all dependencies are available and versions are pinned

### Registry Authentication Failures

**Issue:** `denied: requested access to the resource is denied`

**Solutions:**
1. Verify GitHub Secrets are configured correctly
2. Test credentials locally:
   ```bash
   docker login registry.nersc.gov
   ```
3. Check NERSC registry permissions for your account
4. Ensure credentials haven't expired

### Image Pull Failures on NERSC Spin

**Issue:** Kubernetes pods fail to pull images

**Solutions:**
1. Verify image exists in registry:
   ```bash
   docker pull registry.nersc.gov/e3sm/simboard/backend:v0.3.0
   ```
2. Check ImagePullSecrets in namespace:
   ```bash
   kubectl get secrets -n simboard-prod
   ```
3. Verify image path and tag are correct in deployment manifest
4. Check NERSC Spin node access to registry

### Wrong API URL in Frontend

**Issue:** Production frontend is connecting to wrong backend

**Solutions:**
1. Verify `VITE_API_BASE_URL` in workflow:
   - Check `.github/workflows/build-frontend-prod.yml`
   - Confirm build arg is set correctly
2. Rebuild with correct URL using manual dispatch
3. Check frontend logs for actual API endpoint being used

### Development Image Not Updating

**Issue:** NERSC Spin dev deployment not pulling latest `:dev` image

**Solutions:**
1. Verify image was built and pushed (check GitHub Actions)
2. Force restart deployment:
   ```bash
   kubectl rollout restart deployment/simboard-backend-dev -n simboard-dev
   ```
3. Check `imagePullPolicy` is set to `Always` for `:dev` tag
4. Clear local Docker cache if testing locally

---

## Additional Resources

- [NERSC Container Registry Documentation](https://docs.nersc.gov/development/containers/registry/)
- [NERSC Spin Documentation](https://docs.nersc.gov/services/spin/)
- [Docker Buildx Documentation](https://docs.docker.com/buildx/working-with-buildx/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Semantic Versioning](https://semver.org/)

---

## Support

For questions or issues:
- Open an issue: [GitHub Issues](https://github.com/E3SM-Project/simboard/issues)
- Contact: E3SM DevOps Team
