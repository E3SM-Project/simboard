# SimBoard Backend

The backend is a FastAPI service that ingests simulation archives, stores normalized metadata in PostgreSQL, and exposes the `/api/v1` REST API used by the frontend and service-account tooling.

## Responsibilities

- archive ingestion and validation
- case, execution, machine, and ingestion persistence
- GitHub OAuth and API-token authentication
- managed-content authorization for human editors and service accounts
- PACE execution lookup
- API schemas and routing

## Important Locations

```text
backend/app/main.py                 FastAPI app and router registration
backend/app/features/ingestion/     ingestion endpoints and parser integration
backend/app/features/catalog/       cases, executions, schemas, delta logic
backend/app/features/machine/       machine models and API
backend/app/features/user/          auth, tokens, user models
backend/app/core/                   config, DB setup, exceptions, logging
backend/migrations/                 Alembic migrations
backend/tests/                      pytest coverage
```

## Developer Commands

Run these from the repo root:

```bash
make backend-run
make backend-test
make backend-migrate m='message'
make backend-upgrade
```

## Single-Execution Ingestion

From the repository root, select an existing absolute execution directory beneath
the configured archive root (or staging root with `scan_mode=staging`):

```bash
make ingest-dry-run machine=perlmutter env=dev scan_mode=archive \
    env_file="$HOME/.config/simboard/env.dev.sh" \
    execution_dir="/global/cfs/cdirs/e3sm/OLD_PERF/2026-10/performance_archive_2026_10_12_10_02_55/COMPLETED/mahf708/E1.baseline.pm-gpu.r04/59694792.261011-211434"
```

Use `ingest-apply` instead of `ingest-dry-run` after reviewing discovery results.
The selected environment file determines the API destination. The runner uses
`backend/.venv/bin/python` unless `PYTHON_BIN` overrides it.

Only the selected execution is discovered and submitted; sibling executions are
excluded. Normal scan layout restrictions and archive date bounds still apply.
Targeted runs bypass completed snapshot checkpoints but never mark a snapshot
complete. Existing execution-state and API
duplicate checks remain active: this is not force-reingestion or metadata overwrite.
Dry runs perform discovery without writes; they do not exercise server-side parsing
and persistence. Invalid selections fail instead of falling back to a broad scan.

Directory selection works with both machine runners. For Chrysalis, use
`machine=chrysalis SIMBOARD_ROOT=<deployment-root>` and a directory beneath its
configured source root; the existing upload transport and deployment setup apply.

## Ingested Simulation Dates

Execution simulation dates use `Curr Time` and `Stop Time` from the initial
driver clock in `cpl.log.<execution_id>` (plain or gzipped). `Stop Time` is the
configured simulation end; termination timestamps do not override it. These
dates are separate from the wall-clock run timestamps supplied by CaseStatus.

Without usable coupler dates, non-continuation runs retain the XML-derived
fallback. For `CONTINUE_RUN=TRUE`, XML initialization dates do not describe the
execution interval and are not used. If the simulation start remains unknown,
ingestion reports a per-execution date validation error without creating the
execution. A missing simulation end may remain null. Missing coupler logs do
not themselves fail required-file validation.

Existing executions are still skipped as duplicates; correcting previously
stored dates is a separate backfill operation.

## Configuration

Backend env templates live in `.envs/example/backend.env.example`. Local developer values live in `.envs/local/backend.env`.

Restart the backend after changing local env values.

For repo-wide setup, assistant LLM configuration, and contributor workflow, see [docs/developer/index.md](../docs/developer/index.md).

## Authorization Notes

- Authenticated read access to executions remains broad.
- Managed content edits must reuse `app.features.user.manager.can_edit_managed_content`.
- Policy shape: `admin` always allowed, `user` allowed only with verified E3SM GitHub org membership, `service_account` denied for human UI-managed edits.
- Routes that enforce this policy should preserve `401` for unauthenticated requests and return `403` for authenticated users who lack edit permission.
