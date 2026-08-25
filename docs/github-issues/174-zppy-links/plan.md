# Plan: Connect zppy Diagnostics to SimBoard Simulations

## Goal

Replace manual diagnostics URL entry with automated linking from zppy diagnostics outputs to existing SimBoard simulation records.

MVP uses SimBoard's static diagnostics-archive registry for supported machines.

## Scope

### In

- Add required zppy provenance fields: `case_name`, `machine`, `hpc_username`
- Add required diagnostics URLs in zppy provenance
- Require standardized zppy diagnostics archive locations for supported machines
- Discover newest paired zppy provenance from the static archive registry
- Require published diagnostic output before linking
- Match diagnostics to SimBoard records using `(case_name, machine, hpc_username)`
- Create idempotent case-scoped diagnostic links
- Maintain database-backed scanner provenance state

### Out

- Frontend redesign
- Changes to manual external-link workflows
- Case identity or uniqueness refactor
- Diagnostics content ingestion or indexing
- Public HTML directory scraping
- Historical backfill beyond configured provenance roots
- Mache runtime/config retrieval

## Core Decisions

### Match diagnostics at case scope

zppy runs against a full case output tree, not a single execution/LID. Use case identity as the primary join key:

```text
(case_name, machine, hpc_username)
```

All three fields are required. `case_name` alone is not globally safe, and `CASE_HASH` is not reliable across executions.

### Do not parse public HTML directories

Avoid public directory scraping. It is fragile, web-server-coupled, slow, and expands the SSRF/content-injection attack surface.

### Use paired zppy provenance files

SimBoard discovers timestamped paired provenance files from the filesystem roots
selected by its static site registry. The cfg establishes that a matching
provenance pair exists; the paired settings file is the authoritative source of
case identity and diagnostics URL. For example:

```text
post/scripts/provenance.20260303_230804_991619.cfg
```

Reference example:

- https://github.com/E3SM-Project/zppy/blob/main/examples/post.v3.LR.historical.zppy_v3.cfg
- https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/zppy_example/v3.2.0/v3.LR.historical_0051/provenance.20260303_230804_991619.cfg

Current cfg examples expose useful contextual fields:

- `case`: case name
- `input`: case run directory
- `output`: diagnostics filesystem root
- `www`: public diagnostics root
- `campaign`: optional campaign metadata

The cfg is not an authoritative join source because it may lack:

- `machine`
- canonical simulation owner
- unambiguous `hpc_username`

Path-derived usernames are unsafe. Example ambiguity:

```text
input  path owner: ac.wlin
output path owner: ac.zhang40
```

Therefore, zppy must write required case identity to provenance settings, copied
from `<input>/case_scripts/env_case.xml`:

| XML field  | Provenance field |
| ---------- | ---------------- |
| `CASE`     | `case_name`      |
| `MACH`     | `machine`        |
| `REALUSER` | `hpc_username`   |

If any required field is missing, SimBoard skips the provenance pair and logs it
as invalid for linking. Settings also provide the explicit `diagnostics_url`.

SimBoard selects the newest complete cfg/settings pair by parsed filename
timestamp and does not fall back to older provenance when the newest pair is
incomplete.

### Require standardized archive locations

SimBoard keeps a checked-in `DIAGNOSTICS_ARCHIVES_BY_MACHINE` registry under
`backend/app/scripts/ingestion/`. Each entry supplies the complete filesystem
archive root and matching public archive URL for a supported SimBoard machine.
The registry is seeded or refreshed during development from Mache machine cfg
files, but the scanner never fetches or parses Mache at runtime.

Custom or ad hoc layouts are not part of this MVP.

### Require explicit diagnostics URLs in provenance

For MVP, SimBoard should not derive diagnostics URLs from path conventions. zppy
should emit an explicit `diagnostics_url` in provenance settings. SimBoard
validates that URL against the configured public archive prefix.

### Use published output as readiness signal

Treat a candidate as ready when its published case directory contains a
non-provenance diagnostic artifact or non-empty diagnostic subdirectory. Do not
inspect zppy status files: they are not published archive artifacts and do not
reliably identify one provenance run. This is a published-output readiness
check, not proof every zppy task has completed.

### Persist links, do not resolve at query time

Create database rows when diagnostics are discovered. Frontend queries should not crawl filesystems or remote URLs.

Diagnostic links are case-scoped. Store scanner state centrally with each
scanner-managed link, keyed by canonical machine and archive-relative case path.
State is removed when its linked `ExternalLink` is deleted, allowing a later
scan to recreate a still-published link.

## Implementation

Implement in order: provenance contract -> storage/API state -> scanner ->
frontend verification.

### zppy

#### 1. Emit required provenance fields

For MVP, runs must write diagnostics outputs and paired provenance
cfg/settings files to the standardized site diagnostics archive.

| Field          | Source                    |
| -------------- | ------------------------- |
| `case_name`    | `env_case.xml` `CASE`     |
| `machine`      | `env_case.xml` `MACH`     |
| `hpc_username` | `env_case.xml` `REALUSER` |

Implementation note:

- For NERSC MVP, zppy can construct explicit diagnostics URLs from cfg `www` plus `mache` machine metadata.
- `mache.MachineInfo` exposes helpers such as `web_portal_base`, `web_portal_url`, and `username`.
- Reference: https://docs.e3sm.org/mache/main/developers_guide/generated/mache.MachineInfo.html

Tests:

