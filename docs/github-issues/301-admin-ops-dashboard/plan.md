# Issue #301 — Administrative operations dashboard

## Problem

Admins need one read-only page per environment that shows whether jobs run, what was ingested, and what failed. Job health (#390, #461) and ingestion summary (#364) APIs exist; rejected executions had no read API.

## Decisions

- **Site filter, not machine.** Machines at a site can share a staging directory. Job and rejection rows use the scanning job's machine, while ingestions use each execution's metadata machine, so a machine filter would split one site's data inconsistently.
- **Preset UTC date ranges** (7, 14, 30, 90 days). The summary API caps ranges at 90 days and job runs are retained 90 days.
- **Tables, no charts.** `upload_failure_daily_counts` only includes days with failures, so a table stays short and shows exact counts.
- **Status colors.** Tiles are tinted only when their count is nonzero. Running uses blue instead of the design system's in-progress amber so it stays distinct from Stale.
- **One reset.** Sections share the header filters, so only the header has "Reset filters"; empty sections say when filters explain the result.
- **Access.** The page is admin-only. The APIs keep the existing administrator and service-account access.

## Scope

### Phase 1 — Backend

- `_resolve_machine_ids` resolves optional `machine_name` and `site_name` filters to machine IDs; unknown values return 404.
- `GET /ingestions/jobs` and `GET /ingestions/summary` accept `site_name`.
- New `GET /ingestions/rejected-executions` returns up to 200 rejected `execution_discovery_results` rows and the full `total`.

### Phase 2 — Frontend shell

- `features/operations/` at `/admin/operations`, under `ProtectedRoute`; non-admins see a notice and no data requests run.
- **Operations** nav item for admins.
- URL filters: `job_type`, `site`, `range`.

### Phase 3 — Sections

- **Job health:** status tiles and table; never-reported jobs (`stale` with no report) shown separately from `stale` and `failed`.
- **Failed uploads:** latest stuck cases per job, truncation notes, and daily counts by machine and category.
- **Recent ingestions:** new executions by day, machine, and case.
- **Rejected executions:** current rejections with validation errors.
- Each section loads, refreshes, fails, and shows empty states independently.

### Phase 4 — Docs

- Dashboard and filter notes in `docs/operations/setup-ingestion-operations.md`.

## Deviations from the reference screenshot

- No percentages, failure chart, or site codes; the APIs do not provide matching data.
- Sections stack full width so wide tables stay readable.
