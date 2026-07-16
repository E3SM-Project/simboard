# Phase 1 Plan: Terminology Contract and UI Labels

## Task

Define `Case -> Execution` as SimBoard's canonical object hierarchy and make the
frontend use **Execution** for the child entity. Preserve **run**, **job**, and
**simulation** only where they describe distinct CIME or scientific concepts.

## Scope

### In scope

- Terminology guidance in `docs/architecture/metadata-ingestion.md`
- Supporting overview language in `README.md` and developer documentation
- User-visible entity labels in `frontend/src`
- Frontend wording checks needed to prevent mixed entity labels

### Out of scope

- Backend Python symbol renames
- API paths or response-field changes
- Frontend TypeScript type, hook, component, or route renames
- Database table, column, constraint, or index changes
- Renaming legitimate fields such as `simulation_type`,
  `simulation_start_date`, `run_start_date`, or `run_end_date`

## Terminology Contract

| Term       | Meaning                                                                                                                               |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Case       | Top-level CIME case identity represented by one SimBoard `Case`.                                                                      |
| Execution  | One case child identified by an execution ID derived from a CIME LID.                                                                 |
| Run        | An action or time interval, including CIME `case.run`, a runner invocation, and run start/end timestamps. Not a SimBoard entity name. |
| Job        | A scheduler or CIME workflow job. It is not assumed to map one-to-one to an execution.                                                |
| Simulation | Scientific model configuration or simulated time metadata. It is not the name of the case child entity.                               |

## Approach

1. Add the terminology contract to
   `docs/architecture/metadata-ingestion.md`.
   - State the hierarchy as `Case -> Execution`.
   - Define execution identity as the case-scoped execution ID/LID.
   - Explain why `run`, `job`, and `simulation` remain valid in narrower
     contexts.

2. Align repository overview prose.
   - Update `README.md`, `docs/developer/README.md`, `backend/README.md`, and
     `docs/backend/README.md` only where they use **run** or **simulation** as
     the child entity name.
   - Do not replace verbs, CIME command names, scheduler terminology, or
     scientific metadata terms mechanically.

3. Standardize frontend entity labels.
   - Replace headings and navigation labels such as **Runs**, **Simulations**,
     **All Simulations**, and **Case Runs** with **Executions**.
   - Cover home, browse, case details, execution details, compare, upload
     results, navigation, empty states, errors, and breadcrumbs.
   - Keep labels such as **Run start**, **Run end**, and literal `case.run`.

4. Keep this phase contract-neutral.
   - Do not change `/simulations` URLs, API payload fields, TypeScript symbol
     names, or query keys yet.
   - Treat temporary mismatch between visible labels and internal names as an
     intentional migration stage resolved by later phases.

## Tests

- Add or update existing frontend assertions for changed labels where test
  coverage already exists.
- Search rendered frontend source for entity-level uses of `Run`, `Runs`,
  `Simulation`, and `Simulations`; review matches manually against the
  terminology contract.
- Run:
  - `make frontend-lint`
  - `pnpm --dir frontend run type-check`
  - `make pre-commit-run`

## Risk

- Risk score: 2
- Main failure modes:
  - Mechanical replacement changes valid CIME or scientific wording.
  - Less-visible empty states or errors retain mixed entity labels.
  - Documentation describes later API or database phases as already complete.

## Open Questions

None.
