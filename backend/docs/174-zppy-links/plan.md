# Plan: Connect zppy Diagnostics to SimBoard Simulations

## Goal

Replace manual diagnostics URL entry with automated linking from zppy diagnostics outputs to existing SimBoard simulation records.

## Scope

### In

- Add required zppy provenance fields: `case_name`, `machine`, `hpc_username`
- Discover zppy diagnostics provenance files from configured filesystem roots
- Confirm diagnostics completion before linking
- Match diagnostics to SimBoard records using `(case_name, machine, hpc_username)`
- Create idempotent diagnostic `ExternalLink` rows
- Maintain scanner state to avoid repeated processing

### Out

- Frontend redesign
- Changes to manual external-link workflows
- PACE integration changes
- Case identity or uniqueness refactor
- Diagnostics content ingestion or indexing
- Public HTML directory scraping
- Historical backfill beyond configured provenance roots
- Optional build/campaign metadata ingestion

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

Do not require zppy to call the SimBoard API. zppy runs as a user-level HPC package, while SimBoard API writes require `SERVICE_ACCOUNT` or `ADMIN` tokens.

Instead, SimBoard discovers zppy provenance files from configured filesystem roots. Newer zppy runs already emit provenance cfg files under diagnostics output paths, for example:

```text
post/scripts/provenance.20260303_230804_991619.cfg
```

Current cfg examples expose useful fields:

- `case`: case name
- `input`: case run directory
- `output`: diagnostics filesystem root
- `www`: public diagnostics root
- `campaign`: optional campaign metadata

But current cfg is not yet an authoritative join source because it may lack:

- `machine`
- execution `LID`
- canonical simulation owner
- unambiguous `hpc_username`

Path-derived usernames are unsafe. Example ambiguity:

```text
input  path owner: ac.wlin
output path owner: ac.zhang40
```

Therefore, zppy must enrich provenance cfg with required case identity copied from `case_scripts/env_case.xml`:

| XML field  | Provenance field |
| ---------- | ---------------- |
| `CASE`     | `case_name`      |
| `MACH`     | `machine`        |
| `REALUSER` | `hpc_username`   |

If any required field is missing, SimBoard skips the provenance file and logs it as invalid for linking.

### Persist links, do not resolve at query time

Create database rows when diagnostics are discovered. Frontend queries should not crawl filesystems or remote URLs.

Use the existing manual-link rendering path where possible: diagnostics links become `ExternalLink` rows with `kind = diagnostic`.

## Implementation

Implement in order: provenance contract -> scanner -> storage target -> resolver/API -> frontend verification.

### zppy

#### 1. Emit required provenance fields

| Field          | Source                    |
| -------------- | ------------------------- |
| `case_name`    | `env_case.xml` `CASE`     |
| `machine`      | `env_case.xml` `MACH`     |
| `hpc_username` | `env_case.xml` `REALUSER` |

Tests:

- emits `case_name`, `machine`, `hpc_username`
- parses values from `env_case.xml`
- handles missing `env_case.xml`
- preserves existing provenance behavior

### SimBoard

#### 1. Add diagnostics scanner

Add `diagnostics_link_scanner.py`.

Responsibilities:

- scan configured diagnostics roots for `provenance*.cfg`
- dedup with state file
- verify diagnostics completion
- parse `case_name`, `machine`, `hpc_username`
- call internal API with service-account auth
- skip and log if full join key is unavailable

Tests:

- discovers cfgs
- parses required cfg identity
- handles malformed cfgs
- skips missing identity
- checks completion marker
- dedups state
- handles duplicate links idempotently

#### 2. Resolve link storage

Add `DiagnosticsLinkRequest` in `backend/app/features/simulation/schemas.py`.

Storage options:

1. Preferred: add `case_id` to `ExternalLink`.
2. Alternative: add `CaseLink`.
3. Shortcut: attach to reference simulation.

#### 3. Add matching resolver

| Input          | Match                     |
| -------------- | ------------------------- |
| `case_name`    | `Case.name`               |
| `machine`      | `Simulation.machine_id`   |
| `hpc_username` | `Simulation.hpc_username` |

Outcomes:

- 1 match: create/update links
- 0 matches: `404`
- multiple matches: `409`

Tests:

- matching triple creates links
- same case/machine under different user does not cross-link
- no match returns `404`
- ambiguous match returns `409`

#### 4. Add internal API endpoint

Endpoint: `POST /api/v1/diagnostics/link`

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

- **Storage gap**: diagnostics are case-scoped, but `ExternalLink` currently points at `simulation_id`.
  Mitigation: decide storage target before implementing resolver/API behavior.
- **Missing identity**: SimBoard cannot link a provenance file without `case_name`, `machine`, and `hpc_username`.
  Mitigation: require zppy provenance enrichment; skip and log invalid files.
- **Deployment variability**: zppy roots and public URL prefixes vary by machine/campaign.
  Mitigation: use env-configured scanner roots and machine/public-prefix mappings.
- **Provenance drift**: cfg layout and required-field coverage may vary across zppy versions.
  Mitigation: add parser tests, schema/version detection, and a documented support window.

## Remaining Open Questions

1. **Storage target:** Should diagnostics links attach to `Case`, `Simulation`, or a new link table?
2. **Provenance schema:** Should zppy emit a versioned normalized block or reuse existing top-level cfg fields?
3. **Completion signal:** Which artifact should SimBoard treat as authoritative completion: status file, generated index, or explicit provenance field?
4. **Deployment scope:** Which scanner roots, machines, and public URL prefixes are supported in MVP?
5. **Retroactive linking:** Does MVP include historical backfill, or only provenance files with the required join key?
6. **Case identity hardening:** Is `(case_name, machine, hpc_username)` sufficient until issue #136 is resolved?
