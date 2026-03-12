# NERSC Spin Workloads (Backend InitContainer Migrations)

This runbook defines the NERSC Spin workload baseline and backend rollout flow using an initContainer for automatic Alembic migrations.
This runbook uses the Rancher UI as the primary deployment workflow.

## Rancher UI Configs

This document is the source of truth for Spin workload settings managed in Rancher UI.
No workload manifests are versioned under `deploy/spin/`.

### Backend Deployment (`backend`)

| Rancher field              | Value                                                                                                 |
| -------------------------- | ----------------------------------------------------------------------------------------------------- |
| Workload type              | `Deployment`                                                                                          |
| Name                       | `backend`                                                                                             |
| Labels                     | `app=simboard-backend`                                                                                |
| Replicas                   | `1`                                                                                                   |
| Image pull secret          | `registry-nersc`                                                                                      |
| Init container name        | `migrate`                                                                                             |
| Init container image       | `registry.nersc.gov/e3sm/simboard/backend:<tag>`                                                      |
| Init container command     | `/app/migrate.sh`                                                                                     |
| Init container args        | leave empty                                                                                           |
| Init container script      | handled by `/app/migrate.sh` (checks `DATABASE_URL`, waits for DB, runs `alembic upgrade head`)     |
| Init envFrom secret        | `simboard-backend-env`                                                                                |
| App container name         | `backend`                                                                                             |
| App container image        | `registry.nersc.gov/e3sm/simboard/backend:<tag>`                                                      |
| App pull policy            | `Always`                                                                                              |
| App command                | leave empty (use image entrypoint)                                                                    |
| App arguments              | leave empty                                                                                           |
| Port                       | `8000/TCP`                                                                                            |
| App envFrom secret         | `simboard-backend-env`                                                                                |
| Container security context | `allowPrivilegeEscalation=false`, `privileged=false`, capabilities add `NET_BIND_SERVICE`, drop `ALL` |

Canonical init container command/args to copy into Rancher:

```sh
Command: /app/migrate.sh
Args: leave empty
```

### Backend Service (`backend`)

| Rancher field          | Value                      |
| ---------------------- | -------------------------- |
| Service type           | `ClusterIP`                |
| Service name           | `backend`                  |
| Service selector label | `app=simboard-backend`     |
| Service port           | `8000/TCP` (target `8000`) |

### Mounting NERSC E3SM Performance Archive

To mount the E3SM performance archive into backend pods, configure a bind mount in Rancher:

| Rancher field                | Value                                        |
| ---------------------------- | -------------------------------------------- |
| Scope                        | Backend Deployment (`backend`)               |
| Section                      | `Pod` -> `Storage`                           |
| Volume type                  | `Bind-Mount`                                 |
| Volume name                  | `performance-archive`                        |
| Path on node                 | `/global/cfs/cdirs/e3sm/performance_archive` |
| The Path on the Node must be | `An existing directory`                      |

Then mount that volume into the backend container (and only other containers that need it):

| Rancher field            | Value                                        |
| ------------------------ | -------------------------------------------- |
| Scope                    | Backend container (`backend`)                |
| Section                  | `Storage`                                    |
| Volume                   | `performance-archive`                        |
| Mount path (recommended) | `/performance_archive`                       |
| Read only                | `true` (recommended)                         |

Security context requirements for NERSC global file system (NGF/CFS) mounts:

- Set numeric `runAsUser` at pod/container level.
- If `runAsGroup` is set, also set `runAsUser`.
- Set `runAsGroup` and `fsGroup` to the appropriate numeric group ID.
- Keep Linux capabilities minimal (`drop: ALL`; only add what is required).

