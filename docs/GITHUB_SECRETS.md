# GitHub Secrets Configuration

This document describes the GitHub Secrets required for the CI/CD pipelines.

## Required Secrets

The following secrets must be configured in the GitHub repository to enable automated container builds and deployments to the NERSC registry.

### 1. NERSC_REGISTRY_USERNAME

**Description:** Username for authenticating to the NERSC container registry (`registry.nersc.gov`)

**Value:** Your NERSC username or service account username

**Example:** `your-nersc-username`

---

### 2. NERSC_REGISTRY_PASSWORD

**Description:** Password or access token for authenticating to the NERSC container registry

**Value:** Your NERSC password or a personal access token

**Example:** `your-nersc-password-or-token`

**Security Note:** If available, prefer using a personal access token or service account token over your main account password.

---

## How to Configure Secrets

### Step 1: Navigate to Repository Settings

1. Go to the GitHub repository: <https://github.com/E3SM-Project/simboard>
2. Click on **Settings** (requires admin access)

### Step 2: Access Secrets Configuration

1. In the left sidebar, navigate to:
   - **Security** → **Secrets and variables** → **Actions**

### Step 3: Add Each Secret

For each secret listed above:

1. Click **New repository secret**
2. Enter the **Name** (exactly as shown above, case-sensitive)
3. Enter the **Value** (the actual credential)
4. Click **Add secret**

### Step 4: Verify Secrets

After adding secrets, they should appear in the list (values are hidden for security).

You should see:
- ✅ `NERSC_REGISTRY_USERNAME`
- ✅ `NERSC_REGISTRY_PASSWORD`

---

## Testing the Configuration

### Option 1: Trigger a Manual Workflow Run

1. Navigate to **Actions** tab
2. Select **Build Backend (Dev)** workflow
3. Click **Run workflow** → **Run workflow**
4. Check the workflow logs for successful authentication

### Option 2: Push to Main Branch

1. Make a small change to `backend/` directory
2. Commit and push to `main` branch
3. GitHub Actions should automatically trigger the dev backend build
4. Check workflow logs for success

---

## Troubleshooting

### "Invalid username or password" Error

**Solution:**
1. Verify the secrets are entered correctly (no extra spaces)
2. Test credentials locally:
   ```bash
   docker login registry.nersc.gov
   # Use the same credentials you entered as secrets
   ```
3. If local login works but GitHub Actions fails, the secrets may be incorrectly formatted

### "Access denied" or "Forbidden" Error

**Solution:**
1. Verify your NERSC account has permission to push to the `e3sm/simboard/` namespace
2. Contact NERSC support to request access if needed
3. Check if your credentials have expired

### Secrets Not Appearing in Workflow

**Solution:**
1. Verify you have admin access to the repository
2. Ensure secrets are added at the **repository** level (not environment level)
3. Restart the workflow run after adding secrets

---

## Security Best Practices

- ✅ **Never commit secrets to source code** - Always use GitHub Secrets
- ✅ **Use service accounts when possible** - Avoid using personal credentials for CI/CD
- ✅ **Rotate credentials periodically** - Update secrets every 90 days or per your organization's policy
- ✅ **Use minimal permissions** - Service accounts should only have push access to the specific registry namespace
- ✅ **Audit secret usage** - Review GitHub Actions logs periodically to ensure secrets are used appropriately

---

## Additional Resources

- [GitHub Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [NERSC Container Registry Documentation](https://docs.nersc.gov/development/containers/registry/)
- [Docker Login Documentation](https://docs.docker.com/engine/reference/commandline/login/)

---

## Support

For issues with:
- **GitHub Secrets:** Contact repository administrators
- **NERSC Registry Access:** Contact NERSC support or E3SM DevOps team
- **Workflow Errors:** Check workflow logs and see [docs/DEPLOYMENT.md](DEPLOYMENT.md) troubleshooting section
