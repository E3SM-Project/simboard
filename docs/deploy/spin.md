# NERSC Spin Workloads (Backend InitContainer Migrations)

This runbook defines the NERSC Spin workload baseline and backend rollout flow using an initContainer for automatic Alembic migrations.
This runbook uses the Rancher UI as the primary deployment workflow.

## Rancher UI Configs

This document is the source of truth for Spin workload settings managed in Rancher UI.
No workload manifests are versioned under `deploy/spin/`.

## Prerequisites (Create First)

Create these resources before configuring workloads in Rancher.

| Secret                   | Type                | Required | Example/Allowed Value       | Used By                                           |
| ------------------------ | ------------------- | -------- | --------------------------- | ------------------------------------------------- |
| `simboard-backend-env`   | `Opaque`            | Yes      | Backend runtime env vars    | `backend` app container, `migrate` init container |
| `simboard-db`            | `Opaque`            | Yes      | PostgreSQL runtime env vars | `db` container                                    |
| `simboard-ingestion-env` | `Opaque`            | Yes      | Ingestor runtime env vars   | `nersc-archive-ingestor` container                |
| `simboard-tls-cert`      | `kubernetes.io/tls` | Yes      | `tls.crt`, `tls.key` (PEM)  | `lb` ingress                                      |
| `registry-nersc`         | Image pull secret   | Yes      | NERSC registry credentials  | `backend`, `frontend`, CronJob workloads          |

Environment variable keys:

`simboard-backend-env`:

| Key                          | Required | Example/Allowed Value                  | Used By              |
| ---------------------------- | -------- | -------------------------------------- | -------------------- |
| `ENV`                        | Yes      | `development`, `staging`, `production` | `backend`, `migrate` |
| `ENVIRONMENT`                | Yes      | `local`, `dev`, `prod`                 | `backend`, `migrate` |
| `PORT`                       | Yes      | `8000`                                 | `backend`, `migrate` |
| `FRONTEND_ORIGIN`            | Yes      | frontend origin URL                    | `backend`, `migrate` |
| `FRONTEND_AUTH_REDIRECT_URL` | Yes      | frontend auth callback URL             | `backend`, `migrate` |
| `FRONTEND_ORIGINS`           | Yes      | comma-separated origins                | `backend`, `migrate` |
| `DATABASE_URL`               | Yes      | Postgres SQLAlchemy URL                | `backend`, `migrate` |
| `TEST_DATABASE_URL`          | Yes      | test Postgres URL                      | `backend`, `migrate` |
| `GITHUB_CLIENT_ID`           | Yes      | GitHub OAuth client id                 | `backend`, `migrate` |
| `GITHUB_CLIENT_SECRET`       | Yes      | GitHub OAuth client secret             | `backend`, `migrate` |
| `GITHUB_REDIRECT_URL`        | Yes      | backend OAuth callback URL             | `backend`, `migrate` |
| `GITHUB_STATE_SECRET_KEY`    | Yes      | random secret string                   | `backend`, `migrate` |
| `COOKIE_NAME`                | Yes      | cookie name                            | `backend`, `migrate` |
| `COOKIE_SECURE`              | Yes      | `true` or `false`                      | `backend`, `migrate` |
| `COOKIE_HTTPONLY`            | Yes      | `true` or `false`                      | `backend`, `migrate` |
| `COOKIE_SAMESITE`            | Yes      | `lax`, `strict`, `none`                | `backend`, `migrate` |
| `COOKIE_MAX_AGE`             | Yes      | seconds as integer                     | `backend`, `migrate` |

`simboard-db`:

| Key                 | Required | Example/Allowed Value | Used By |
| ------------------- | -------- | --------------------- | ------- |
| `POSTGRES_USER`     | Yes      | DB username           | `db`    |
| `POSTGRES_PASSWORD` | Yes      | DB password           | `db`    |
| `POSTGRES_DB`       | Yes      | DB name               | `db`    |
| `POSTGRES_PORT`     | Yes      | `5432`                | `db`    |
| `POSTGRES_SERVER`   | Yes      | `db`                  | `db`    |
| `PGDATA`            | Yes      | Postgres data dir     | `db`    |
| `PGTZ`              | Yes      | timezone string       | `db`    |

`simboard-ingestion-env`:

