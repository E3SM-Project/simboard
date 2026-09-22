# Ingestion Coverage and Manual Upload

SimBoard normally receives E3SM performance metadata through automated ingestion
from supported HPC environments. Use the Cases page to check whether a case is
already available before submitting an archive manually.

## Automated HPC ingestion

Automated collection has separate paths for current performance output and
historical archive data. The standard remote-site scheduler configuration scans
current performance output every 15 minutes and historical archive snapshots
daily. Site operators can adjust schedules and archive date bounds, so the
available coverage varies by configured environment.

Historical archive scans use configurable inclusive lower and upper bounds in
`YYYY` or `YYYY-MM` form. Refer to the configured environment and the catalog
itself for the current coverage of a particular machine or case.

## E3SM v3 historical data

SimBoard includes a targeted E3SM v3 historical-data ingestion process for
Chrysalis archives. It matches the documented E3SM v3 simulation set and scans
from January 2024 onward. This is a targeted backfill rather than a guarantee
that every v3 case is present or that new v3 data appears immediately.

Search the Cases page to confirm whether a particular v3 case is available.

## Manual case upload

Use the browser Upload page when a compressed E3SM performance case archive is
not yet available through automated ingestion, or when a direct ad hoc archive
submission is appropriate. A case archive can contain one or more execution
directories. The browser also accepts a directly packaged single execution
directory when needed.

The browser validates the archive before ingestion. If any execution directory
is incomplete or invalid, the archive is rejected and no executions are
ingested.

## Questions about coverage

For a missing case, a requested archive range, or questions about ingestion
status, contact the SimBoard administrator: [Tom Vo](mailto:vo13@llnl.gov).
