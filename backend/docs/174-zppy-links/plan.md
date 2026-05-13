# Plan: Connect zppy Diagnostics to SimBoard Simulations

## Task

Replace manual diagnostic URL-pasting with automated, metadata-based linking of zppy diagnostics outputs to SimBoard simulation records.

## Scope

**In:** matching strategy (`case_name` + `machine` + `hpc_username`), persistence model, discovery mechanism, zppy manifest spec.
**Out:** frontend UI redesign, PACE changes, existing manual link workflow, Case uniqueness refactor (issue #136), diagnostics data ingestion (Phase 2+).

## Key Decisions

### Do NOT parse public HTML directories

- **Fragility** — HTML layouts vary by web server; breaks on config changes.
- **Security** — SSRF and content-injection attack surface.
- **Coupling** — SimBoard depends on external web server availability/structure.
- **Latency** — Network crawling is slow and unreliable for production.

### zppy writes a manifest file (no API call)

zppy runs as a user-level Python package on HPC machines. SimBoard's API requires `SERVICE_ACCOUNT` or `ADMIN` bearer tokens — it is not feasible for each user to obtain and configure an API token in zppy.

**Instead, zppy writes a small manifest file to a well-known location within its output directory.** This requires zero authentication, zero network access from zppy, and trivial zppy-side changes.

```jsonc
// <zppy_output_dir>/.simboard-diagnostics.json
{
  "case_name": "v3.LR.historical_0201",
  "machine": "chrysalis",
  "hpc_username": "user123",
  "diagnostics": [
    {
      "kind": "e3sm_diags",
      "url": "https://web.lcrc.anl.gov/...",
      "label": "E3SM Diags",
    },
    {
      "kind": "mpas_analysis",
      "url": "https://web.lcrc.anl.gov/...",
      "label": "MPAS-Analysis",
    },
  ],
}
```

zppy already knows `case_name`, `machine`, and the running user from its cfg. `mache` resolves machine-specific public web URL prefixes to construct the URLs.

### SimBoard discovers manifests via filesystem scanning (not API push)

SimBoard already has a CronJob-based filesystem scanner (`nersc_archive_ingestor.py`) that:

- Walks mounted HPC directories every 15 min
- Uses state-based incremental dedup
- Authenticates with a single service account token
- Calls `POST /ingestions/from-path` internally

The diagnostics linking should follow the same pattern: a SimBoard-side scanner discovers `.simboard-diagnostics.json` manifests, reads them, matches to existing Cases, and creates `ExternalLink` rows. **No per-user tokens needed.**

### Persist links in database (not query-time resolution)

Store `ExternalLink` rows on match. No remote calls during frontend queries. Same model as manually-added links — frontend works with zero changes. `ExternalLink.created_at` provides audit trail.

## Approach

1. **Join key:** `(case_name, machine, hpc_username)` — all three required. `case_name` alone is not globally unique (`Case.name` has a unique index but different users can reuse names). Adding `machine` + `hpc_username` disambiguates. `CASE_HASH` is unreliable across executions (see issue #136). zppy has all three values.

2. **Matching query:** Machine is on `Simulation` not `Case`, so the resolver joins: `Case.name == X AND Simulation.machine_id == Y AND Simulation.hpc_username == Z`. All simulations in a case share the same machine in practice.

3. **zppy-side (minimal change):** After diagnostics complete, zppy writes `.simboard-diagnostics.json` to its output directory. `mache` resolves public URL prefixes. No API call, no token.

4. **SimBoard diagnostics scanner** — two options:

   **Option A — Extend NERSC archive ingestor (recommended for MVP):** Add a post-scan phase to the existing `nersc_archive_ingestor.py` that also walks known diagnostics output directories (or the same archive tree) looking for `.simboard-diagnostics.json` files. On discovery, it calls a new internal endpoint or directly creates `ExternalLink` rows via the existing service account token.

   **Option B — Separate diagnostics scanner script:** A new lightweight CronJob script (`diagnostics_link_scanner.py`) that walks diagnostics output directories. Same pattern as `nersc_archive_ingestor.py` — env-configured, state-file dedup, service account auth. Better separation of concerns, but more operational overhead.

5. **API endpoint** (extend `backend/app/features/simulation/api.py`):

   ```
   POST /api/v1/diagnostics/link
   Body: { "case_name": "...", "machine": "...", "hpc_username": "...", "diagnostics": [...] }
   ```

   Restricted to `ADMIN` / `SERVICE_ACCOUNT` roles (same as ingestion). Resolves the triple → `Case` → creates `ExternalLink` rows with `kind = diagnostic`. The scanner calls this endpoint; users don't call it directly.

6. **Schema:** Add `DiagnosticsLinkRequest` to `backend/app/features/simulation/schemas.py`.

7. **Migration:** None if linking to existing FK targets. Required if adding `case_id` FK to `ExternalLink` (see open question #1).

8. **Frontend:** No changes. Existing `grouped_links` rendering picks up new diagnostic links automatically.

### Alternative: Convention-based URL derivation (no zppy changes)

For production runs with enforced path conventions, SimBoard could derive diagnostic URLs from simulation metadata + `mache` without any zppy changes or manifest files. Per issue #174, zppy outputs follow a fixed directory structure and `mache` resolves per-machine URL prefixes.

This works only when path conventions are strict. The manifest approach is more robust for custom user paths. Could combine both: derive URLs for production campaigns, manifest for custom runs.

## Tests

- `backend/tests/features/simulation/test_api.py` — endpoint tests:
  - Happy path: matching `(case_name, machine, hpc_username)` → links created
  - Different user, same case_name + machine → no cross-linking (isolation test)
  - No matching case → 404
  - Duplicate link idempotency
  - Invalid payload → 422
- Scanner tests: manifest discovery, state dedup, malformed manifest handling
- Run: `make backend-test && make pre-commit-run`

## Risk

**Score: 3 (normal)**

1. **zppy adoption lag** — No data until zppy emits manifests. Mitigate with convention-based derivation for production runs.
2. **Case name collision** — `Case.name` is unique in DB but not globally meaningful. The `(case_name, machine, hpc_username)` triple mitigates. Broader fix tracked in issue #136.
3. **Diagnostics output path visibility** — Scanner must have filesystem access to zppy output directories. On NERSC this requires mounting the relevant CFS paths into the SimBoard container (same pattern as performance archive).
4. **Timing gap** — Scanner-based approach has up to 15-min latency. Acceptable for diagnostics linking.

## Open Questions (ask colleagues)

1. **Case-level vs execution-level linking?** zppy diagnostics run across simulation output in time increments — they're inherently case-scoped, not tied to a specific execution/LID. Current `ExternalLink` only has `simulation_id` FK. Options: (a) add optional `case_id` FK to `ExternalLink`, (b) create a separate `CaseLink` model, (c) link to reference simulation only as a pragmatic shortcut. This is the key schema decision.
2. **Case uniqueness long-term?** The `(case_name, machine, hpc_username)` triple is a pragmatic join key but `Case.name` as the sole DB unique constraint is fragile. Issue #136 is evaluating `CASE_HASH` but it's unstable across executions. Should Case uniqueness be strengthened in the model itself?
3. **Diagnostics output directory location?** Where are zppy outputs stored on each machine? Need the path pattern to configure the scanner. Per issue #174, the coupled group stores results on machine web servers — need the exact filesystem mount paths for NERSC (and other machines if applicable).
4. **Retroactive linking needed?** If yes, plan a one-time bulk-linking script (or convention-based derivation) for existing diagnostics that predate this feature.
5. **Convention-based derivation viable for MVP?** If zppy output paths are predictable enough from `(case_name, machine, hpc_username)` + `mache`, SimBoard could derive diagnostic URLs without any zppy changes. Worth evaluating as a faster MVP path.
