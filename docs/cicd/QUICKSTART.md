# Quick Start: CI/CD Setup

This guide helps you quickly set up and test the CI/CD pipelines.

## For Repository Administrators

### Step 1: Configure GitHub Secrets (5 minutes)

1. **Navigate to repository settings:**
   ```
   https://github.com/E3SM-Project/simboard/settings/secrets/actions
   ```

2. **Add two secrets:**

   **Secret 1: NERSC_REGISTRY_USERNAME**
   - Click "New repository secret"
   - Name: `NERSC_REGISTRY_USERNAME`
   - Value: Your NERSC username
   - Click "Add secret"

   **Secret 2: NERSC_REGISTRY_PASSWORD**
   - Click "New repository secret"
   - Name: `NERSC_REGISTRY_PASSWORD`
   - Value: Your NERSC password or token
   - Click "Add secret"

### Step 2: Verify Registry Access (2 minutes)

Test locally that the credentials work:

```bash
docker login registry.nersc.gov
# Enter the same username and password you used in Step 1
# Should see: "Login Succeeded"
```

### Step 3: Test Dev Backend Build (5 minutes)

Trigger a manual build:

1. Go to: https://github.com/E3SM-Project/simboard/actions
2. Select **"Build Backend (Dev)"** workflow
3. Click **"Run workflow"** dropdown
4. Select branch: `main`
5. Click **"Run workflow"** button
6. Wait ~10-15 minutes for build to complete
7. Check the workflow run logs

**Expected result:** ✅ Workflow completes successfully, image pushed to registry

### Step 4: Test Dev Frontend Build (Optional, 5 minutes)

Optionally trigger a frontend dev build:

1. Go to: https://github.com/E3SM-Project/simboard/actions
2. Select **"Build Frontend (Dev)"** workflow
3. Click **"Run workflow"** dropdown
4. Select branch: `main`
5. Click **"Run workflow"** button
6. Wait ~10-15 minutes for build to complete

**Expected result:** ✅ Workflow completes successfully, image pushed to registry

### Step 5: Verify Images (2 minutes)

```bash
docker login registry.nersc.gov
docker pull registry.nersc.gov/e3sm/simboard/backend:dev
docker pull registry.nersc.gov/e3sm/simboard/frontend:dev
docker inspect registry.nersc.gov/e3sm/simboard/backend:dev
docker inspect registry.nersc.gov/e3sm/simboard/frontend:dev
```

**Expected result:** ✅ Images download successfully

---

## For DevOps Team

### Step 6: Update NERSC Spin Dev Deployments (15 minutes)

Update your Kubernetes deployments to use the new images:

```yaml
# dev-backend-deployment.yaml
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
        imagePullPolicy: Always  # Important: Always pull latest :dev
```

```yaml
# dev-frontend-deployment.yaml
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
        imagePullPolicy: Always  # Important: Always pull latest :dev
```

Apply the deployments:

```bash
kubectl apply -f dev-backend-deployment.yaml
kubectl apply -f dev-frontend-deployment.yaml
kubectl rollout status deployment/simboard-backend-dev -n simboard-dev
kubectl rollout status deployment/simboard-frontend-dev -n simboard-dev
```

**Expected result:** ✅ Pods restart with new images

### Step 7: Verify Dev Deployments (2 minutes)

```bash
# Check pods are running
kubectl get pods -n simboard-dev

# Check logs
kubectl logs -l app=simboard-backend -n simboard-dev --tail=20
kubectl logs -l app=simboard-frontend -n simboard-dev --tail=20

# Test health endpoints (adjust URLs to your setup)
curl https://simboard-dev-api.e3sm.org/api/v1/health
curl https://simboard-dev.e3sm.org/health
```

**Expected result:** ✅ Both backend and frontend are healthy and responding

---

## For Development Team

### Step 8: Test Automated Dev Builds (5 minutes)

Make a small change to trigger automatic build:

```bash
# Make a trivial change
cd backend
echo "# CI/CD test" >> README.md
git add README.md
git commit -m "test: trigger dev backend build"
git push origin main
```

**Expected result:** ✅ Workflow automatically triggers and completes

You can also test frontend builds:

