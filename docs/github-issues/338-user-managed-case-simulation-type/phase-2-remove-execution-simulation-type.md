# Phase 2 Plan: Remove Execution Simulation Type

## Task

Remove the obsolete execution-level `simulation_type` after the case-level
classification is deployed and confirmed as the only supported classification.

## Preconditions

- Phase 1 has deployed the case-level field and first-party clients use it.
- Product owners confirm that executions of one case do not require independent
  production/development classification.
- Known API consumers have been notified of the breaking contract removal where
  required.

## Scope

### In scope

- `Execution.simulation_type` ORM field and its database enum or constraint.
- Execution create, update, list, detail, filter-option, filter, and sorting
  contracts that expose or consume the field.
- Frontend execution forms, filters, tables, badges, comparisons, fixtures, and
  seed data that use the legacy value.
- Tests and current documentation describing execution-level simulation type.

### Out of scope

- Case-level simulation type behavior from Phase 1.
- Diagnostics consistency indicators.
- Any data backfill or inferred mapping from legacy execution values to cases.
- Diagnostics publication workflows.

## Approach

1. Inventory every backend and frontend usage of the execution field before
   editing. Classify each use as an API contract, UI presentation, filter,
   fixture, or documentation reference.
2. Remove the field from the execution ORM model, Pydantic schemas, API query
   parameters, filtering predicates, sorting validation, and filter-option
   responses.
3. Remove execution-level UI controls and presentation, including filters,
   badges, columns, comparison rows, create/edit forms, and seed fixtures.
4. Add an Alembic migration that removes the execution column and its associated
   database type or constraint. The downgrade restores only the schema; it does
   not reconstruct removed values.
5. Do not translate `unknown`, `experimental`, or `test` into a case value.
   Existing cases remain whatever users set in Phase 1, including unset.
6. Update tests and current docs so case-level classification is the sole
   supported concept.

## Tests

- Execution API tests verify requests no longer accept the removed field and
  responses/filter options no longer expose it.
- Catalog API tests verify case-level classification remains unaffected.
- Frontend tests and linting verify execution lists, details, creation, editing,
  filtering, and comparison no longer reference the removed field.
- Migration tests verify the column and associated constraint/type are removed
  on upgrade and reconstructed structurally on downgrade.

## Risk

- This is a breaking API and database change. Mitigation: do not start until the
  preconditions are met and release communication is complete.
- The field is used across catalog views and fixtures. Mitigation: inventory
  usages first and rely on type checking, API tests, and frontend linting to
  catch missed references.
- Dropping stored legacy values is irreversible. Mitigation: confirm that the
  legacy classification is not needed for reporting before applying the
  migration.

## Validation

- `make backend-test`
- `make frontend-lint`
- `make pre-commit-run`
