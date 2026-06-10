# Plan: Connect zppy Diagnostics to SimBoard Simulations

## Goal

Replace manual diagnostics URL entry with automated linking from zppy diagnostics outputs to existing SimBoard simulation records.

MVP is NERSC-only.

## Scope

### In

- Add required zppy provenance fields: `case_name`, `machine`, `hpc_username`
- Add required diagnostics URLs in zppy provenance
- Require standardized zppy diagnostics output locations for NERSC production runs
- Discover zppy diagnostics provenance files from configured NERSC production filesystem roots
- Confirm diagnostics completion from index page plus status files
- Match diagnostics to SimBoard records using `(case_name, machine, hpc_username)`
- Create idempotent case-scoped diagnostic links
- Maintain scanner state to avoid repeated processing

### Out

- Frontend redesign
- Changes to manual external-link workflows
- Case identity or uniqueness refactor
- Diagnostics content ingestion or indexing
- Public HTML directory scraping
- Historical backfill beyond configured provenance roots
- Non-NERSC deployments

## Core Decisions

### Match diagnostics at case scope

zppy runs against a full case output tree, not a single execution/LID. Use case identity as the primary join key:

```text
(case_name, machine, hpc_username)
```

All three fields are required. `case_name` alone is not globally safe, and `CASE_HASH` is not reliable across executions.

### Do not parse public HTML directories

Avoid public directory scraping. It is fragile, web-server-coupled, slow, and expands the SSRF/content-injection attack surface.

### Use zppy provenance cfg as the primary input

SimBoard discovers zppy provenance files from configured NERSC filesystem roots. Newer zppy runs already emit provenance cfg files under diagnostics output paths, for example:

```text
post/scripts/provenance.20260303_230804_991619.cfg
```

Reference example:

- https://github.com/E3SM-Project/zppy/blob/main/examples/post.v3.LR.historical.zppy_v3.cfg
- https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/zppy_example/v3.2.0/v3.LR.historical_0051/provenance.20260303_230804_991619.cfg

Current cfg examples expose useful fields:

- `case`: case name
- `input`: case run directory
- `output`: diagnostics filesystem root
- `www`: public diagnostics root
- `campaign`: optional campaign metadata

But current cfg is not yet an authoritative join source because it may lack:

- `machine`
- canonical simulation owner
- unambiguous `hpc_username`

Path-derived usernames are unsafe. Example ambiguity:

```text
input  path owner: ac.wlin
output path owner: ac.zhang40
```

Therefore, zppy must enrich provenance cfg with required case identity copied from `<input>/case_scripts/env_case.xml`:

| XML field  | Provenance field |
| ---------- | ---------------- |
| `CASE`     | `case_name`      |
| `MACH`     | `machine`        |
| `REALUSER` | `hpc_username`   |

If any required field is missing, SimBoard skips the provenance file and logs it as invalid for linking.

For MVP, zppy should reuse existing top-level cfg fields rather than emit a new versioned normalized block.

### Require standardized output locations for production runs

For MVP, NERSC production runs must use standardized zppy diagnostics output locations. SimBoard relies on those known production roots for provenance discovery.

Custom or ad hoc layouts do not block the overall design, but they are not the required path for MVP.

### Require explicit diagnostics URLs in provenance

For MVP, SimBoard should not derive diagnostics URLs from path conventions. zppy should emit explicit diagnostics URLs in provenance cfg.

### Use index page plus status files as completion signal

Treat diagnostics as complete only when the expected index page and zppy status files are present.

### Persist links, do not resolve at query time

Create database rows when diagnostics are discovered. Frontend queries should not crawl filesystems or remote URLs.

Diagnostic links are case-scoped. For MVP, store them on `Case` by adding `case_id` to `ExternalLink`. Keep the existing manual-link rendering path where possible by surfacing case-scoped diagnostic links alongside current links.

## Implementation

Implement in order: provenance contract -> scanner -> storage target -> resolver/API -> frontend verification.

### zppy

#### 1. Emit required provenance fields

For MVP, production runs must write diagnostics outputs and provenance cfg files to the standardized NERSC zppy output locations.

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

- uses standardized NERSC production output locations
- emits `case_name`, `machine`, `hpc_username`
- emits explicit diagnostics URLs (`diagnostic_url`)
- can construct explicit diagnostics URLs from cfg `www` plus `mache` machine metadata
- parses values from `env_case.xml`
- parses values from `env_build.xml`
- handles missing `env_case.xml` or `env_build.xml`
- preserves existing provenance behavior

### SimBoard

#### 1. Add diagnostics scanner

Add `diagnostics_link_scanner.py`.

Responsibilities:

- scan configured NERSC production diagnostics roots for `provenance*.cfg`
- dedup with state file
- verify diagnostics completion from index page plus status files
- parse `case_name`, `machine`, `hpc_username`
- parse explicit diagnostics URLs (`diagnostic_url`)
- call internal API with service-account auth
- skip and log if full join key is unavailable

Tests:

- discovers cfgs
- parses required cfg identity
- handles malformed cfgs
- skips missing identity
- checks index-plus-status completion marker
- dedups state
- handles duplicate links idempotently

#### 2. Resolve link storage

Add `DiagnosticsLinkRequest` in `backend/app/features/simulation/schemas.py`.

For MVP, add `case_id` to `ExternalLink` and store diagnostic links at case scope.
Add a partial unique index on `(case_id, kind, url)` where `case_id IS NOT NULL` so case-owned diagnostic links remain idempotent under repeated or concurrent writes.

#### 3. Add matching resolver

| Input          | Match                   |
| -------------- | ----------------------- |
| `case_name`    | `Case.name`             |
| `machine`      | joined case simulations |
| `hpc_username` | joined case simulations |

Outcomes:

- 1 case match: create/update case-scoped links
- 0 matches: `404`
- multiple matches: `409`

Tests:

- matching triple creates links
- same case/machine under different user does not cross-link
- no match returns `404`
- ambiguous match returns `409`

#### 4. Add internal API endpoint

Endpoint: `POST /api/v1/diagnostics/link`

Implementation note:

- Define the endpoint in `backend/app/features/simulation/api.py` using a dedicated `diagnostics_router` with prefix `/diagnostics`.
- Register that router in `backend/app/main.py` with `API_BASE` so the public path remains exactly `/api/v1/diagnostics/link` instead of inheriting the `/simulations` prefix.

Roles: `ADMIN`, `SERVICE_ACCOUNT`

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
- **NERSC deployment variability**: zppy roots and public URL prefixes may still vary by campaign or user layout within NERSC.
  Mitigation: use env-configured NERSC scanner roots and NERSC public-prefix mappings.
- **Provenance drift**: cfg layout and required-field coverage may vary across zppy versions.
  Mitigation: add parser tests, schema/version detection, and a documented support window.

## Remaining Open Questions

1. **NERSC deployment scope:** Which NERSC scanner roots and public URL prefixes are supported in MVP?
2. **Retroactive linking:** Does MVP include historical backfill, or only provenance files with the required join key?
3. **Case identity hardening:** Is `(case_name, machine, hpc_username)` sufficient until issue #136 is resolved?