| Key                     | Required | Example/Allowed Value                    | Used By                  |
| ----------------------- | -------- | ---------------------------------------- | ------------------------ |
| `SIMBOARD_API_TOKEN`    | Yes      | service-account bearer token             | `nersc-archive-ingestor` |
| `SIMBOARD_API_BASE_URL` | Yes      | `http://backend:8000`                    | `nersc-archive-ingestor` |
| `PERF_ARCHIVE_ROOT`     | Yes      | `/performance_archive`                   | `nersc-archive-ingestor` |
| `MACHINE_NAME`          | Yes      | `perlmutter`                             | `nersc-archive-ingestor` |
| `STATE_PATH`            | Yes      | `/var/lib/simboard-ingestion/state.json` | `nersc-archive-ingestor` |
| `DRY_RUN`               | No       | `true` or `false`                        | `nersc-archive-ingestor` |

### Backend Deployment (`backend`)

#### Top-level configuration

| Rancher field     | Value                  |
| ----------------- | ---------------------- |
| Workload type     | `Deployment`           |
| Name              | `backend`              |
| Labels            | `app=simboard-backend` |
| Replicas          | `1`                    |
| Image pull secret | `registry-nersc`       |

#### 1. Pod tab

`Security Context`:

| Rancher field        | Value   |
| -------------------- | ------- |
| Pod Filesystem Group | `62756` |

Required for NERSC global file system (NGF/CFS) mounts to ensure correct permissions for the backend container user.

`Storage`:

| Rancher field                | Value                                        |
| ---------------------------- | -------------------------------------------- |
| Volume type                  | `Bind-Mount`                                 |
| Volume name                  | `performance-archive`                        |
| Path on node                 | `/global/cfs/cdirs/e3sm/performance_archive` |
| The Path on the Node must be | `An existing directory`                      |

#### 2. Container tab (`backend`)

`General`:

| Rancher field         | Value                                            |
| --------------------- | ------------------------------------------------ |
| Container Name        | `backend`, Standard Container                    |
| Container Image       | `registry.nersc.gov/e3sm/simboard/backend:<tag>` |
| Pull policy           | `Always`                                         |
| Environment Variables | Type: Secret, Secret: `simboard-backend-env`     |

`General -> Networking`:

| Rancher field          | Value       |
| ---------------------- | ----------- |
| Service type           | `ClusterIP` |
| Name                   | `backend`   |
| Private Container Port | `8000`      |
| Protocol               | `TCP`       |

`Security Context`:

| Rancher field     | Value                                        |
| ----------------- | -------------------------------------------- |
| Run as User ID    | Required: set numeric NERSC UID (check Iris) |
| Add Capabilities  | leave empty                                  |
| Drop Capabilities | `ALL`                                        |

`Storage`:

| Rancher field | Value                  |
| ------------- | ---------------------- |
| Volume        | `performance-archive`  |
| Mount path    | `/performance_archive` |
| Read only     | `true` (recommended)   |

#### 3. Container tab (`migrate`, init container)

`General`:

| Rancher field         | Value                                                                              |
| --------------------- | ---------------------------------------------------------------------------------- |
| Container type        | Init container                                                                     |
| Name                  | `migrate`                                                                          |
| Container image       | `registry.nersc.gov/e3sm/simboard/backend:<tag>`                                   |
| Command               | `/app/migrate.sh`                                                                  |
| Args                  | leave empty                                                                        |
| Environment Variables | Type: Secret, Secret: `simboard-backend-env`                                       |
| Script behavior       | `/app/migrate.sh` checks `DATABASE_URL`, waits for DB, runs `alembic upgrade head` |

`Security Context`:

| Rancher field            | Value                           |
| ------------------------ | ------------------------------- |
| Run as User ID           | Required: set numeric NERSC UID |
| allowPrivilegeEscalation | `false`                         |
| privileged               | `false`                         |
| capabilities             | add `DAC_OVERRIDE`, drop `ALL`  |

### NERSC Archive Ingestion CronJob (`nersc-archive-ingestor`)

Use a Rancher-managed `CronJob` to run incremental ingestion every 15 minutes.

#### 1. CronJob tab

`Top-level configuration`:

| Rancher field                 | Value                                          |
| ----------------------------- | ---------------------------------------------- |
| Namespace                     | `simboard`                                     |
| Name                          | `nersc-archive-ingestor`                       |
| Schedule                      | `*/15 * * * *`                                 |
| Concurrency policy            | `Skip next run if current run hasn't finished` |
| Successful jobs history limit | `3`                                            |
| Failed jobs history limit     | `3`                                            |

#### 2. Pod tab

`Security Context`:

| Rancher field        | Value   |
| -------------------- | ------- |
| Pod Filesystem Group | `62756` |