- uses standardized diagnostics archive locations
- emits `case_name`, `machine`, `hpc_username`
- emits explicit diagnostics URLs (`diagnostics_url`)
- can construct explicit diagnostics URLs from cfg `www` plus `mache` machine metadata
- parses values from `env_case.xml`
- parses values from `env_build.xml`
- handles missing `env_case.xml` or `env_build.xml`
- preserves existing provenance behavior

### SimBoard

#### 1. Add diagnostics scanner and static site registry

Add `diagnostics_link_scanner.py`.

Responsibilities:

- add a checked-in machine-to-archive registry under `scripts/ingestion`, seeded
  or refreshed from Mache cfg files during development only
- select a registry entry by accepted SimBoard machine name or alias; reject an
  unsupported machine before scanning
- scan bounded production and development archive trees, including optional
  case-group directories, without following symlinks outside the archive root
- select newest paired cfg/settings provenance by parsed filename timestamp
- parse identity and `diagnostics_url` only from settings; validate settings
  syntax, archive layout, and URL scheme/authority/path boundary
- require published diagnostic output beyond provenance files; do not inspect
  zppy status files
- read database-backed provenance state and skip an unchanged successful
  settings filename/fingerprint
- call the scanner-specific internal diagnostics endpoint with service-account
  auth, leaving `POST /api/v1/diagnostics/link` unchanged
- skip and log malformed, output-not-ready, or non-matching candidates

Tests:

- selects static archive registry entries by canonical machine name and alias
- rejects unsupported machines and invalid registry roots or public URLs
- generates registry candidates from representative Mache cfg files while
  skipping files without usable `[web_portal]` values
- discovers grouped and ungrouped cases in both archive classifications
- selects the newest paired provenance without stale fallback
- parses required settings identity and URL without parsing cfg identity
- handles malformed or unsafe provenance
- skips missing identity
- checks published output and provenance-only directories without status files
- retries transient submissions and dedups central successful state
- handles duplicate links idempotently

#### 2. Resolve link storage and scanner state

Use the existing diagnostics-link request schema in
`backend/app/features/catalog/schemas.py`.

Use the existing case-owned `ExternalLink` storage and partial uniqueness on
`(case_id, kind, url)` so repeated or concurrent submissions remain idempotent.

Add `DiagnosticProvenanceState` for each scanner-managed diagnostic link. Store
the canonical machine, normalized archive-relative case path, settings filename,
timestamp, fingerprint, URL, and successful submission time. Give the state row
a unique foreign key to `ExternalLink` with cascade deletion, and add a unique
machine/path constraint.

#### 3. Add matching resolver

| Input          | Match                   |
| -------------- | ----------------------- |
| `case_name`    | `Case.name`             |
| `machine`      | resolved `Case.machine_id` |
| `hpc_username` | `Case.hpc_username`     |

Outcomes:

- 1 case match: create/update case-scoped links
- 0 matches: `404`
- case uniqueness makes multiple matches invalid

Tests:

- matching triple creates links
- same case/machine under different user does not cross-link
- no match returns `404`
- case uniqueness prevents ambiguous matches

#### 4. Add internal diagnostics APIs

Endpoint: `POST /api/v1/diagnostics/link`

Implementation note:

- Define the endpoint in `backend/app/features/catalog/api.py` using a dedicated `diagnostics_router` with prefix `/diagnostics`.
- Register that router in `backend/app/main.py` with `API_BASE` so the public path remains exactly `/api/v1/diagnostics/link` instead of inheriting the `/simulations` prefix.

Roles: `ADMIN`, `SERVICE_ACCOUNT`

Keep this endpoint's contract unchanged. Add scanner-specific state read and
link endpoints for service accounts. The scanner link endpoint accepts existing
diagnostics-link identity plus provenance metadata and atomically upserts the
case link and `DiagnosticProvenanceState` in one transaction.

Request:

| Field          | Required |
| -------------- | -------- |
| `case_name`    | yes      |
| `machine`      | yes      |
| `hpc_username` | yes      |
| `diagnostics`  | yes      |

Diagnostics item:

| Field               | Required |
| ------------------- | -------- |
| `name`              | yes      |
| `url`               | yes      |
| `kind = diagnostic` | yes      |

Tests:

- duplicate request is idempotent
- concurrent duplicate request is idempotent
- invalid payload returns `422`
- auth required
- scanner state lookup skips unchanged successful provenance
- scanner link submission atomically persists link and state
- concurrent scanner submissions remain safe
- deleting a scanner-managed link cascades state deletion

#### 5. Keep frontend unchanged

Existing external-link rendering should display diagnostic links once rows exist.

## Fallbacks

### Curated backfill

Allow convention-based URL derivation only for controlled campaigns. Do not use as the primary MVP path.

### Validation command

```bash
make backend-test && make pre-commit-run
```

## Risks

- **Case-scoped link migration**: diagnostics are case-scoped, but `ExternalLink` currently points at `simulation_id`.
  Mitigation: add `case_id` for MVP and keep migration/API behavior narrow.
- **Missing identity**: SimBoard cannot link a provenance file without `case_name`, `machine`, and `hpc_username`.
  Mitigation: require zppy provenance enrichment; skip and log invalid files.
- **Static registry drift**: a site may move its published archive.
  Mitigation: refresh the checked-in registry through a reviewed SimBoard change.
- **Provenance drift**: cfg layout and required-field coverage may vary across zppy versions.
  Mitigation: add parser tests, schema/version detection, and a documented support window.

## Remaining Open Questions

1. **Retroactive linking:** Does MVP include historical backfill, or only provenance files with the required join key?
2. **Case identity hardening:** Is `(case_name, machine, hpc_username)` sufficient until issue #136 is resolved?