Source: [NERSC Spin Storage - NERSC Global File Systems](https://docs.nersc.gov/services/spin/storage/#nersc-global-file-systems).

### NERSC Archive Ingestion CronJob (`nersc-archive-ingestor`)

Use a Rancher-managed `CronJob` to run incremental ingestion every 15 minutes.

| Rancher field                   | Value                                                     |
| ------------------------------- | --------------------------------------------------------- |
| Workload type                   | `CronJob`                                                 |
| Name                            | `nersc-archive-ingestor`                                  |
| Schedule                        | `*/15 * * * *`                                            |
| Concurrency policy              | `Forbid`                                                  |
| Suspend                         | `false`                                                   |
| Successful jobs history limit   | `3`                                                       |
| Failed jobs history limit       | `3`                                                       |
| Job restart policy              | `OnFailure`                                               |
| Container image                 | `registry.nersc.gov/e3sm/simboard/backend:<tag>`          |
| Command                         | `python`                                                  |
| Args                            | `-m app.scripts.ingestion.nersc_archive_ingestor`         |
| Env: `SIMBOARD_API_BASE_URL`    | `http://backend:8000`                                     |
| Env: `PERF_ARCHIVE_ROOT`        | `/performance_archive`                                    |
| Env: `MACHINE_NAME`             | `perlmutter`                                              |
| Env: `STATE_PATH`               | `/var/lib/simboard-ingestion/state.json`                  |
| EnvFrom Secret                  | Secret containing `SIMBOARD_API_TOKEN`                    |
| Archive volume mount            | `performance-archive` -> `/performance_archive` (readOnly) |
| State volume mount              | writable path for state file (`/var/lib/simboard-ingestion`) |

Notes:

- Keep `SIMBOARD_API_TOKEN` in a dedicated Secret and mount as env var.
- The state volume must be writable across job runs so deduplication persists.
- Use backend service DNS (`http://backend:8000`) for in-cluster API calls.
- Non-zero CronJob exits indicate at least one case ingestion failure in that run.

#### Setup Procedure (New Ingestion Script)

1. Provision a service account token for ingestion.
   Run this from your local machine (recommended), or any trusted environment
   that can reach `https://simboard-dev-api.e3sm.org` and has `uv` available:

   ```bash
   cd backend
   uv run python -m app.scripts.users.provision_service_account \
     --service-name nersc-archive-ingestor \
     --base-url https://simboard-dev-api.e3sm.org \
     --admin-email admin@simboard.org \
     --expires-in-days 365
   ```

2. Create/update a Spin secret containing the token in the Rancher UI:
   Open Rancher and select the target namespace.
   Go to **Storage** -> **Secrets**.
   Click **Create** and set name to `simboard-ingestion-token`.
   Add key `SIMBOARD_API_TOKEN` with value `<TOKEN>`.
   Save the secret.

3. Create/update the `nersc-archive-ingestor` CronJob in Rancher using the
   configuration values listed in the table above.

4. Configure storage mounts for the CronJob pod:
   Mount the existing `performance-archive` bind mount read-only at `/performance_archive`.
   Mount a writable volume at `/var/lib/simboard-ingestion` for persistent state.

5. Validate once with a dry run before enabling schedule:
   Set `DRY_RUN=true`, run a one-off job from CronJob, and confirm logs show `scan_completed` and candidate discovery.
   Remove `DRY_RUN` (or set to `false`) after successful validation.

6. Verify operational behavior:
   Confirm job runs every 15 minutes.
   Confirm successful runs write/update `state.json` and do not repeatedly ingest unchanged cases.
   Confirm failures are visible in CronJob failed runs and `case_ingestion_failed` log events.

### Frontend Deployment (`frontend`)

| Rancher field              | Value                                                                                                                     |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Workload type              | `Deployment`                                                                                                              |
| Name                       | `frontend`                                                                                                                |
| Labels                     | `app=simboard-frontend`                                                                                                   |
| Replicas                   | `1`                                                                                                                       |
| Container name             | `frontend`                                                                                                                |
| Image                      | `registry.nersc.gov/e3sm/simboard/frontend:<tag>`                                                                         |
| Pull policy                | `Always` for `:dev`; `IfNotPresent` for versioned tags                                                                    |
| Command                    | leave empty (use image CMD)                                                                                               |
| Arguments                  | leave empty                                                                                                               |
| Port                       | `80/TCP`                                                                                                                  |
| Image pull secret          | `registry-nersc`                                                                                                          |
| Container security context | `allowPrivilegeEscalation=false`, `privileged=false`, capabilities add `CHOWN,SETGID,SETUID,NET_BIND_SERVICE`, drop `ALL` |

### Frontend Service (`frontend`)

| Rancher field          | Value                   |
| ---------------------- | ----------------------- |
| Service type           | `ClusterIP`             |
| Service name           | `frontend`              |
| Service selector label | `app=simboard-frontend` |
| Service port           | `80/TCP` (target `80`)  |

### DB Service (`db`)

| Rancher field          | Value                      |
| ---------------------- | -------------------------- |
| Service type           | `ClusterIP`                |
| Service name           | `db`                       |
| Service selector label | `app=simboard-db`          |
| Service port           | `5432/TCP` (target `5432`) |

### DB Deployment (`db`)

| Rancher field              | Value                                                                                                                        |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Workload type              | `Deployment`                                                                                                                 |
| Name                       | `db`                                                                                                                         |
| Labels                     | `app=simboard-db`                                                                                                            |
| Replicas                   | `1`                                                                                                                          |
| Container name             | `db`                                                                                                                         |
| Image                      | `postgres:17`                                                                                                                |
| Pull policy                | `Always`                                                                                                                     |
| Port                       | `5432/TCP`                                                                                                                   |
| EnvFrom secret             | `simboard-db` (includes all required DB runtime vars)                                                                        |
| Container security context | `allowPrivilegeEscalation=false`, `privileged=false`, capabilities add `CHOWN,DAC_OVERRIDE,FOWNER,SETGID,SETUID`, drop `ALL` |

### TLS Secret (`simboard-tls-cert`)

| Rancher field | Value                       |
| ------------- | --------------------------- |
| Resource type | `Secret`                    |
| Name          | `simboard-tls-cert`         |
| Secret type   | `kubernetes.io/tls`         |
| Data key      | `tls.crt` (certificate PEM) |
| Data key      | `tls.key` (private key PEM) |

### Ingress (`lb`)

| Rancher field       | Value                                                                                              |
| ------------------- | -------------------------------------------------------------------------------------------------- |
| Resource type       | `Ingress`                                                                                          |
| Name                | `lb`                                                                                               |
| Ingress class       | `nginx`                                                                                            |
| TLS secret          | `simboard-tls-cert`                                                                                |
| TLS hosts           | `simboard-dev.e3sm.org`, `simboard-dev-api.e3sm.org`, `lb.simboard.development.svc.spin.nersc.org` |
| Rule                | Host `simboard-dev.e3sm.org`, path `/`, service `frontend:80`                                      |
| Rule                | Host `simboard-dev-api.e3sm.org`, path `/`, service `backend:8000`                                 |
| Optional host alias | `lb.simboard.development.svc.spin.nersc.org`                                                       |

## Required Secrets

Create a backend env secret (example: `simboard-backend-env`) with all backend runtime vars
consumed by both app and migration init container, including:

- `ENV`, `ENVIRONMENT`, `PORT`
- `FRONTEND_ORIGIN`, `FRONTEND_AUTH_REDIRECT_URL`, `FRONTEND_ORIGINS`
- `DATABASE_URL`, `TEST_DATABASE_URL`
- `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URL`, `GITHUB_STATE_SECRET_KEY`
- `COOKIE_NAME`, `COOKIE_SECURE`, `COOKIE_HTTPONLY`, `COOKIE_SAMESITE`, `COOKIE_MAX_AGE`

Create a DB env secret (example: `simboard-db`) with DB container runtime vars, including:

- `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `POSTGRES_DB`, `POSTGRES_PORT`, `POSTGRES_SERVER`
- `PGDATA`, `PGTZ`

Create a TLS secret (example: `simboard-tls-cert`) with:

- `tls.crt`: TLS certificate in PEM format
- `tls.key`: TLS private key in PEM format

Create an ingestion token secret (example: `simboard-ingestion-token`) with:

- `SIMBOARD_API_TOKEN`: service-account bearer token used by `nersc-archive-ingestor`

## Deploy Order

1. Open the [Rancher UI](https://rancher2.spin.nersc.gov/dashboard/home) and select the target namespace.
2. Ensure DB service/deployment (`db`) are healthy in **Service Discovery → Services** and **Workloads → Deployments**.
3. Update/redeploy backend deployment with the target backend image tag.
4. Watch backend pod init container logs (`migrate`) in Rancher to confirm migration success.
5. Verify backend deployment health and pod status under **Workloads → Pods**.
6. Verify ingress routing under **Service Discovery → Ingresses** for `lb` and confirm both frontend and backend hosts resolve via HTTPS.

Frontend deploys independently from backend migration initContainer. For frontend releases, update/redeploy the `frontend` deployment in **Workloads → Deployments** with the target frontend image tag.

## Failure Handling

- If backend init container `migrate` fails, the backend pod will not become Ready.
- Fix database connectivity or migration issues, then redeploy backend.
- Backend image rollback does not revert schema automatically; handle schema rollback explicitly via Alembic when required.

## Concurrency Note

Migrations run once per new backend pod via initContainer. During a rollout, more than one backend pod can exist at the same time (for example, with multiple replicas or a RollingUpdate strategy and `maxSurge > 0`), and multiple pods can attempt migrations concurrently. If your migration safety model depends on a single migrator, configure the backend deployment to use either a **Recreate** rollout strategy or a **RollingUpdate** strategy with `maxSurge=0` (and typically `maxUnavailable=1`), or ensure your migration tooling enforces a DB-level migration lock.