`Pod`:

| Rancher field                | Value                                                  |
| ---------------------------- | ------------------------------------------------------ |
| Restart policy               | `OnFailure`                                            |
| Run as User ID               | Required: set to a numeric NERSC UID for this workload |
| Volume type                  | `Bind-Mount`                                           |
| Volume name                  | `performance-archive`                                  |
| Path on node                 | `/global/cfs/cdirs/e3sm/performance_archive`           |
| The Path on the Node must be | `An existing directory`                                |
| State volume                 | Writable volume for `/var/lib/simboard-ingestion`      |

#### 3. Container tab (`nersc-archive-ingestor`)

`General`:

| Rancher field         | Value                                             |
| --------------------- | ------------------------------------------------- |
| Container Name        | `nersc-archive-ingestor`                          |
| Container image       | `registry.nersc.gov/e3sm/simboard/backend:<tag>`  |
| Image pull policy     | `IfNotPresent`                                    |
| Command               | `python`                                          |
| Arguments             | `-m app.scripts.ingestion.nersc_archive_ingestor` |
| Environment Variables | Type: Secret, Secret: `simboard-ingestion-env`    |

`Security Context`:

| Rancher field            | Value      |
| ------------------------ | ---------- |
| allowPrivilegeEscalation | `false`    |
| privileged               | `false`    |
| capabilities             | drop `ALL` |

`Storage`:

| Rancher field | Value                         |
| ------------- | ----------------------------- |
| Volume        | `performance-archive`         |
| Mount path    | `/performance_archive`        |
| Read only     | `true` (recommended)          |
| State mount   | `/var/lib/simboard-ingestion` |

Notes:

- Manage ingestion configuration via one Opaque secret (`simboard-ingestion-env`) and expose it as secret-backed environment variables.
- The state volume must be writable across job runs so deduplication persists.
- Use backend service DNS (`http://backend:8000`) for in-cluster API calls.
- Non-zero CronJob exits indicate at least one case ingestion failure in that run.

#### Setup Procedure (New Ingestion Script)

1. Provision a service account token for ingestion.
   Run this from your local machine (recommended), or any trusted environment
   with `uv` and network access to the target SimBoard API base URL:

   ```bash
   cd backend
   uv run python -m app.scripts.users.provision_service_account \
     --service-name nersc-archive-ingestor \
     --base-url <simboard-api-base-url> \
     --admin-email <admin-email> \
     --expires-in-days 365
   ```

   Example (dev environment):
   `--base-url https://simboard-dev-api.e3sm.org`

2. Create/update an Opaque Spin secret for ingestor env vars in the Rancher UI:
   Open Rancher and select the target namespace.
   Go to **Storage** -> **Secrets**.
   Click **Create** and set name to `simboard-ingestion-env`.
   Set secret type to **Opaque**.
   Add these keys:
   `SIMBOARD_API_TOKEN=<TOKEN>`
   `SIMBOARD_API_BASE_URL=http://backend:8000`
   `PERF_ARCHIVE_ROOT=/performance_archive`
   `MACHINE_NAME=perlmutter`
   `STATE_PATH=/var/lib/simboard-ingestion/state.json`
   `DRY_RUN=true|false` (optional)
   Save the secret.

3. Create/update the `nersc-archive-ingestor` CronJob in Rancher using the
   configuration values listed in the table above, including secret-backed
   environment variables from `simboard-ingestion-env`.

4. Configure storage mounts for the CronJob pod:
   Mount the existing `performance-archive` bind mount read-only at `/performance_archive`.
   Mount a writable volume at `/var/lib/simboard-ingestion` for persistent state.

5. Validate once with a dry run before enabling schedule:
   Add `DRY_RUN=true` to the `simboard-ingestion-env` secret, run a one-off job
   from CronJob, and confirm logs show `scan_completed` and candidate discovery.
   Remove `DRY_RUN` (or set to `false`) in the secret after successful validation.

6. Verify operational behavior:
   Confirm job runs every 15 minutes.
   Confirm successful runs write/update `state.json` and do not repeatedly ingest unchanged cases.
   Confirm failures are visible in CronJob failed runs and `case_ingestion_failed` log events.

### Mounting NERSC E3SM Performance Archive

Canonical values for all workloads that mount the E3SM performance archive:
These values should already be set in the instructions above, but are repeated here for
clarity and to highlight security context requirements.

