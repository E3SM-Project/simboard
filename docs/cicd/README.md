# CI/CD Container Builds

Audience: maintainers operating CI/CD and release image builds.

SimBoard uses GitHub Actions to build and publish frontend and backend container images to the GitHub Container Registry.

## Registry

```text
ghcr.io/e3sm-project/simboard/backend
ghcr.io/e3sm-project/simboard/frontend
```

Authentication uses the built-in `GITHUB_TOKEN` — no additional secrets are required for registry access.

## GitHub Secrets

No registry secrets are required. Authentication to `ghcr.io` is handled automatically via the built-in `GITHUB_TOKEN` with `packages: write` permission granted in each workflow.

Test locally:

```bash
docker login ghcr.io
# Use your GitHub username and a personal access token with `write:packages` scope
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

| Git tag           | Component | Image                                               |
| ----------------- | --------- | --------------------------------------------------- |
| `backend-vX.Y.Z`  | Backend   | `ghcr.io/e3sm-project/simboard/backend:X.Y.Z`       |
| `frontend-vX.Y.Z` | Frontend  | `ghcr.io/e3sm-project/simboard/frontend:X.Y.Z`      |

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
docker login ghcr.io
docker pull ghcr.io/e3sm-project/simboard/backend:dev
docker pull ghcr.io/e3sm-project/simboard/frontend:dev
```

## Troubleshooting

### Authentication failure

- Ensure the workflow has `packages: write` permission (already set in all build workflows).
- For local pulls, use a GitHub personal access token with `read:packages` scope.

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
- [GitHub Container Registry](https://ghcr.io)
