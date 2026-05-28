# CI/CD Container Builds

Audience: maintainers operating CI/CD and release image builds.

SimBoard uses GitHub Actions to build and publish frontend and backend container images to the NERSC container registry.

## Registry

```text
registry.nersc.gov/e3sm/simboard/backend
registry.nersc.gov/e3sm/simboard/frontend
```

A NERSC E3SM project robot account is provided to SimBoard administrators for automated registry access.

## GitHub Secrets

Configure these secrets in repository Actions settings:

| Secret                    | Purpose                                                  |
| ------------------------- | -------------------------------------------------------- |
| `NERSC_REGISTRY_USERNAME` | Username for `docker login registry.nersc.gov`.          |
| `NERSC_REGISTRY_PASSWORD` | Password or token for `docker login registry.nersc.gov`. |

Test locally:

```bash
docker login registry.nersc.gov
```

## Workflows

Current workflow files and exact trigger filters live under [`.github/workflows/` on GitHub](https://github.com/E3SM-Project/simboard/tree/main/.github/workflows).

| Workflow               | Trigger                                                  | Image tags                           |
| ---------------------- | -------------------------------------------------------- | ------------------------------------ |
| Backend dev build      | Push to `main` with backend changes, or manual dispatch  | `:dev`, `:sha-<commit>`              |
| Frontend dev build     | Push to `main` with frontend changes, or manual dispatch | `:dev`, `:sha-<commit>`              |
| Backend release build  | Tag matching `backend-v*`                                | `:X.Y.Z`, `:sha-<commit>`, `:latest` |
| Frontend release build | Tag matching `frontend-v*`                               | `:X.Y.Z`, `:sha-<commit>`, `:latest` |

## Build Flow

```text
Dev builds:     push to main or manual dispatch -> :dev, :sha-<short>
Release builds: component tag                   -> :X.Y.Z, :sha-<short>, :latest
```

Dev builds do not modify production images. Release builds do not modify the `:dev` image.

## Image Tagging

| Git tag           | Component | Image                                             |
| ----------------- | --------- | ------------------------------------------------- |
| `backend-vX.Y.Z`  | Backend   | `registry.nersc.gov/e3sm/simboard/backend:X.Y.Z`  |
| `frontend-vX.Y.Z` | Frontend  | `registry.nersc.gov/e3sm/simboard/frontend:X.Y.Z` |

Use full semantic versions in production for reproducibility. Use `:sha-<commit>` tags for debugging or precise rollback.

## Manual Build Verification

Trigger a manual dev build:

1. Open [GitHub Actions](https://github.com/E3SM-Project/simboard/actions).
2. Select the backend or frontend dev build workflow.
3. Click **Run workflow**.
4. Select `main`.
5. Run the workflow.

Verify images:

```bash
docker login registry.nersc.gov
docker pull registry.nersc.gov/e3sm/simboard/backend:dev
docker pull registry.nersc.gov/e3sm/simboard/frontend:dev
```

## Troubleshooting

### Authentication failure

- Verify GitHub Actions secrets are configured.
- Test the same credentials with `docker login registry.nersc.gov`.
- Confirm the account has push permissions for the `e3sm/simboard` registry namespace.

### Workflow not triggering

- Verify changes match the workflow path filters.
- Verify tags follow the component conventions: `backend-vX.Y.Z` or `frontend-vX.Y.Z`.
- Check that GitHub Actions are enabled for the repository.

### Image built but deployment did not update

CI only builds and publishes images. Deployment updates are handled separately through NERSC Spin.

See [Deployment and Release Guide](../deploy/deployment-and-release.md).

## Related Documentation

- [Deployment and Release Guide](../deploy/deployment-and-release.md)
- [NERSC Spin Runbook](../deploy/nersc-spin-runbook.md)
- [GitHub Actions](https://github.com/E3SM-Project/simboard/actions)
- [NERSC Registry](https://registry.nersc.gov/harbor/projects)
