# Issue 330: Support zppy Diagnostics Archive Layout

## Goal

Update SimBoard diagnostics discovery to support the path contract introduced by
[zppy PR 868](https://github.com/E3SM-Project/zppy/pull/868): one authoritative,
unnested production directory per case, and development directories nested by
the publishing HPC username.

## zppy Publishing Contract

For inferred zppy `www` paths, the scanner must recognize these layouts below
the configured `diagnostics_archive` root:

| Tier | Ungrouped case | CASE_GROUP case |
| --- | --- | --- |
| `production` | `production/<case_name>` | `production/<case_group>/<case_name>` |
| `development` | `development/<username>/<case_name>` | `development/<case_group>/<username>/<case_name>` |

The development username is an archive-path namespace, not a new SimBoard case
identity field. It is intentionally **not** validated against provenance
`hpc_username`: zppy derives the path segment from `MachineInfo.username`, but
derives provenance identity from `env_case.xml` `REALUSER`. SimBoard must
continue to resolve the Case solely from the authoritative provenance identity.
Production must remain unnested so it retains one authoritative published path
per case. This issue changes the scanner's accepted inferred-path contract; it
does not add support for arbitrary explicit `www` layouts outside that contract.

## Implementation Plan

1. **Make archive-layout validation tier-aware.**
   - Update `_validate_layout()` in
     `backend/app/scripts/ingestion/diagnostics_link_scanner.py` to parse the
     tier first and accept only the four layouts above.
   - Preserve current validations that `case_name` matches the terminal path
     component and that `case_group` is present only when the grouped form is
     used and matches its path component.
   - For `development`, treat the username component as an opaque required
     directory segment. Do not compare it to provenance `hpc_username`; the
     latter remains the authoritative identity supplied by `env_case.xml`.
   - Keep all malformed, ambiguous, and unsupported paths invalid so discovery
     logs and skips them rather than linking an incorrect directory.

2. **Preserve candidate and scanner-state identity behavior.**
   - Continue treating the full archive-relative case directory as the scanner
     state key. This naturally distinguishes two development users publishing
     the same case while retaining the single production path.
   - Keep newest-provenance selection scoped to each discovered case directory;
     no changes are needed to URL-boundary, symlink, output-readiness, or
     provenance-pair validation beyond the layout contract.

3. **Extend focused scanner tests.**
   - Update the test fixture in
     `backend/tests/features/ingestion/test_diagnostics_link_scanner.py` so it
     writes `case_group` based on the tier-aware path shape rather than simply
     directory depth.
   - Add successful discovery coverage for ungrouped and grouped production,
     plus ungrouped and grouped development paths. Include a development case
     where the path username differs from provenance `hpc_username` to confirm
     path namespacing does not alter case resolution.
   - Add rejection coverage for legacy development paths without the username
     component, malformed extra components, and production paths that include
     an additional username component.
   - Retain explicit coverage that a production layout never interprets its
     case-group component as a username.

4. **Align user and architecture documentation.**
   - Update `docs/user/diagnostics.md` with the tier-specific layouts,
     explaining that development output is per user and that production is
     intentionally a single authoritative path.
   - Update `docs/architecture/diagnostics-linkage.md` to describe the accepted
     production/development shapes, distinguish development path namespacing
     from provenance-based Case identity, and clarify that scanner state remains
     per archive-relative directory.

5. **Validate the change.**
   - Run the focused scanner tests first:
     `uv run pytest tests/features/ingestion/test_diagnostics_link_scanner.py`
     from `backend/` (or the project-equivalent configured test invocation).
   - Run the required backend suite from the repository root:
     `make backend-test`.
   - Run `make pre-commit-run` from the repository root before submitting the
     change.

## Out of Scope

- Changes to zppy publishing, its production-collision checks, or its
  provenance-settings permission fix; those are delivered by zppy PR 868.
- Provisioning the group-writable `diagnostics_archive` directory spine, which
  zppy explicitly identifies as a separate operational task.
- Reorganizing or migrating existing diagnostics directories. Legacy layouts
  that do not meet the current contract should be skipped rather than guessed.
