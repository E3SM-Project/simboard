# Test Ingestion Operations

Use this procedure to exercise site-ingestion operations in an isolated test
deployment before using production credentials or installing a crontab. Run it
from a local checkout or an HPC-site checkout; it creates an isolated deployment
root below `/tmp` and clones the current branch.

Do not install the generated crontab during this test.

This is the first required validation before remote-site deployment. After it
succeeds, follow [Set Up Ingestion Operations](setup-ingestion-operations.md)
to validate the target HPC site with a dry run before enabling scheduled work.

## 1. Define an isolated deployment

Run these commands from the repository root:

```bash
export TEST_ROOT="/tmp/simboard-operations-test"
export SIMBOARD_ROOT="${TEST_ROOT}/deployment"
export SIMBOARD_REPOSITORY_URL="file://$(pwd)"
export SIMBOARD_REPOSITORY_REF="$(git branch --show-current)"
```

The repository URL and ref direct provisioning to clone the current branch
rather than the public repository default.

Remove a previous test deployment, if present:

```bash
rm -rf "${TEST_ROOT}"
```

## 2. Provision the deployment

```bash
make operations-provision
```

This creates `${SIMBOARD_ROOT}`, creates `${SIMBOARD_ROOT}/operations`, clones
the checkout into `${SIMBOARD_ROOT}/repository/simboard`, and synchronizes the
backend runtime.

Inspect the resulting deployment:

```bash
ls -la "${SIMBOARD_ROOT}"
ls -la "${SIMBOARD_ROOT}/operations"
git -C "${SIMBOARD_ROOT}/repository/simboard" status --short
```

The checkout status should be clean.

## 3. Initialize dummy API environments

```bash
make operations-init-env site=chrysalis
```

Use harmless test values at the prompts:

```text
dev SIMBOARD_API_BASE_URL [https://simboard-dev-api.e3sm.org]: https://dev.example.test
dev SIMBOARD_API_TOKEN: dummy-dev-token
prod SIMBOARD_API_BASE_URL [https://simboard-api.e3sm.org]: https://prod.example.test
prod SIMBOARD_API_TOKEN: dummy-prod-token
```

Verify both protected files were created:

```bash
ls -l "${SIMBOARD_ROOT}/operations/env."*.sh
```

They should both be mode `640`. Do not print these files when using real tokens.

## 4. Generate, but do not install, the cron file

```bash
make operations-init-cron site=chrysalis
```

Replace the template root with the isolated test deployment:

```bash
perl -0pi -e 's|SIMBOARD_ROOT=/path/to/simboard_root|SIMBOARD_ROOT='"${SIMBOARD_ROOT}"'|' \
  "${SIMBOARD_ROOT}/operations/chrysalis.crontab"
```

Inspect the generated commands:

```bash
grep -n "SIMBOARD_ROOT\|refresh_repository\|site_ingestion_launcher" \
  "${SIMBOARD_ROOT}/operations/chrysalis.crontab"
```

Do **not** run `crontab "${SIMBOARD_ROOT}/operations/chrysalis.crontab"` during
this test.

## 5. Test a no-op refresh

```bash
make operations-refresh
```

Expected output reports that the checkout is already current. This verifies the
refresh path does not reinstall backend dependencies when the revision is
unchanged.

On macOS, the system may not provide `flock`; the refresh reports that it is
proceeding without a process lock. This is expected for a single test run.

## 6. Test the deployed refresh helper

This exercises the same helper invoked by the cron template:

```bash
PATH="$HOME/.local/bin:$PATH" \
  "${SIMBOARD_ROOT}/repository/simboard/backend/app/scripts/ingestion/sites/operations/refresh_repository.sh"
```

Expected output again reports that the checkout is already current.

## 7. Optionally test a changed revision

Create a committed test change in the source repository, then refresh the
deployment clone:

```bash
git commit --allow-empty -m "test: verify operations refresh"
make operations-refresh
```

The refresh should fetch and check out the new revision, then synchronize the
backend runtime. Confirm both checkouts resolve to the same commit:

```bash
git rev-parse HEAD
git -C "${SIMBOARD_ROOT}/repository/simboard" rev-parse HEAD
```

Remove or otherwise handle the temporary commit according to the normal Git
workflow before pushing any branch.

## 8. Clean up

```bash
rm -rf "${TEST_ROOT}"
unset TEST_ROOT SIMBOARD_ROOT SIMBOARD_REPOSITORY_URL SIMBOARD_REPOSITORY_REF
```
