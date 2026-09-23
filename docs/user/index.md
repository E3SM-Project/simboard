# SimBoard User Guide

SimBoard is a public catalog of E3SM simulation cases and their executions.
Use it to find work by case, machine, or HPC user; inspect the metadata and
artifacts associated with an execution; and compare selected executions.

## Start with the catalog

Open the **Cases** page to search and filter the catalog. Each case groups its
related executions, making it easier to move from a high-level case record to
the specific execution you need. Open a case to review its execution history,
then select an execution for its metadata, artifacts, and available external
links.

Use the comparison controls on the catalog and execution pages to collect
executions and review them side by side. Direct URLs preserve the catalog
context, so they can be shared with collaborators.

## Get data into SimBoard

Most catalog data arrives through automated collection from supported HPC
environments. The catalog reflects the data that has been ingested, so search
for a case before preparing a manual upload.

When an archive is not yet available through automated collection, use the
browser **Upload** page to submit a compressed E3SM performance case archive.
The upload is validated before ingestion; an archive containing an incomplete
or invalid execution is rejected without ingesting any of its executions.

For available environments, historical-data coverage, and manual-upload
details, see [Ingestion Coverage and Manual Upload](ingestion-coverage.md).

## Publish diagnostics links

SimBoard can link a catalog case to published zppy diagnostics output. Follow
the [diagnostics publishing guide](diagnostics.md) to configure zppy, prepare
the expected archive layout, and troubleshoot missing or incorrect links.

## Need help?

For missing cases, archive-range requests, or ingestion questions, contact the
SimBoard administrator: [Tom Vo](mailto:vo13@llnl.gov).
