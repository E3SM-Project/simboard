# NERSC Spin Workloads (Backend InitContainer Migrations)

This runbook defines the NERSC Spin workload baseline and backend rollout flow using an initContainer for automatic Alembic migrations.
This runbook uses the Rancher UI as the primary deployment workflow.

## Rancher UI Configs

This document is the source of truth for Spin workload settings managed in Rancher UI.
If a setting is not listed, leave it at Rancher defaults unless it affects
security context, networking, storage, secrets, or image pull behavior.
No workload manifests are versioned under `deploy/spin/`.

## Prerequisites (Create First)

Create these resources before configuring workloads in Rancher.
Create `simboard-ingestion-env` later in **Workload 3 setup**, after generating the ingestion service-account token.

| Secret                 | Type                | Required | Example/Allowed Value       | Used By                                           |
| ---------------------- | ------------------- | -------- | --------------------------- | ------------------------------------------------- |
| `simboard-backend-env` | `Opaque`            | Yes      | Backend runtime env vars    | `backend` app container, `migrate` init container |
| `simboard-db`          | `Opaque`            | Yes      | PostgreSQL runtime env vars | `db` container                                    |
| `simboard-tls-cert`    | `kubernetes.io/tls` | Yes      | `tls.crt`, `tls.key` (PEM)  | `lb` ingress                                      |
| `registry-nersc`       | Image pull secret   | Yes      | NERSC registry credentials  | `backend`, `frontend`, CronJob workloads          |

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

## Workload Configurations

### Workload 1: Database Deployment (`db`)

Workloads -> Deployments -> Create (top-right)

#### 1. Top-level configuration

| Rancher field | Value      |
| ------------- | ---------- |
| Namespace     | `simboard` |
| Name          | `db`       |
| Replicas      | `1`        |

#### 2. Pod tab

`Storage`:

Create a PersistentVolumeClaim volume for Postgres data.

| Rancher field                | Value                                                  |
| ---------------------------- | ------------------------------------------------------ |
| Volume type                  | `PersistentVolumeClaim`                                |
| Volume name                  | `db-data` (or your naming standard)                    |
| Persistent Volume Claim Name | `pvc-simboard-db` (or existing claim)                  |
| Access mode                  | `Single-Node Read/Write`                               |
| Capacity                     | `1Gi` minimum (or larger per policy)                   |
| Storage class                | Namespace/default class (example: `nfs-client-vast`)   |

#### 3. Container tab (`db`)

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

| Rancher field     | Value                                        |
| ----------------- | -------------------------------------------- |
| Run as User       | Required: set numeric NERSC UID (check Iris) |
| Add Capabilities  | `CHOWN,DAC_OVERRIDE,FOWNER,SETGID,SETUID`    |
| Drop Capabilities | `ALL`                                        |

`Storage`:

| Rancher field    | Value                                                             |
| ---------------- | ----------------------------------------------------------------- |
| Volume           | `db-data` (PVC volume defined in `Pod -> Storage`)               |
| Mount path       | `/var/lib/postgresql/data/pgdata`                                |
| Sub path         | leave empty (unless required by storage policy)                  |
| Read only        | `false` (required; Postgres data directory must be writable)     |

### Workload 2: Backend Deployment (`backend`)

Workloads -> Deployments -> Create (top-right)

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

| Rancher field         | Value                                                  |
| --------------------- | ------------------------------------------------------ |
| Container Name        | `backend`, Standard Container                          |
| Container Image       | `registry.nersc.gov/e3sm/simboard/backend:<tag>`       |
| Pull policy           | `Always` for `:dev`; `IfNotPresent` for versioned tags |
| Environment Variables | Type: Secret, Secret: `simboard-backend-env`           |

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
| Run as User       | Required: set numeric NERSC UID (check Iris) |
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
| Run as User              | Required: set numeric NERSC UID |
| allowPrivilegeEscalation | `false`                         |
| privileged               | `false`                         |
| capabilities             | add `DAC_OVERRIDE`, drop `ALL`  |

### Workload 3: NERSC Archive Ingestion CronJob (`nersc-archive-ingestor`)

Use a Rancher-managed `CronJob` to run incremental ingestion every 15 minutes.

Prerequisites for this section:

- Backend service must be up and reachable from within the cluster (`http://backend:8000`).
- At least one admin account must exist (see setup step 1 below).
- Ingestion service account token must be provisioned (see setup step 2 below).

#### Setup Procedure (New Ingestion Script)

