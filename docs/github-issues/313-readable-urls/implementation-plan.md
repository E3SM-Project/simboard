# Issue 313: Readable Case and Execution URLs

## Goal

Replace UUID browser detail URLs with permanent, human-readable case identity
URLs:

```text
/cases/{machine}/{hpc_username}/{case_name}
/cases/{machine}/{hpc_username}/{case_name}/{execution_id}
```

The composite case identity is immutable: a new case, HPC username, or machine
identity creates a distinct record. UUIDs remain the internal primary keys for
database relationships, mutations, history, cache keys, and service APIs.

## Scope

### In

- Resolve case and execution detail pages from the immutable composite identity.
- Generate readable links everywhere the application links to case or execution
  details.
- Encode every URL path component independently.
- Remove UUID browser-detail routes; this development build has no compatibility
  requirement for them.
- Cover successful direct resolution and missing case/execution records.

### Out

- Database migration or a replacement for UUID primary keys.
- Renames, aliases, redirects, or backward compatibility for UUID browser URLs.
- Changing UUID-based mutation, history, summary, or compare service contracts.

## Implementation Phases

### Phase 1: Backend identity resolution

1. Add read-only catalog resolver endpoints for a case identity and an execution
   identity. They return the existing detail response schemas.
2. Reuse the canonical machine-name resolver and query the existing unique case
   tuple of case name, machine ID, and HPC username.
3. Resolve an execution by the matched case and its execution ID.
4. Keep UUID detail endpoints intact for internal consumers and write API tests
   for success, missing case, missing execution, and machine aliases.

### Phase 2: Frontend route identity and canonical URL helpers

1. Add catalog-owned URL helper functions that encode one path segment at a
   time and construct case/execution detail paths.
2. Replace UUID route definitions with the readable route shapes.
3. Add resolver API calls and hooks. Detail pages first resolve URL identity to
   a UUID, then continue using the UUID for existing detail, history, summary,
   mutation, and selection flows.
4. Preserve return-navigation state and make share links use the current
   canonical route.

### Phase 3: Link migration

1. Replace all case/execution detail links in catalog, browse, compare, home,
   upload, and legacy simulation redirects with the shared helpers.
2. Propagate an identity tuple where a link source currently exposes only a
   UUID. Do not add UUID URL fallbacks.
3. Remove obsolete UUID detail-link assumptions and verify links from nested
   case views and execution detail views.

### Phase 4: Verification and release readiness

1. Run backend tests, frontend linting, type checking, and repository
   pre-commit checks.
2. Verify direct navigation, browser refresh, encoded path components, and
   missing-record UI manually or in the available browser test tooling.
3. Confirm the deployed SPA serves the application entry point for nested URL
   paths.

## Acceptance Criteria

- Generated case links use `/cases/{machine}/{hpc_username}/{case_name}`.
- Generated execution links append `/{execution_id}` to the corresponding case
  URL.
- Directly loaded readable URLs resolve to the intended records.
- Every route component is encoded safely, including case and execution names
  with URL-reserved characters.
- Unknown case identities and unknown execution IDs present existing not-found
  behavior rather than loading a different record.
- Existing UUID APIs continue to support non-routing workflows.
