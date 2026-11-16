# Site Ingestion Assets

This directory contains the host-side entrypoint and the assets it uses to run
remote-site ingestion jobs.

| Location | Responsibility |
| --- | --- |
| `site_ingestion_launcher.sh` | Stable scheduler entrypoint. Loads one reviewed site config and starts the configured Python ingestor. |
| `configs/` | Reviewed site-specific defaults such as archive roots, machine name, ingestor module, and archive lower bound. Never store tokens or deployment paths here. |
| `templates/` | Committed templates for deployment-local API environment files and scheduler crontabs. |
| `operations/` | Helpers used by the `make ops-*` targets to provision or refresh a checkout and create protected environment files, plus weekly launcher-log archiving. |
| `diagnostics/` | Wrappers for diagnostics operations that are separate from performance ingestion. |

`SIMBOARD_ROOT`, API tokens, and installed crontabs are deployment-local. The
standard operations workspace separates `raw_logs/`, `history_logs/`, and
`quality_assurance/`; see the repository's
`docs/operations/setup-ingestion-operations.md` guide for provisioning, migration,
retention, and scheduler instructions.

Set `SIMBOARD_INGESTION_LOG_LEVEL=DEBUG` for execution detail (INFO is the
default). INFO/DEBUG jobs emit canonical run metrics for future aggregation.
See [Ingestion Logging](../../../../../docs/architecture/ingestion-logging.md)
for the authoritative terminology, logging contract, and
early launcher failure capture.

`operations/archive_ingestion_logs.py` archives completed launcher logs from
`raw_logs/` into Sunday–Saturday UTC `.tar.gz` files in `history_logs/`. It
inherits cron's `DRY_RUN` setting and removes sources only after verifying the
archive. Summarization is a separate API task, not part of this utility.
