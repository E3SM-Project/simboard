# Follow-up issue draft: component-specific physical grid resolution

This is a draft for a separate GitHub issue, not part of the grid metadata bug fix.

## Problem

`grid_alias` records the README selection argument. `grid_long_name` records XML
`GRID`. Neither field defines numeric physical spacing, which can vary by component
and location, especially for variable-resolution and unstructured grids.

## Scope

- Identify authoritative archive artifacts for atmosphere, land, ocean, sea ice,
  runoff, and other supported components.
- Define each supported value's meaning, units, and source provenance.
- Specify how variable-resolution grids report ranges or other meaningful measures.
- Define missing-value behavior and validation using representative source files.
- Propose storage and API changes only after those source contracts are verified.

## Acceptance criteria

- Each proposed numeric value has a component, unit, definition, and verified source.
- Aliases and grid specifications remain separate from physical-resolution values.
- Tests cover uniform, variable-resolution, and unavailable metadata.

Creating the GitHub issue requires separate authorization.
