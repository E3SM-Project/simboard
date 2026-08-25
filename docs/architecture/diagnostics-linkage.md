# Diagnostics Linkage Architecture

The diagnostics scanner is separate from performance-metadata collection. It discovers published zppy diagnostics and attaches a case-scoped diagnostic link to an already ingested SimBoard Case.

## Terminology

| Term | Definition |
| --- | --- |
| Diagnostics archive | A reviewed, machine-specific readable filesystem root and its corresponding public HTTP(S) base URL. It contains published diagnostics output; it is not a performance archive directory. |
| Diagnostics case | One published diagnostics case directory below a diagnostics archive. This filesystem identity is distinct from, and is resolved to, a SimBoard Case using the provenance case name, machine, and HPC username. |
| Provenance configuration | A timestamped `provenance.*.cfg` file in a diagnostics case directory. Its timestamp identifies which configuration is newest for discovery purposes. |
| Provenance settings | The non-symlink `.settings` file paired with the selected provenance configuration. It supplies the required case-resolution and diagnostics URL values and is the content used to produce the fingerprint. |
| Scanner candidate | A diagnostics case whose newest timestamped provenance configuration has valid paired settings, a published output, a diagnostics URL under the archive's public base URL, and a layout consistent with its settings. If that selected configuration or its settings are invalid or missing, the case is skipped; the scanner does not fall back to an older configuration. At most one candidate is discovered per diagnostics case directory in each archive tier. |
| Fingerprint | The SHA-256 digest of the selected provenance settings file bytes. It lets scanner state distinguish unchanged settings from changed settings without treating the provenance timestamp alone as sufficient. |
| Scanner state | The successful scanner submission record for a machine and archive-relative diagnostics case path. It records the selected settings filename, provenance timestamp, fingerprint, linked URL, submission time, and linked diagnostic link. |
| Linked candidate | A candidate for which scanner state has the same settings filename and fingerprint. It is already represented by a successful scanner submission and is not submitted again. |
| Unchanged candidate | A linked candidate: its selected settings filename and fingerprint match scanner state. “Unchanged” describes scanner submission state, not whether files in the diagnostics directory changed. |
| Deferred candidate | A candidate whose scanner-state lookup cannot complete successfully. It is left for a later scanner run rather than submitted without state. A candidate whose link submission fails is likewise not recorded as successfully linked and remains eligible later. |

Invalid, unreadable, unsafe, or malformed provenance and settings inputs are skipped during discovery rather than becoming scanner candidates. The scanner only considers the `production` and `development` archive tiers, and selects the newest timestamped provenance configuration in each diagnostics case directory.

## Scanner State Flow

1. `MACHINE_NAME` is required and must name the machine whose diagnostics archive the scanner resolves. The scanner rejects unset or blank values before archive resolution, then verifies that the configured root is readable and its public base URL is absolute HTTP(S).
2. It discovers scanner candidates by selecting the newest timestamped provenance configuration for each diagnostics case directory, then validating its paired settings and computing the settings fingerprint. If the selected configuration or settings are invalid or missing, the case is skipped without falling back to an older configuration.
3. For every candidate, it calls `GET /api/v1/diagnostics/scanner-state` with the configured machine and archive-relative diagnostics case path. A missing state is an unlinked candidate; matching settings filename and fingerprint make it unchanged; a failed or non-successful lookup defers it.
4. For each unlinked or changed candidate, it calls `POST /api/v1/diagnostics/scanner/link` with one diagnostic link and provenance metadata. The API resolves the target SimBoard Case from case name, machine, and HPC username, then atomically upserts the case diagnostic link and scanner state. A successful request returns no content.
5. On a later run, the persisted state makes a matching candidate unchanged. A changed filename or fingerprint is submitted again and updates the state for that machine/path identity.

Scanner API access is permitted only for `ADMIN` and `SERVICE_ACCOUNT` roles. A state lookup can return no state, and it returns an error when the supplied machine is unknown. The scanner-link endpoint requires exactly one diagnostic and rejects unsafe archive-relative paths; case-resolution failures also prevent a successful state update.

With `DRY_RUN` enabled, the scanner performs archive resolution and candidate discovery, logs the diagnostics case paths it would link, and exits without reading scanner state or submitting links. It therefore creates or updates no diagnostic links or scanner state; every discovered candidate is reported as a proposed link rather than classified as linked, unchanged, or deferred.