| Field                   | Value                                        |
| ----------------------- | -------------------------------------------- |
| Path on node            | `/global/cfs/cdirs/e3sm/performance_archive` |
| Volume name             | `performance-archive`                        |
| In-container mount path | `/performance_archive`                       |
| Read only               | `true` (recommended for archive mounts)      |

Security context requirements for NERSC global file system (NGF/CFS) mounts:

- Set numeric `Run as User ID` at pod/container level.
- If `Run as Group ID` is set, also set `Run as User ID`.
- Set `Run as Group ID` to the appropriate numeric group ID (`62756` for E3SM)
- Keep Linux capabilities minimal (`drop: ALL`; only add what is required).

Source: [NERSC Spin Storage - NERSC Global File Systems](https://docs.nersc.gov/services/spin/storage/#nersc-global-file-systems).

### Frontend Deployment (`frontend`)

#### 1. Top-level configuration

| Rancher field     | Value                   |
| ----------------- | ----------------------- |
| Workload type     | `Deployment`            |
| Name              | `frontend`              |
| Labels            | `app=simboard-frontend` |
| Replicas          | `1`                     |
| Image pull secret | `registry-nersc`        |

#### 2. Container tab (`frontend`)

`General`:

| Rancher field   | Value                                                  |
| --------------- | ------------------------------------------------------ |
| Container image | `registry.nersc.gov/e3sm/simboard/frontend:<tag>`      |
| Pull policy     | `Always` for `:dev`; `IfNotPresent` for versioned tags |
| Port            | `80/TCP`                                               |

`General -> Networking`:

| Rancher field          | Value       |
| ---------------------- | ----------- |
| Service type           | `ClusterIP` |
| Name                   | `frontend`  |
| Private Container Port | `80`        |
| Protocol               | `TCP`       |

`Security Context`:

| Rancher field     | Value                                  |
| ----------------- | -------------------------------------- |
| Add Capabilities  | `CHOWN,SETGID,SETUID,NET_BIND_SERVICE` |
| Drop Capabilities | `ALL`                                  |

### DB Deployment (`db`)

#### 1. Top-level configuration

| Rancher field | Value      |
| ------------- | ---------- |
| Namespace     | `simboard` |
| Name          | `db`       |
| Replicas      | `1`        |

#### 2. Container tab (`db`)

`General`:

| Rancher field         | Value                                 |
| --------------------- | ------------------------------------- |
| Container Name        | `db`                                  |
| Container image       | `postgres:17`                         |
| Pull policy           | `Always`                              |
| Environment Variables | Type: `Secret`, Secret: `simboard-db` |

`General -> Networking`:

| Rancher field          | Value       |
| ---------------------- | ----------- |
| Service type           | `ClusterIP` |
| Name                   | `db`        |
| Private Container Port | `5432`      |
| Protocol               | `TCP`       |

`Security Context`:

| Rancher field              | Value                                                                                                                        |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Container security context | `allowPrivilegeEscalation=false`, `privileged=false`, capabilities add `CHOWN,DAC_OVERRIDE,FOWNER,SETGID,SETUID`, drop `ALL` |

### TLS Secret (`simboard-tls-cert`)

#### General tab

| Rancher field | Value               |
| ------------- | ------------------- |
| Resource type | `Secret`            |
| Name          | `simboard-tls-cert` |
| Secret type   | `kubernetes.io/tls` |

#### Data tab

| Rancher field | Value                       |
| ------------- | --------------------------- |
| Data key      | `tls.crt` (certificate PEM) |
| Data key      | `tls.key` (private key PEM) |

### Ingress (`lb`)

#### General tab

| Rancher field | Value     |
| ------------- | --------- |
| Resource type | `Ingress` |
| Name          | `lb`      |
| Ingress class | `nginx`   |

#### TLS tab

| Rancher field | Value                                                                                              |
| ------------- | -------------------------------------------------------------------------------------------------- |
| TLS secret    | `simboard-tls-cert`                                                                                |
| TLS hosts     | `simboard-dev.e3sm.org`, `simboard-dev-api.e3sm.org`, `lb.simboard.development.svc.spin.nersc.org` |

#### Rules tab

| Rancher field       | Value                                                              |
| ------------------- | ------------------------------------------------------------------ |
| Rule                | Host `simboard-dev.e3sm.org`, path `/`, service `frontend:80`      |
| Rule                | Host `simboard-dev-api.e3sm.org`, path `/`, service `backend:8000` |
| Optional host alias | `lb.simboard.development.svc.spin.nersc.org`                       |

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
