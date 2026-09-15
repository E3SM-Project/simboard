# Plan: Remove Legacy Execution Simulation Type

## Scope

Remove the obsolete execution-level simulation classification while preserving
the user-managed `Case.simulationType` introduced in #338.

## Implementation

1. Remove the field from the execution ORM model, creation and update schemas,
   list/detail response schemas, filtering, sorting, and filter-option APIs.
2. Stop ingestion from deriving or persisting execution simulation types and
   remove assistant snapshot and summary references to that field.
3. Remove execution-specific frontend types, filters, table columns, badges,
   detail controls, comparison rows, and seed fixture values.
4. Add a reversible structural migration that drops the execution column on
   upgrade and restores its legacy schema with an `unknown` default on
   downgrade. It deliberately does not restore discarded values.
5. Update API, schema, ingestion, assistant, migration, and frontend coverage
   to reject the legacy request field and verify case classification is intact.

## Validation

Run `make backend-test`, `make frontend-lint`, and `make pre-commit-run`.
