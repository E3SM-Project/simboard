# Plan: Link E3SM v3 Cases to HPSS Archives

## Goal

Connect existing Chrysalis E3SM v3 cases to their documented long-term HPSS
archive locations, while making the existing execution archive terminology clear
in the UI.

## Scope

- Expand the targeted v3 archive backfill to include all documented v3 case
  entries before HPSS reconciliation.
- Fetch the E3SM v3 simulation table and map its `Simulation` values to HPSS
  URLs.
- Match existing Chrysalis and Perlmutter cases by normalized case name and
  retain their stored HPC usernames.
- Idempotently create or update a case-owned `Long-Term Archive` external link.
- Relabel existing execution `Archive` artifacts as `Short-Term Archive` in the
  frontend without changing the persisted artifact kind.

## Design

The HPSS URL describes a case-level, long-term data location, so it is stored as
an `other` external link on `Case`, rather than as an execution artifact. Case
links are already visible from every execution belonging to that case.

The linker is a standalone, dry-run-first script run in the deployed backend
container or an administrative job. It is intentionally separate from archive
ingestion: the documentation table is curated metadata and is not part of
filesystem archive discovery.

## Implementation

1. Add `lcrc_v3_hpss_linker.py`, which fetches (or reads a saved copy of) the
   v3 simulation table, extracts Simulation-to-HPSS URL mappings, and normalizes
   grouped Simulation values to their leaf case names.
2. Expand the targeted Chrysalis v3 archive catalog with the documented RRM,
   ensemble, and symlinked NARRM entries, then run its dry-run reconciliation
   before linking. Keep the Perlmutter-owned `v3.LR.amip_bonus_0101` in its
   normal Perlmutter ingestion workflow.
3. Query existing `chrysalis` and `perlmutter` cases and reconcile matching case
   names. The
   script never derives or changes `hpc_username`.
4. Default to dry run. With `--apply`, create missing managed links, leave
   matching links unchanged, and update one existing managed link when its URL
   changes. Report ambiguous managed links and conflicting documentation mappings
   without guessing. Treat the documentation-only `LR_ensemble` and
   `RRM_ensemble` rows as explicit exceptions while their resolution is tracked
   in [issue #323](https://github.com/E3SM-Project/simboard/issues/323).
5. Add tests for document parsing, normalization, reconciliation, idempotency,
   and dry-run behavior.
6. Update frontend labels to `Short-Term Archive` and adjust inherited-link copy
   to describe general case-level links.

## Verification

Run backend tests, frontend linting, and pre-commit. Before applying against a
shared database, run the linker in dry-run mode and review matched, unmatched,
conflicting, and ambiguous records.