```bash
# Make a trivial change to frontend
cd frontend
echo "# CI/CD test" >> README.md
git add README.md
git commit -m "test: trigger dev frontend build"
git push origin main
```

**Expected result:** ✅ Frontend dev workflow automatically triggers and completes

### Step 9: Cut a Test Release (10 minutes)

Create a test release to verify production builds:

1. **Create and push a tag:**
   ```bash
   git tag v0.1.0-test
   git push origin v0.1.0-test
   ```

2. **Create GitHub Release:**
   - Go to: https://github.com/E3SM-Project/simboard/releases/new
   - Select tag: `v0.1.0-test`
   - Title: "Test Release v0.1.0"
   - Description: "Testing CI/CD pipeline"
   - Check "This is a pre-release"
   - Click "Publish release"

3. **Monitor workflows:**
   - Go to Actions tab
   - Watch "Build Backend (Prod)" and "Build Frontend (Prod)"
   - Wait ~10-15 minutes for both to complete

**Expected result:** ✅ Both workflows complete successfully

4. **Verify images:**
   ```bash
   docker pull registry.nersc.gov/e3sm/simboard/backend:v0.1.0-test
   docker pull registry.nersc.gov/e3sm/simboard/frontend:v0.1.0-test
   ```

**Expected result:** ✅ Both images are available

### Step 10: Deploy to Production (Optional, 15 minutes)

If you're ready to test production deployment:

```yaml
# prod-backend-deployment.yaml
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
        image: registry.nersc.gov/e3sm/simboard/backend:v0.1.0-test
        imagePullPolicy: IfNotPresent
```

```yaml
# prod-frontend-deployment.yaml
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
        image: registry.nersc.gov/e3sm/simboard/frontend:v0.1.0-test
        imagePullPolicy: IfNotPresent
```

Apply deployments:

```bash
kubectl apply -f prod-backend-deployment.yaml
kubectl apply -f prod-frontend-deployment.yaml

kubectl rollout status deployment/simboard-backend-prod -n simboard-prod
kubectl rollout status deployment/simboard-frontend-prod -n simboard-prod
```

**Expected result:** ✅ Production deployments succeed

---

## Troubleshooting

### Issue: "No such secret" error

**Solution:** Verify secrets are configured at repository level, not environment level.

### Issue: Workflow doesn't trigger

**Solution:** 
- Check workflow file is on the correct branch
- Verify trigger conditions (paths, branches)
- Check Actions are enabled in repository settings

### Issue: Build fails with "authentication required"

**Solution:**
- Verify GitHub Secrets are set correctly
- Test credentials locally with `docker login registry.nersc.gov`
- Check NERSC account has push permissions to `e3sm/simboard/` namespace

### Issue: Image not found in registry

**Solution:**
- Check workflow completed successfully (no errors in logs)
- Verify correct image name and tag
- Try `docker pull registry.nersc.gov/e3sm/simboard/backend:dev` locally

---

## Success Checklist

After completing all steps, you should have:

- [x] GitHub Secrets configured
- [x] Dev backend builds automatically on `main` push
- [x] Prod builds trigger on releases
- [x] Images are accessible from NERSC Spin
- [x] Dev backend deployed and running on NERSC Spin
- [x] Test release created and images verified
- [x] Team familiar with release process

---

## Next Steps

Now that CI/CD is set up:

1. **Remove test release** (if created):
   ```bash
   git tag -d v0.1.0-test
   git push origin :refs/tags/v0.1.0-test
   ```
   Delete release from GitHub UI

2. **Plan first real release**:
   - Review [DEPLOYMENT.md](DEPLOYMENT.md) for full release process
   - Coordinate with team on release schedule

3. **Set up monitoring**:
   - Configure GitHub Actions notifications
   - Monitor workflow failures
   - Set up alerts for deployment issues

4. **Update documentation**:
   - Document any environment-specific configurations
   - Update deployment runbooks

---

## Getting Help

- **Full Documentation:** [DEPLOYMENT.md](DEPLOYMENT.md)
- **Secrets Setup:** [GITHUB_SECRETS.md](GITHUB_SECRETS.md)
- **Workflow Reference:** [REFERENCE.md](CI_CD_REFERENCE.md)
- **Open an Issue:** https://github.com/E3SM-Project/simboard/issues
