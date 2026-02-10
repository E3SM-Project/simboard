# CI/CD Implementation Summary

This document summarizes the automated CI/CD pipeline implementation for SimBoard container builds to NERSC Registry.

## What Was Implemented

### 1. GitHub Actions Workflows (4 new workflows)

#### `build-backend-dev.yml` - Development Backend Builds
- **Trigger:** Push to `main` branch (backend changes)
- **Image:** `registry.nersc.gov/e3sm/simboard/backend`
- **Tags:** `:dev`, `:sha-<commit>`
- **Purpose:** Continuous deployment to NERSC Spin dev environment

#### `build-frontend-dev.yml` - Development Frontend Builds
- **Trigger:** Push to `main` branch (frontend changes)
- **Image:** `registry.nersc.gov/e3sm/simboard/frontend`
- **Tags:** `:dev`, `:sha-<commit>`
- **Purpose:** Continuous deployment to NERSC Spin dev environment
- **Special:** Supports manual dispatch with custom API URL

#### `build-backend-prod.yml` - Production Backend Builds
- **Trigger:** GitHub Release or version tag (e.g., `v0.3.0`)
- **Image:** `registry.nersc.gov/e3sm/simboard/backend`
- **Tags:** `:vX.Y.Z`, `:vX.Y`, `:vX`, `:latest`
- **Purpose:** Versioned releases for NERSC Spin production environment

#### `build-frontend-prod.yml` - Production Frontend Builds
- **Trigger:** GitHub Release or version tag (e.g., `v0.3.0`)
- **Image:** `registry.nersc.gov/e3sm/simboard/frontend`
- **Tags:** `:vX.Y.Z`, `:vX.Y`, `:vX`, `:latest`
- **Purpose:** Versioned releases for NERSC Spin production environment
- **Special:** Supports manual dispatch with custom API URL

### 2. Documentation (4 new documents)

#### `docs/DEPLOYMENT.md` (13.7 KB)
Comprehensive deployment guide covering:
- Environment architecture
- CI/CD workflow details
- Image naming and tagging conventions
- Complete production release process
- Kubernetes deployment examples
- Troubleshooting guide

#### `docs/GITHUB_SECRETS.md` (4.1 KB)
GitHub Secrets configuration guide:
- Required secrets list and descriptions
- Step-by-step setup instructions
- Testing and troubleshooting
- Security best practices

#### `docs/CI_CD_REFERENCE.md` (7.0 KB)
Quick reference guide:
- Workflow overview table
- Trigger conditions
- Manual dispatch instructions
- Common operations
- Monitoring and troubleshooting

#### Updated `README.md`
- Added "Deployment & CI/CD" section
- Linked to comprehensive documentation
- Updated manual build instructions
- Clarified automated vs manual workflows

### 3. Workflow Features

All workflows include:
- ✅ Multi-architecture builds (linux/amd64, linux/arm64)
- ✅ Docker Buildx with layer caching
- ✅ Secure authentication via GitHub Secrets
- ✅ Semantic versioning for production builds
- ✅ GitHub Actions summary with build details
- ✅ Manual dispatch capability for all workflows

## Architecture Decisions

### Environment Separation Strategy

**Development:**
- Frontend: NERSC Spin dev namespace (`:dev` tag from `main`)
- Backend: NERSC Spin dev namespace (`:dev` tag from `main`)

**Production:**
- Frontend: NERSC Spin prod namespace (`:vX.Y.Z` tag from releases)
- Backend: NERSC Spin prod namespace (`:vX.Y.Z` tag from releases)

**Rationale:**
- Both dev frontend and backend on NERSC Spin enable consistent deployment pipeline
- Vercel-hosted dev frontend remains available for rapid UX prototyping
- Explicit versioning for production ensures immutable, auditable deployments
- Separation via image tags and K8s namespaces (not separate infrastructure)

### Image Tagging Strategy

**Development Backend:**
- `:dev` - Always points to latest `main` build (mutable, for CD)
- `:sha-<commit>` - Specific commit (immutable, for debugging/rollback)

**Development Frontend:**
- `:dev` - Always points to latest `main` build (mutable, for CD)
- `:sha-<commit>` - Specific commit (immutable, for debugging/rollback)

**Production Images:**
- `:vX.Y.Z` - Full semantic version (immutable, recommended for prod)
- `:vX.Y` - Minor version (mutable, updates with patches)
- `:vX` - Major version (mutable, updates with minors)
- `:latest` - Latest release (mutable, for reference)

**Best Practice:** Production K8s manifests should reference `:vX.Y.Z` for reproducibility.

### Workflow Triggers

**Automatic:**
- `main` push → Dev backend build
- Release/tag → Prod backend and frontend builds

**Manual:**
- All workflows support manual dispatch
- Frontend prod supports custom `VITE_API_BASE_URL` override

**Rationale:**
- Automatic dev builds enable continuous deployment
- Explicit prod releases prevent accidental promotions
- Manual dispatch enables emergency builds and testing

## Required Setup

### GitHub Secrets (Required for workflows to run)

| Secret | Description |
|--------|-------------|
| `NERSC_REGISTRY_USERNAME` | NERSC registry username |
| `NERSC_REGISTRY_PASSWORD` | NERSC registry password/token |

