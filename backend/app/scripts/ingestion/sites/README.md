# Site Ingestion Assets

This directory contains the host-side entrypoint and the assets it uses to run
remote-site ingestion jobs.

| Location | Responsibility |
| --- | --- |
| `site_ingestion_launcher.sh` | Stable scheduler entrypoint. Loads one reviewed site config and starts the configured Python ingestor. |
| `configs/` | Reviewed site-specific defaults such as archive roots, machine name, ingestor module, and archive lower bound. Never store tokens or deployment paths here. |
| `templates/` | Committed templates for deployment-local API environment files and scheduler crontabs. |
| `operations/` | Helpers used by the `make operations-*` targets to provision or refresh a checkout and create protected environment files. |
| `diagnostics/` | Wrappers for diagnostics operations that are separate from performance ingestion. |

`SIMBOARD_ROOT`, API tokens, and installed crontabs are deployment-local. See
the repository's `docs/deploy/setup-ingestion-operations.md` guide for
provisioning and scheduler instructions.
