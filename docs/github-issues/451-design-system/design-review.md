# Frontend design review (#451)

Audit of `frontend/src` against [Frontend Design System](../../design-system.md) and external references. These are proposals, not conventions. Paths are relative to `frontend/src/`.

## Strengths

- Consistent shadcn/Radix primitive layer with semantic tokens; `text-muted-foreground` is the dominant secondary-text style.
- SimBoard-specific primitives cover recurring needs: `LoadingState`, `TableCellText`, `ExecutionStatusBadge`.
- The Cases filter panel matches established filter-toolbar guidance: URL-backed state, removable active-filter pills, "Clear all", and a collapsible secondary group.
- Execution selection and comparison handle limits, hidden selections, live counts, and dialog focus return.
- Data views keep stale data visible on refresh failure and offer `Retry`.

## Recommendations

Priority: **P1** high impact or accessibility, **P2** consistency and maintainability, **P3** polish.

### Consistency fixes

Low risk; no UX decision needed. Addressed in #451.

| #   | Issue                                                                                                                                                | Proposal                                                                            | References                                                                                                                                     | Priority |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| 1   | Cases table headers show `▲`/`▼` text, no `aria-sort`, and no focus ring (`features/catalog/CasesPage.tsx`).                                         | Match `ExecutionSortHeader`: `aria-sort`, direction icon, focus-visible ring.       | `features/catalog/components/CaseExecutionsTable.tsx`; [PatternFly table](https://www.patternfly.org/components/table/design-guidelines)       | P1       |
| 2   | Cases expand button lacks `aria-expanded`.                                                                                                           | Add `aria-expanded`.                                                                | WAI-ARIA disclosure pattern                                                                                                                    | P1       |
| 3   | Cases filter `<label>`s are not associated with their controls.                                                                                      | Add `htmlFor` and matching control `id`s; the search input has no accessible name.  | Case Group field in `features/catalog/CaseDetailsPage.tsx`                                                                                     | P1       |
| 4   | About 12 inline error, warning, and info notices repeat the same classes.                                                                            | Add the shadcn `Alert` primitive with SimBoard state variants; keep current colors. | [shadcn Alert](https://ui.shadcn.com/docs/components/alert); [PatternFly alert](https://www.patternfly.org/components/alert/design-guidelines) | P2       |
| 5   | Text links mix `text-blue-600` and `text-blue-700`.                                                                                                  | Standardize on `text-blue-600`. Both pass AA on white (5.17:1 and 6.70:1).          | —                                                                                                                                              | P3       |
| 6   | Unused files: `App.css`, `features/compare/ComparePage.css`, `components/examples/`, `components/ui/multi-select.tsx`, and unused upload components. | Delete them.                                                                        | —                                                                                                                                              | P2       |

### Needs UX evaluation or an architecture decision

Tracked in [#452](https://github.com/E3SM-Project/simboard/issues/452): neutral color strategy (`slate-*`, `gray-*`, or semantic tokens), dark mode, Upload form controls, and page width and heading tiers.

Further items not yet tracked:

| #   | Issue                                                                                                                                              | Proposal                                                                                                | References                                                                                    | Priority |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | -------- |
| 7   | `Checkbox` sets `focus-visible:ring-0`, so keyboard focus is invisible on selection checkboxes (`components/ui/checkbox.tsx`).                     | Restore a visible focus ring (shadcn default `focus-visible:ring-1`).                                   | WCAG 2.2 SC 2.4.7                                                                             | P1       |
| 8   | Contrast: `muted-foreground` on `bg-muted` is 4.35:1; `text-destructive` on white is 3.76:1; `slate-400` icons on interactive controls are 2.56:1. | Check affected surfaces; use darker text for small text and at least 3:1 for interactive icons.         | WCAG 2.2 SC 1.4.3 and 1.4.11                                                                  | P1       |
| 9   | Three sorting implementations (TanStack, manual state, and a sort `select` in `ExecutionPicker`).                                                  | Keep TanStack for paginated tables; share one header component across header-sorted tables.             | [Carbon data table](https://carbondesignsystem.com/components/data-table/usage/)              | P3       |
| 10  | `ExecutionStatusBadge` uses raw palette colors and its own markup instead of `Badge`.                                                              | Decide with #452 whether status colors become tokens; then build the badge on `Badge`.                  | [Material 3 color roles](https://m3.material.io/styles/color/roles)                           | P3       |
| 11  | `NavBar` puts a mouse-only tooltip on every primary link and hardcodes `bg-gray-900` for it.                                                       | Evaluate whether nav tooltips add value; if kept, use default `TooltipContent` styling.                 | —                                                                                             | P3       |
| 12  | Empty states vary: plain table rows, dashed panels with actions, and plain text.                                                                   | Distinguish "no data" from "no results"; offer "Reset filters" whenever filters cause the empty result. | [PatternFly empty state](https://www.patternfly.org/components/empty-state/design-guidelines) | P3       |

## Contrast measurements

Computed with the WCAG 2.x relative-luminance formula. Normal text needs 4.5:1; UI components and large text need 3:1.

| Pair                               | Ratio |
| ---------------------------------- | ----- |
| `muted-foreground` on `background` | 4.74  |
| `muted-foreground` on `muted`      | 4.35  |
| `destructive` on white             | 3.76  |
| `slate-400` on white               | 2.56  |
| `slate-500` on white               | 4.76  |
| `blue-600` on white                | 5.17  |
| `red-700` on `red-50`              | 5.91  |
| `amber-900` on `amber-50`          | 8.75  |
