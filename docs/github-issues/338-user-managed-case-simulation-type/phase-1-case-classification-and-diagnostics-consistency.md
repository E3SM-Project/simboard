# Phase 1 Plan: Case Classification and Diagnostics Consistency

## Task

Add a nullable, user-managed `simulation_type` to cases and display a
non-blocking warning when it differs from the tier observed in linked
diagnostics provenance.

## Scope

### In scope

- `Case.simulation_type` persistence and an Alembic migration.
- Case response and update schemas in `backend/app/features/catalog/`.
- Existing case metadata-change auditing for user edits.
- Case Details types, edit form, and display in the frontend.
- Backend-derived or API-exposed diagnostics-tier consistency information needed
  by the Case Details warning.
- Backend and frontend tests for the new behavior.

### Out of scope

- Diagnostics promotion, publishing, relocation, or deletion.
- Scanner changes that write, reject, or otherwise synchronize case simulation
  types.
- Diagnostics backfill, including updates based on existing provenance.
- Removal of the legacy execution-level field; that is Phase 2.

## Data and API Contract

1. Add `simulation_type` to `cases` as a nullable string constrained to
   `production` and `development`.
2. Define a case-specific Python type and Pydantic validation accepting the two
   values or `None` for updates. Do not import or change the execution-level
   enum for this purpose.
3. Include `simulationType` in case summary and detail responses. This makes
   the canonical value available wherever a case is rendered.
4. Add `simulationType` to `CaseUpdate`.
   - Omitted means unchanged.
   - `production` and `development` set the value.
   - `null` clears the value.
5. Let the existing update transaction snapshot and record changes to
   `simulation_type` in `MetadataChange`, including the authenticated editor
   and optional edit reason.

## Diagnostics Consistency Contract

1. Determine an observed tier only from scanner-managed
   `DiagnosticProvenanceState.archive_relative_case_path` values whose first
   segment is the validated `production` or `development` archive tier.
2. Keep the observed tier separate from `Case.simulation_type`; provenance is
   evidence for a warning, not an authority that changes the case.
3. Define response/UI states explicitly:
   - case type unset: no mismatch warning;
   - no observed diagnostics tier: no mismatch warning;
   - observed tier equals case type: indicate consistency or remain neutral;
   - observed tier differs: display a clear, non-blocking mismatch warning.
4. If a case has provenance from both tiers, expose that as ambiguous diagnostics
   evidence and show a warning only when the UI can explain the ambiguity. Do
   not choose a tier by recency and do not mutate the case.
5. Do not alter scanner request handling or its successful link/provenance
   transaction for this feature.

## Frontend Approach

1. Add a case-specific TypeScript union for `production`, `development`, and
   `null`; do not reuse the execution type.
2. Add the field to `CaseSummaryOut`, `CaseDetailOut`, and `CaseUpdate` types.
3. In Case Details, initialize editable state from the case value and include it
   in change comparison, PATCH payload construction, save reset, and cancel
   reset.
4. Render a labeled selector with Unset, Development, and Production choices
   for authorized editors. Render a readable value for non-editing users.
5. Render the diagnostics consistency warning near the case classification,
   with the case and observed diagnostics values named in the message. It must
   not disable saving or the selector.

## Tests

- Model/schema tests accept the supported values and reject all others.
- Migration tests cover upgrade and downgrade where the project migration test
  setup supports them.
- Case GET, resolve, and PATCH tests cover serialization, setting, clearing,
  authorization, no-op updates, and metadata history.
- Consistency tests cover matching, mismatched, absent, unset, and ambiguous
  provenance states without any write to `Case.simulation_type`.
- Frontend tests, where supported, cover form payloads and warning states;
  otherwise cover the behavior through type checking and focused manual UI
  verification.

## Risk

- The legacy execution field can be mistakenly reused because it shares a name.
  Mitigation: use distinct case-specific types and avoid changing execution
  behavior in this phase.
- A case can have more than one diagnostics provenance row. Mitigation: expose
  ambiguity rather than selecting an arbitrary tier.
- API consumers may need the consistency data without loading provenance
  internals. Mitigation: expose a stable, purpose-specific response field rather
  than leaking storage details.

## Validation

- `make backend-test`
- `make frontend-lint`
- `make pre-commit-run`
