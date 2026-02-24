# Deployment Guide

Complete reference for CI/CD pipelines and NERSC Spin deployments.

---

## Table of Contents

- [Overview](#overview)
- [Environment Architecture](#environment-architecture)
- [CI/CD Workflows](#cicd-workflows)
- [GitHub Secrets Setup](#github-secrets-setup)
- [Image Tagging Strategy](#image-tagging-strategy)
- [Development Deployment](#development-deployment)
- [Production Release Process](#production-release-process)
- [Kubernetes Configuration](#kubernetes-configuration)
- [Manual Builds](#manual-builds)
- [Troubleshooting](#troubleshooting)

---

## Overview

SimBoard uses **GitHub Actions** to automatically build and publish container images to the **NERSC container registry** (`registry.nersc.gov/e3sm/simboard/`).

**Key Features:**
- ✅ Automated dev builds from `main` branch
- ✅ Production builds from GitHub Releases only
- ✅ Multi-architecture support (linux/amd64, linux/arm64)
- ✅ Semantic versioning for production
- ✅ Docker Buildx with layer caching
- ✅ Separation via image tags and K8s namespaces

---

## Environment Architecture

### Development

| Component | Hosting | Image | Pull Policy |
|-----------|---------|-------|-------------|
| Backend | NERSC Spin (dev) | `backend:dev` | Always |
| Frontend | NERSC Spin (dev) | `frontend:dev` | Always |

**Trigger:** Automatic on push to `main`

### Production

| Component | Hosting | Image | Pull Policy |
|-----------|---------|-------|-------------|
| Backend | NERSC Spin (prod) | `backend:v0.3.0` | IfNotPresent |
| Frontend | NERSC Spin (prod) | `frontend:v0.3.0` | IfNotPresent |

**Trigger:** Manual via GitHub Release

---

## CI/CD Workflows

### Backend Dev (`build-backend-dev.yml`)

**Triggers:** Push to `main` (backend changes) or manual dispatch

**Tags:** `:dev`, `:sha-<commit>`

**Registry:** `registry.nersc.gov/e3sm/simboard/backend`

---

### Frontend Dev (`build-frontend-dev.yml`)

**Triggers:** Push to `main` (frontend changes) or manual dispatch

**Tags:** `:dev`, `:sha-<commit>`

**Build args:**
- `VITE_API_BASE_URL`: `https://simboard-dev-api.e3sm.org` (default)

**Registry:** `registry.nersc.gov/e3sm/simboard/frontend`

---

### Backend Prod (`build-backend-prod.yml`)

**Triggers:** GitHub Release or tag `v*.*.*`

**Tags:** `:vX.Y.Z`, `:vX.Y`, `:vX`, `:latest`

**Registry:** `registry.nersc.gov/e3sm/simboard/backend`

---

### Frontend Prod (`build-frontend-prod.yml`)

**Triggers:** GitHub Release or tag `v*.*.*`

**Tags:** `:vX.Y.Z`, `:vX.Y`, `:vX`, `:latest`

**Build args:**
- `VITE_API_BASE_URL`: `https://simboard-api.e3sm.org` (default, override in manual dispatch)

**Registry:** `registry.nersc.gov/e3sm/simboard/frontend`

---

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

---

## Image Tagging Strategy

### Development Images

| Tag | Description | Use Case |
|-----|-------------|----------|
| `:dev` | Latest from `main` | Primary dev deployment |
| `:sha-a1b2c3d` | Specific commit | Debugging, rollback |

### Production Images

| Tag | Description | Use Case |
|-----|-------------|----------|
| `:v0.3.0` | Full version | Production (recommended) |
| `:v0.3` | Minor version | Auto-update patches |
| `:v0` | Major version | Auto-update minors |
| `:latest` | Latest release | Reference only |

**Best practice:** Use full semantic versions (`:vX.Y.Z`) in production for reproducibility.

---

## Development Deployment

### Update Dev Environment

Development images are automatically built and pushed when you push to `main`. To deploy:

```bash
# Force restart to pull latest :dev images
kubectl rollout restart deployment/simboard-backend-dev -n simboard-dev
kubectl rollout restart deployment/simboard-frontend-dev -n simboard-dev

# Check status
kubectl get pods -n simboard-dev
kubectl logs -l app=simboard-backend -n simboard-dev --tail=20
```

### Kubernetes Manifests

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: simboard-backend-dev
  namespace: simboard-dev
spec:
  template:
    spec:
      containers:
      - name: backend
        image: registry.nersc.gov/e3sm/simboard/backend:dev
        imagePullPolicy: Always
```

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: simboard-frontend-dev
  namespace: simboard-dev
spec:
  template:
    spec:
      containers:
      - name: frontend
        image: registry.nersc.gov/e3sm/simboard/frontend:dev
        imagePullPolicy: Always
```

---

## Production Release Process

### Step 1: Prepare Release

```bash
# Ensure main is up to date
git checkout main && git pull

# Run tests
make backend-test
make frontend-lint
```

### Step 2: Create GitHub Release

1. Go to [Releases](https://github.com/E3SM-Project/simboard/releases/new)
2. Create new tag: `v0.3.0` (semantic versioning)
3. Target: `main`
4. Write release notes (features, fixes, breaking changes)
5. Publish release

**This triggers both backend and frontend production builds automatically.**

### Step 3: Monitor Builds

Check [Actions tab](https://github.com/E3SM-Project/simboard/actions) - both workflows should complete in ~10-15 minutes.

### Step 4: Deploy to Production

**Option A: Update manifests (GitOps)**

Update your Kubernetes manifests:
```yaml
image: registry.nersc.gov/e3sm/simboard/backend:v0.3.0
image: registry.nersc.gov/e3sm/simboard/frontend:v0.3.0
```

**Option B: Direct kubectl update**

```bash
kubectl set image deployment/simboard-backend-prod \
  backend=registry.nersc.gov/e3sm/simboard/backend:v0.3.0 \
  -n simboard-prod

kubectl set image deployment/simboard-frontend-prod \
  frontend=registry.nersc.gov/e3sm/simboard/frontend:v0.3.0 \
  -n simboard-prod

# Watch rollout
kubectl rollout status deployment/simboard-backend-prod -n simboard-prod
kubectl rollout status deployment/simboard-frontend-prod -n simboard-prod
```

### Step 5: Verify Production

```bash
# Check pods
kubectl get pods -n simboard-prod

# Check logs
kubectl logs -l app=simboard-backend -n simboard-prod --tail=50

# Test endpoints
curl https://simboard-api.e3sm.org/api/v1/health
curl https://simboard.e3sm.org/health
```

### Rollback (if needed)

```bash
kubectl rollout undo deployment/simboard-backend-prod -n simboard-prod
kubectl rollout undo deployment/simboard-frontend-prod -n simboard-prod
```

---

## Kubernetes Configuration

### Development Deployment Example

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: simboard-backend-dev
  namespace: simboard-dev
spec:
  replicas: 1
  selector:
    matchLabels:
      app: simboard-backend
  template:
    metadata:
      labels:
        app: simboard-backend
    spec:
      containers:
      - name: backend
        image: registry.nersc.gov/e3sm/simboard/backend:dev
        imagePullPolicy: Always  # Always pull latest :dev
        ports:
        - containerPort: 8000
        env:
        - name: ENV
          value: "production"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: simboard-secrets
              key: database-url
```

### Production Deployment Example

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: simboard-backend-prod
  namespace: simboard-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: simboard-backend
  template:
    metadata:
      labels:
        app: simboard-backend
    spec:
      containers:
      - name: backend
        image: registry.nersc.gov/e3sm/simboard/backend:v0.3.0
        imagePullPolicy: IfNotPresent  # Use immutable version
        ports:
        - containerPort: 8000
        env:
        - name: ENV
          value: "production"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: simboard-secrets
              key: database-url
```

---

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

---

## Troubleshooting

### Authentication Failures

**Issue:** `denied: requested access to the resource is denied`

**Solutions:**
1. Verify GitHub Secrets are configured
2. Test credentials: `docker login registry.nersc.gov`
3. Check NERSC account has push permissions to `e3sm/simboard/` namespace

---

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

---

### Dev Image Not Updating

**Issue:** NERSC Spin not pulling latest `:dev`

**Solutions:**
1. Verify image was built (check GitHub Actions)
2. Force restart: `kubectl rollout restart deployment/... -n simboard-dev`
3. Check `imagePullPolicy: Always` is set for `:dev` tags

---

### Wrong API URL in Frontend

**Issue:** Frontend connecting to wrong backend

**Solutions:**
1. Check `VITE_API_BASE_URL` in workflow file
2. Rebuild with manual dispatch and correct URL
3. Verify environment-specific URLs:
   - Dev: `https://simboard-dev-api.e3sm.org`
   - Prod: `https://simboard-api.e3sm.org`

---

### Workflow Not Triggering

**Issue:** Push to main doesn't trigger build

**Solutions:**
1. Verify changes are in watched paths:
   - Backend: `backend/**`
   - Frontend: `frontend/**`
2. Check workflow files exist and are on `main` branch
3. Verify Actions are enabled in repository settings

---

## Additional Resources

- [NERSC Container Registry Docs](https://docs.nersc.gov/development/containers/registry/)
- [NERSC Spin Docs](https://docs.nersc.gov/services/spin/)
- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Docker Buildx Docs](https://docs.docker.com/buildx/working-with-buildx/)
- [Semantic Versioning](https://semver.org/)

---

## Support

- **GitHub Issues:** [Open an issue](https://github.com/E3SM-Project/simboard/issues)
- **Workflow Logs:** [Actions tab](https://github.com/E3SM-Project/simboard/actions)
- **Contact:** E3SM DevOps Team
