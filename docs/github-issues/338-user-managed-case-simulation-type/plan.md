# Plan: User-Managed Case Simulation Type

Tracks [issue #338](https://github.com/E3SM-Project/simboard/issues/338).

## Goal

Make `simulation_type` a nullable, user-managed property of a case. A case may
be classified as `production`, `development`, or unset. Diagnostics publication
remains user-managed outside SimBoard; SimBoard only highlights a disagreement
between the case value and the tier recorded in diagnostics provenance.

## Decisions

- Store unset as `NULL`, not as an `unset` string.
- Define a case-specific type rather than reusing the execution-level
  `SimulationType`, which has incompatible values and semantics.
- Permit authorized users to set, change, or clear the case value even when
  diagnostics exist.
- Derive diagnostics tiers only for informational consistency checks. Do not
  move diagnostics, reject scanner submissions, or automatically update a case
  classification.
- Exclude diagnostics backfill and scanner synchronization. The separate v3
  diagnostics-backfill work owns its own backfill behavior.
- Remove the obsolete execution-level simulation type only in a separately
  deployable follow-up phase, with no value migration to cases.

## Phases

1. [Case classification and diagnostics consistency](phase-1-case-classification-and-diagnostics-consistency.md)
   adds the case data/API/UI contract and a non-blocking diagnostics mismatch
   indicator.
2. [Execution simulation-type removal](phase-2-remove-execution-simulation-type.md)
   removes the legacy per-execution classification after the case contract is
   deployed and consumers have migrated.

## Out of Scope

- Publishing, moving, promoting, or deleting diagnostics output.
- Updating case classification from scanner input or existing provenance.
- A migration or script that backfills case classifications.
- Mapping legacy execution values such as `unknown`, `experimental`, or `test`
  into case values.

## Verification

Each phase must update affected tests and run the checks appropriate to its
backend and frontend changes. Run repository pre-commit hooks from the
repository root before submitting a change.
