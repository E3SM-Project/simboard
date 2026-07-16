# Phase 2 Plan: Backend Domain Model

## Task

Rename the backend's case child domain object from `Simulation` to `Execution`
without changing database object names or public API contracts. Keep scientific
simulation fields and CIME run fields unchanged.

## Scope

### In scope

- ORM class and relationship names in `backend/app/features/simulation/models.py`
- Pydantic class names in `backend/app/features/simulation/schemas.py`
- Backend service, ingestion, PACE, assistant, seed, and test symbols that refer
  to the child entity
- Execution-oriented status naming where status belongs to the child entity
- Compatibility aliases needed to keep current API payloads unchanged

### Out of scope

- Renaming the `simulations` database table or `simulation_id` columns
- Adding `/api/v1/executions`
- Changing JSON field names such as `simulations` or `totalSimulations`
- Changing frontend TypeScript contracts or browser routes
- Moving the existing `backend/app/features/simulation` package
- Renaming scientific fields or types that still describe simulation metadata

## Approach

1. Rename the ORM domain class.
   - Rename `Simulation` to `Execution`.
   - Keep `Execution.__tablename__ = "simulations"` during this phase.
   - Rename Python relationships to `Case.executions` and
     `Ingestion.executions` while preserving their current database joins.
   - Rename entity-oriented local variables, function names, type annotations,
     docstrings, and log messages.

2. Separate entity names from scientific properties.
   - Rename schema classes such as `SimulationCreate`, `SimulationUpdate`,
     `SimulationOut`, and page/list variants to `Execution*`.
   - Rename `SimulationStatus` to `ExecutionStatus` if its values describe the
     collected execution result.
   - Retain `SimulationType`, `simulation_type`, `simulation_start_date`, and
     `simulation_end_date`; these describe scientific simulation metadata.
   - Retain `run_start_date` and `run_end_date`; these describe the CIME run
     interval.

3. Update backend consumers.
   - Update `backend/app/features/ingestion` parsing, mapping, duplicate
     detection, persistence, and result internals to use execution terminology.
   - Update `backend/app/features/pace` lookup internals.
   - Update `backend/app/features/assistant` snapshots, services, and
     orchestrator internals while preserving current external endpoint and
     citation-path contracts.
   - Update seed and rollback scripts to use `Execution` symbols.

4. Preserve public compatibility explicitly.
   - Keep current `/api/v1/simulations` routes and OpenAPI-visible payload
     fields unchanged.
   - Use response adapters or legacy response schemas where renamed internal
     relationships would otherwise emit `executions`.
   - Keep ingestion response field `simulations` and assistant citation root
     `simulation.*` until Phase 3.
   - Avoid permanent duplicate model classes; compatibility aliases must be
     marked for removal in Phase 5.

5. Keep feature-package movement deferred.
   - Leave imports under `app.features.simulation` so this phase remains an
     internal domain rename rather than a package-layout refactor.
   - Record remaining legacy package names in Phase 5 cleanup scope.

## Tests

- Update backend model and schema tests for `Execution` classes and
  `Case.executions` relationships.
- Update ingestion tests for creation, duplicate detection, case grouping, and
  response compatibility.
- Update PACE and assistant tests to use execution-oriented internals while
  proving current external payloads stay unchanged.
- Add API regression assertions for:
  - `/api/v1/simulations` remaining available
  - case payloads still exposing `simulations`
  - ingestion responses still exposing `simulations`
  - assistant citations still accepting `simulation.*`
- Run:
  - `make backend-test`
  - `make pre-commit-run`

## Risk

- Risk score: 5
- Main failure modes:
  - ORM relationship renames introduce broken eager-load paths or backrefs.
  - Compatibility adapters accidentally change current JSON payloads.
  - Broad search-and-replace changes valid scientific simulation fields.
  - Assistant citation paths drift before the canonical API is available.

## Open Questions

None.