1. **Create admin account (if one does not already exist)**
   - This script must run in the deployed backend environment (so it has the correct DB connection and app settings).
   - In Rancher UI, open target namespace -> **Workloads** -> **Pods** -> backend pod -> **Execute Shell** (`backend` container).
   - Run:

     ```bash
     cd /app
     python -m app.scripts.users.create_admin_account
     ```

   - Enter admin email/password when prompted.
   - Use this admin account in step 2 for service-account provisioning.

2. **Provision ingestion service-account token**
   - Service accounts are required when non-interactive systems (for example, this CronJob) authenticate to the SimBoard API.
   - Run this in the same backend pod shell opened in step 1 (no `kubectl` required).
   - Execute:

     ```bash
     cd /app
     python -m app.scripts.users.provision_service_account \
       --service-name nersc-archive-ingestor \
       --base-url http://backend:8000 \
       --admin-email <admin-email-from-step-1> \
       --expires-in-days 365
     ```

   - Enter admin password when prompted.
   - Copy the generated token immediately; it is shown once.
   - Store and rotate the token per your org policy.
   - Use this token as `SIMBOARD_API_TOKEN` in `simboard-ingestion-env` (step 3).

   Optional: quick token validation call

   ```bash
   export SIMBOARD_API_TOKEN=<TOKEN>
   curl -X POST http://backend:8000/api/v1/ingestions/from-path \
     -H "Authorization: Bearer $SIMBOARD_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
           "archive_path": "/global/cfs/cdirs/e3sm/simulations/archive.tar.gz",
           "machine_name": "perlmutter",
           "hpc_username": "<your_hpc_username>"
         }'
   ```

3. **Create/update secret `simboard-ingestion-env`**
   - In Rancher, open target namespace -> **Storage** -> **Secrets** -> **Create**.
   - Name: `simboard-ingestion-env`
   - Secret type: `Opaque`
   - Populate keys from the table below.

Key table for step 3 (`simboard-ingestion-env`):

| Key                     | Required | Example/Allowed Value                                      | Used By                  |
| ----------------------- | -------- | ---------------------------------------------------------- | ------------------------ |
| `SIMBOARD_API_TOKEN`    | Yes      | service-account bearer token (from Setup Procedure step 2) | `nersc-archive-ingestor` |
| `SIMBOARD_API_BASE_URL` | Yes      | `http://backend:8000`                                      | `nersc-archive-ingestor` |
| `PERF_ARCHIVE_ROOT`     | Yes      | `/performance_archive`                                     | `nersc-archive-ingestor` |
| `MACHINE_NAME`          | Yes      | `perlmutter`                                               | `nersc-archive-ingestor` |
| `STATE_PATH`            | Yes      | `/var/lib/simboard-ingestion/state.json`                   | `nersc-archive-ingestor` |
| `DRY_RUN`               | No       | `true` or `false`                                          | `nersc-archive-ingestor` |

4. **Create PersistentVolumeClaim (PVC) for ingestion state**
   - In Rancher, open target namespace -> **Storage** -> **PersistentVolumeClaims** -> **Create**.
   - Volume Claim settings:
     - Name: `simboard-ingestion-state`
     - Source: `Use a Storage Class to provision a new Persistent Volume`
     - Storage class: default class (or your namespace standard)
     - Request storage: `1Gi` (or larger per policy)
   - Customize:
     - Access Modes: Single Node Read/Write

5. **Create/update CronJob `nersc-archive-ingestor`**
   - Use the values in the **Configuration Reference** section below.
   - Configure secret-backed environment variables from `simboard-ingestion-env`.
   - Configure **Pod -> Storage** and **Container -> Storage** exactly as shown in the tables below (including PVC claim `simboard-ingestion-state` and state mount path).

6. **Validate once with dry run**
   - Set `DRY_RUN=true` in `simboard-ingestion-env`.
   - Trigger a one-off job from the CronJob.
   - Confirm logs include `scan_completed` and candidate discovery.
   - Remove `DRY_RUN` (or set `DRY_RUN=false`) after validation.

7. **Verify steady-state behavior**
   - Confirm the CronJob runs every 15 minutes.
   - Confirm `state.json` is written/updated and unchanged cases are not re-ingested.
   - Confirm failures appear as failed CronJob runs and `case_ingestion_failed` log events.

#### Configuration Reference

`Top-level configuration`:

| Rancher field | Value                    |
| ------------- | ------------------------ |
| Namespace     | `simboard`               |
| Name          | `nersc-archive-ingestor` |
| Schedule      | `*/15 * * * *`           |

##### 1. CronJob tab

`Scaling and Upgrade Policy`:

| Rancher field                 | Value                                          |
| ----------------------------- | ---------------------------------------------- |
| Concurrency policy            | `Skip next run if current run hasn't finished` |
| Successful jobs history limit | `3`                                            |
| Failed jobs history limit     | `3`                                            |

