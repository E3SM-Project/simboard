# CI/CD Automation for NERSC Container Builds

Automated multi-arch container builds to NERSC Registry with dev/prod separation.

---

## 🚀 Quick Start

> Note: A NERSC E3SM project robot account is provided to SimBoard administrators for automated
> deployment on NERSC registry.

### 1. Configure GitHub Secrets (Required)

Add these secrets in [repository settings](https://github.com/E3SM-Project/simboard/settings/secrets/actions):

- `NERSC_REGISTRY_USERNAME` - Your NERSC username
- `NERSC_REGISTRY_PASSWORD` - Your NERSC password or token

### 2. Test the Setup

Trigger a manual build:

1. Go to [Actions](https://github.com/E3SM-Project/simboard/actions)
2. Select "Build Backend (Dev)" or "Build Frontend (Dev)"
3. Click "Run workflow" → Select `main` → Run

### 3. Verify Images

```bash
docker login registry.nersc.gov
docker pull registry.nersc.gov/e3sm/simboard/backend:dev
docker pull registry.nersc.gov/e3sm/simboard/frontend:dev
```

---

## 📋 Workflows

| Workflow                  | Trigger                           | Image Tags              |
| ------------------------- | --------------------------------- | ----------------------- |
| `build-backend-dev.yml`   | Push to `main` (backend changes)  | `:dev`, `:sha-<commit>` |
| `build-frontend-dev.yml`  | Push to `main` (frontend changes) | `:dev`, `:sha-<commit>` |
| `build-backend-prod.yml`  | Release or tag `v*.*.*`           | `:vX.Y.Z`, `:latest`    |
| `build-frontend-prod.yml` | Release or tag `v*.*.*`           | `:vX.Y.Z`, `:latest`    |

**Registry:** `registry.nersc.gov/e3sm/simboard/{backend,frontend}`

**Features:**

- Multi-arch builds (linux/amd64, linux/arm64)
- Docker Buildx with layer caching
- Automatic tagging with semantic versioning
- Manual dispatch support

---

## 🏗️ Architecture

```
Development:
  main branch → :dev tag → NERSC Spin dev namespace

Production:
  GitHub Release → :vX.Y.Z tag → NERSC Spin prod namespace
```

**Dev Environment:**

- Backend: `registry.nersc.gov/e3sm/simboard/backend:dev`
- Frontend: `registry.nersc.gov/e3sm/simboard/frontend:dev`
- Updates automatically on push to `main`

**Prod Environment:**

- Backend: `registry.nersc.gov/e3sm/simboard/backend:v0.3.0`
- Frontend: `registry.nersc.gov/e3sm/simboard/frontend:v0.3.0`
- Explicitly versioned via GitHub Releases

---

## 📦 Creating a Release

1. **Prepare:**

   ```bash
   git checkout main && git pull
   make backend-test && make frontend-lint
   ```

2. **Create release on GitHub:**
   - Go to [Releases](https://github.com/E3SM-Project/simboard/releases/new)
   - Create tag: `v0.3.0`
   - Write release notes
   - Publish release

3. **Monitor builds:**
   - Check [Actions](https://github.com/E3SM-Project/simboard/actions) tab
   - Both backend and frontend prod workflows will trigger

4. **Deploy to NERSC Spin:**

   ```bash
   kubectl set image deployment/simboard-backend-prod \
     backend=registry.nersc.gov/e3sm/simboard/backend:v0.3.0 \
     -n simboard-prod

   kubectl set image deployment/simboard-frontend-prod \
     frontend=registry.nersc.gov/e3sm/simboard/frontend:v0.3.0 \
     -n simboard-prod
   ```

---

## 🔧 NERSC Spin Deployment

### Development

```yaml
# Dev deployments use :dev tag with Always pull policy
image: registry.nersc.gov/e3sm/simboard/backend:dev
imagePullPolicy: Always
```

Restart to pull latest:

```bash
kubectl rollout restart deployment/simboard-backend-dev -n simboard-dev
kubectl rollout restart deployment/simboard-frontend-dev -n simboard-dev
```

### Production

```yaml
# Prod deployments use explicit versions with IfNotPresent
image: registry.nersc.gov/e3sm/simboard/backend:v0.3.0
imagePullPolicy: IfNotPresent
```

---

## 🐛 Troubleshooting

**Build fails with "authentication required":**

- Verify GitHub Secrets are configured correctly
- Test: `docker login registry.nersc.gov` locally

**Image not updating in dev:**

- Force restart: `kubectl rollout restart deployment/... -n simboard-dev`
- Check imagePullPolicy is `Always` for `:dev` tags

**Workflow not triggering:**

- Verify file changes match workflow paths (e.g., `backend/**`)
- Check Actions are enabled in repository settings

**For more help:** See [DEPLOYMENT.md](DEPLOYMENT.md) for complete documentation

---

## 📚 Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete reference guide with detailed workflows, Kubernetes examples, and troubleshooting

---

## 🔗 Quick Links

- [NERSC Registry](https://registry.nersc.gov/harbor/projects)
- [NERSC Spin Dashboard](https://rancher2.spin.nersc.gov/)
- [GitHub Actions](https://github.com/E3SM-Project/simboard/actions)
- [Repository Settings](https://github.com/E3SM-Project/simboard/settings)