**Setup:** See `docs/GITHUB_SECRETS.md`

### NERSC Registry Permissions

The account used in GitHub Secrets must have:
- Read/write access to `registry.nersc.gov/e3sm/simboard/` namespace
- Permission to push images to the registry

### Kubernetes Configuration (NERSC Spin)

**Dev Backend:**
```yaml
image: registry.nersc.gov/e3sm/simboard/backend:dev
imagePullPolicy: Always  # Pull latest :dev on restart
```

**Prod Backend:**
```yaml
image: registry.nersc.gov/e3sm/simboard/backend:v0.3.0
imagePullPolicy: IfNotPresent  # Use immutable version
```

**Prod Frontend:**
```yaml
image: registry.nersc.gov/e3sm/simboard/frontend:v0.3.0
imagePullPolicy: IfNotPresent  # Use immutable version
```

## Release Workflow

### Development Cycle
1. Developer pushes changes to `main`
2. Backend CI runs (tests, linting)
3. If backend changed, dev backend build workflow runs
4. New `:dev` image pushed to NERSC registry
5. NERSC Spin dev backend (optionally) automatically pulls new `:dev` image

### Production Release
1. Team decides to cut a release
2. Create GitHub Release with tag `vX.Y.Z` targeting `main`
3. Prod backend and frontend build workflows trigger automatically
4. Multi-arch images built and pushed with multiple tags
5. DevOps team updates K8s manifests to reference `:vX.Y.Z`
6. Production deployment rolled out on NERSC Spin
7. Verification and smoke testing

### Rollback (if needed)
```bash
kubectl rollout undo deployment/simboard-backend-prod -n simboard-prod
```

## Validation Checklist

- [x] All workflow YAML files are syntactically valid
- [x] Workflows use latest stable action versions
- [x] Docker contexts correctly reference `./backend` and `./frontend`
- [x] Multi-architecture builds configured (amd64, arm64)
- [x] Build args properly configured (ENV, VITE_API_BASE_URL)
- [x] Registry authentication uses GitHub Secrets
- [x] Image tags follow semantic versioning conventions
- [x] Workflows include job summaries for visibility
- [x] Manual dispatch enabled for all build workflows
- [x] Documentation covers all workflows and processes
- [x] GitHub Secrets configuration documented
- [x] Troubleshooting guides included
- [x] README.md updated with CI/CD information

## What Needs to be Done Next

### By Repository Administrators

1. **Configure GitHub Secrets** (Required)
   - Navigate to Settings → Secrets and variables → Actions
   - Add `NERSC_REGISTRY_USERNAME`
   - Add `NERSC_REGISTRY_PASSWORD`
   - See `docs/GITHUB_SECRETS.md` for details

2. **Verify NERSC Registry Access** (Required)
   - Ensure the account has push permissions to `e3sm/simboard/` namespace
   - Test with `docker login registry.nersc.gov`

3. **Test Workflows** (Recommended)
   - Trigger manual dispatch of `Build Backend (Dev)`
   - Verify image appears in NERSC registry
   - Check workflow logs for any issues

### By DevOps Team

4. **Update NERSC Spin Deployments** (Required for automation)
   - Configure dev backend to use `backend:dev` image
   - Set `imagePullPolicy: Always` for dev deployments
   - Configure prod deployments to use versioned tags (`:vX.Y.Z`)
   - Set `imagePullPolicy: IfNotPresent` for prod deployments

5. **Set Up Continuous Deployment (Optional)**
   - Configure ArgoCD, Flux, or similar for GitOps
   - Or set up webhook to trigger K8s rolling update on new `:dev` image

6. **Configure Monitoring (Recommended)**
   - Set up GitHub Actions notifications
   - Monitor workflow failures
   - Track deployment metrics

### By Development Team

7. **Follow Release Process** (When ready)
   - Cut first release using GitHub Releases
   - Verify workflows build and push images
   - Deploy to production following `docs/DEPLOYMENT.md`

## Success Criteria

✅ **Implementation Complete** when:
- [x] All workflow files created and validated
- [x] Documentation complete and comprehensive
- [x] README.md updated with CI/CD information
- [ ] GitHub Secrets configured (requires admin)
- [ ] First dev build successfully pushed to registry
- [ ] First prod release successfully built and deployed
- [ ] Team trained on release process

## Maintenance

### Regular Tasks
- Rotate NERSC registry credentials every 90 days
- Update GitHub Actions versions when new releases available
- Review and update documentation as processes evolve

### Monitoring
- Watch for failed workflow runs
- Monitor image sizes (optimize if growing)
- Track build times (optimize if increasing)

## Documentation Links

- **Full Deployment Guide:** [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md)
- **GitHub Secrets Setup:** [docs/GITHUB_SECRETS.md](../docs/GITHUB_SECRETS.md)
- **Workflow Reference:** [docs/CI_CD_REFERENCE.md](../docs/CI_CD_REFERENCE.md)
- **Main README:** [README.md](../README.md)

## Support

For questions or issues:
- Check documentation first
- Review workflow logs in GitHub Actions
- Open an issue: [GitHub Issues](https://github.com/E3SM-Project/simboard/issues)
- Contact: E3SM DevOps Team