##### 2. Pod tab

`Security Context`:

| Rancher field        | Value   |
| -------------------- | ------- |
| Pod Filesystem Group | `62756` |

`Pod`:

| Rancher field  | Value       |
| -------------- | ----------- |
| Restart policy | `OnFailure` |

`Storage`:

| Rancher field                | Value                                          |
| ---------------------------- | ---------------------------------------------- |
| Volume type                  | `Bind-Mount`                                   |
| Volume name                  | `performance-archive`                          |
| Path on node                 | `/global/cfs/cdirs/e3sm/performance_archive`   |
| The Path on the Node must be | `An existing directory`                        |
| State volume type            | `PersistentVolumeClaim`                        |
| State volume name            | `ingestion-state`                              |
| State claim name             | `simboard-ingestion-state` (or existing claim) |

##### 3. Container tab (`nersc-archive-ingestor`)

`General`:

| Rancher field         | Value                                                  |
| --------------------- | ------------------------------------------------------ |
| Container Name        | `nersc-archive-ingestor`                               |
| Container image       | `registry.nersc.gov/e3sm/simboard/backend:<tag>`       |
| Pull policy           | `Always` for `:dev`; `IfNotPresent` for versioned tags |
| Image pull secret     | `registry-nersc`                                       |
| Command               | `python`                                               |
| Arguments             | `-m app.scripts.ingestion.nersc_archive_ingestor`      |
| Environment Variables | Type: Secret, Secret: `simboard-ingestion-env`         |

`Security Context`:

| Rancher field            | Value                                                  |
| ------------------------ | ------------------------------------------------------ |
| Run as User              | Required: set to a numeric NERSC UID for this workload |
| allowPrivilegeEscalation | `false`                                                |
| privileged               | `false`                                                |
| capabilities             | drop `ALL`                                             |

`Storage`:

| Rancher field      | Value                                                   |
| ------------------ | ------------------------------------------------------- |
| Archive volume     | `performance-archive`                                   |
| Archive mount path | `/performance_archive`                                  |
| Archive read only  | `true` (recommended)                                    |
| State volume       | `ingestion-state`                                       |
| State source claim | `simboard-ingestion-state` (through Pod volume mapping) |
| State mount path   | `/var/lib/simboard-ingestion`                           |
| State read only    | `false` (required; must be writable across runs)        |

Notes:

- Manage ingestion configuration via one Opaque secret (`simboard-ingestion-env`) and expose it as secret-backed environment variables.
- The state volume must be writable across job runs so deduplication persists.
- Use backend service DNS (`http://backend:8000`) for in-cluster API calls.
- Non-zero CronJob exits indicate at least one case ingestion failure in that run.

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

- Set numeric `Run as User` at pod/container level.
- If `Run as Group ID` is set, also set `Run as User`.
- Set `Run as Group ID` to the appropriate numeric group ID (`62756` for E3SM)
- Keep Linux capabilities minimal (`drop: ALL`; only add what is required).

Source: [NERSC Spin Storage - NERSC Global File Systems](https://docs.nersc.gov/services/spin/storage/#nersc-global-file-systems).

### Workload 4: Frontend Deployment (`frontend`)

Workloads -> Deployments -> Create (top-right)

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

## Additional Configurations

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

Service Discovery -> Ingresses -> Create

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
6. Update/redeploy frontend deployment with the target frontend image tag, then verify frontend pod status.
7. Create/confirm an admin account (Rancher pod shell), then provision ingestion service-account token and create/update secret `simboard-ingestion-env`.
8. Create PersistentVolumeClaim `simboard-ingestion-state` for CronJob state.
9. Create/update CronJob `nersc-archive-ingestor`, run a one-off dry run (`DRY_RUN=true`), then set `DRY_RUN=false`.
10. Verify ingress routing under **Service Discovery → Ingresses** for `lb` and confirm both frontend and backend hosts resolve via HTTPS.

## Failure Handling

- If backend init container `migrate` fails, the backend pod will not become Ready.
- Fix database connectivity or migration issues, then redeploy backend.
- Backend image rollback does not revert schema automatically; handle schema rollback explicitly via Alembic when required.

## Concurrency Note

Migrations run once per new backend pod via initContainer. During a rollout, more than one backend pod can exist at the same time (for example, with multiple replicas or a RollingUpdate strategy and `maxSurge > 0`), and multiple pods can attempt migrations concurrently. If your migration safety model depends on a single migrator, configure the backend deployment to use either a **Recreate** rollout strategy or a **RollingUpdate** strategy with `maxSurge=0` (and typically `maxUnavailable=1`), or ensure your migration tooling enforces a DB-level migration lock.
