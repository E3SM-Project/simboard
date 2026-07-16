# Phase 4 Plan: Database Terminology Migration

## Task

Rename persistence objects from simulation-oriented entity names to execution
terminology after application and API code use `Execution` canonically.

## Scope

### In scope

- New Alembic migration under `backend/migrations/versions`
- `simulations` table rename to `executions`
- Child-owner foreign-key column renames from `simulation_id` to `execution_id`
- Related current constraint, index, and foreign-key names
- ORM table and column mappings, raw SQL, seed scripts, and database tests
- Upgrade and downgrade behavior

### Out of scope

- Editing historical migration files
- Renaming scientific columns such as `simulation_type`,
  `simulation_start_date`, or `simulation_end_date`
- Removing API compatibility routes or frontend redirects
- Changing execution identity or uniqueness semantics
- General schema cleanup unrelated to terminology

## Approach

1. Inventory current persistence references.
   - Use current SQLAlchemy metadata and the migration head as authoritative.
   - Identify tables that currently reference `simulations.id`, including
     artifacts and external links.
   - Identify current indexes, unique constraints, foreign keys, and raw SQL
     whose names or definitions contain entity-level simulation terminology.
   - Ignore names present only in historical migrations for columns already
     removed from the current schema.

2. Add one reversible Alembic migration.
   - Rename `simulations` to `executions` without copying or recreating rows.
   - Rename current owner columns such as `artifacts.simulation_id` and
     `external_links.simulation_id` to `execution_id`.
   - Update foreign-key targets and rename current constraints and indexes to
     execution-oriented names.
   - Preserve UUID values, timestamps, case relationships, ingestion
     relationships, cascade behavior, and uniqueness on `(case_id,
execution_id)`.
   - Provide a downgrade that reverses only this migration's changes.

3. Update ORM persistence mappings.
   - Set `Execution.__tablename__ = "executions"`.
   - Update artifact and external-link mapped columns, relationships, joins,
     ownership checks, and schema adapters to use `execution_id`.
   - Update `Case.executions`, `Ingestion.executions`, and eager-loading paths
     to point at the renamed mappings.

4. Update database-aware supporting code.
   - Update seed and rollback scripts.
   - Update raw SQL and constraint-name assertions in backend tests.
   - Update link ownership metadata so public values use `execution`, while
     Phase 3 compatibility schemas can still emit legacy `simulation` values
     where required.

5. Define deployment ordering.
   - Treat application code and migration as one coordinated deployment unless
     zero-downtime compatibility is explicitly required.
   - Run migration against a production-like database copy before deployment.
   - Do not introduce compatibility views or dual-write columns unless the
     deployment platform requires overlapping old and new application versions.

## Tests

- Add migration verification covering:
  - upgrade from the pre-rename migration head with representative cases,
    executions, artifacts, links, and ingestions
  - preserved IDs and row counts
  - preserved `(case_id, execution_id)` uniqueness
  - artifact and link foreign-key integrity
  - delete cascades
  - downgrade back to simulation-oriented persistence names
- Update model tests for `executions`, `execution_id`, relationship loading,
  and link ownership.
- Run:
  - `make backend-test`
  - `make pre-commit-run`

## Risk

- Risk score: 7
- Main failure modes:
  - Constraint or index names differ between test and deployed PostgreSQL
    databases.
  - Application and migration deploy in the wrong order.
  - Raw SQL or an operational script still references `simulations`.
  - Foreign-key or cascade behavior changes during column renames.
  - Downgrade fails after dependent objects are renamed.

## Open Questions

None. Default plan uses a coordinated migration deployment; zero-downtime
overlap requires a separate deployment constraint before implementation.
