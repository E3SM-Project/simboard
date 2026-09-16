# Operational Scripts

This directory contains internal operational entry points. This page covers
ingestion and diagnostics; use `make help` for database-management and
account-provisioning commands. Run Python scripts as modules from the backend
project root:

```bash
uv run python -m app.scripts.ingestion.nersc_archive_ingestor
uv run python -m app.scripts.ingestion.hpc_upload_archive_ingestor
uv run python -m app.scripts.ingestion.diagnostics_link_scanner
```

Do not execute Python scripts directly by file path; module execution preserves
package imports and application configuration.

## Ingestion Operations

The step-by-step setup, site configuration, cron, environment-variable, targeted
E3SM v3 backfill, and diagnostics instructions are maintained in
[Set Up an Ingestion Workflow](../../../docs/deploy/setup-ingestion-workflow.md).

Use the runner selected by archive access:

| Archive location | Runner |
| --- | --- |
| Mounted in the SimBoard backend environment | `nersc_archive_ingestor.py` |
| Available only at a remote HPC site | `hpc_upload_archive_ingestor.py` via `sites/site_ingestion_launcher.sh` |

For service-account and API-token provisioning, see
[HPC API Token Authentication](../../../docs/deploy/hpc-api-token-authentication.md).
