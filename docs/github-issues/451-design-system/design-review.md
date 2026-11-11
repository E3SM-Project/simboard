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

| #   | Issue                                                                                                                                                | Proposal                                                                                                                                                                        | References                                                                                                                                     | Priority |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| 1   | Cases table headers show `▲`/`▼` text, no `aria-sort`, and no focus ring (`features/catalog/CasesPage.tsx`).                                         | Match `ExecutionSortHeader`: `aria-sort`, direction icon, focus-visible ring.                                                                                                   | `features/catalog/components/CaseExecutionsTable.tsx`; [PatternFly table](https://www.patternfly.org/components/table/design-guidelines)       | P1       |
| 2   | Cases expand button lacks `aria-expanded`.                                                                                                           | Add `aria-expanded`.                                                                                                                                                            | WAI-ARIA disclosure pattern                                                                                                                    | P1       |
| 3   | Cases filter `<label>`s are not associated with their controls.                                                                                      | Add `htmlFor` and matching control `id`s; the search input has no accessible name.                                                                                              | Case Group field in `features/catalog/CaseDetailsPage.tsx`                                                                                     | P1       |
| 4   | About 12 inline error, warning, and info notices repeat the same classes.                                                                            | Add the shadcn `Alert` primitive with SimBoard state variants; keep current colors.                                                                                             | [shadcn Alert](https://ui.shadcn.com/docs/components/alert); [PatternFly alert](https://www.patternfly.org/components/alert/design-guidelines) | P2       |
| 5   | Text links mix `text-blue-600` and `text-blue-700`.                                                                                                  | Standardize text links on `text-blue-600`. Both pass AA on white (5.17:1 and 6.70:1). Link-styled buttons in `ExecutionSummaryPanel` and ID labels in `ExecutionPicker` remain. | —                                                                                                                                              | P3       |
| 6   | Unused files: `App.css`, `features/compare/ComparePage.css`, `components/examples/`, `components/ui/multi-select.tsx`, and unused upload components. | Delete them.                                                                                                                                                                    | —                                                                                                                                              | P2       |

### Needs UX evaluation or an architecture decision

Tracked in [#452](https://github.com/E3SM-Project/simboard/issues/452): neutral color strategy (`slate-*`, `gray-*`, or semantic tokens), dark mode, Upload form controls, and page width and heading tiers.

Further items, also tracked in #452:

| #   | Issue                                                                                                                                              | Proposal                                                                                                | References                                                                                    | Priority |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | -------- |
| 7   | `Checkbox` sets `focus-visible:ring-0`, so keyboard focus is invisible on selection checkboxes (`components/ui/checkbox.tsx`).                     | Restore a visible focus ring (shadcn default `focus-visible:ring-1`).                                   | WCAG 2.2 SC 2.4.7                                                                             | P1       |
| 8   | Contrast: `muted-foreground` on `bg-muted` is 4.35:1; `text-destructive` on white is 3.76:1; `slate-400` icons on interactive controls are 2.56:1. | Check affected surfaces; use darker text for small text and at least 3:1 for interactive icons.         | WCAG 2.2 SC 1.4.3 and 1.4.11                                                                  | P1       |
| 9   | Three sorting implementations (TanStack, manual state, and a sort `select` in `ExecutionPicker`).                                                  | Keep TanStack for paginated tables; share one header component across header-sorted tables.             | [Carbon data table](https://carbondesignsystem.com/components/data-table/usage/)              | P3       |
| 10  | `ExecutionStatusBadge` uses raw palette colors and its own markup instead of `Badge`.                                                              | Decide with #452 whether status colors become tokens; then build the badge on `Badge`.                  | [Material 3 color roles](https://m3.material.io/styles/color/roles)                           | P3       |
| 11  | `NavBar` puts a mouse-only tooltip on every primary link and hardcodes `bg-gray-900` for it.                                                       | Evaluate whether nav tooltips add value; if kept, use default `TooltipContent` styling.                 | —                                                                                             | P3       |
| 12  | Empty states vary: plain table rows, dashed panels with actions, and plain text.                                                                   | Distinguish "no data" from "no results"; offer "Reset filters" whenever filters cause the empty result. | [PatternFly empty state](https://www.patternfly.org/components/empty-state/design-guidelines) | P3       |

## Decisions (#452)

| Item                | Decision                                                                                                          | Rationale                                                                                                                  | Status                                   |
| ------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| Neutral colors      | Use semantic tokens; map raw `slate-*`, `gray-*`, and `bg-white` to them.                                         | Matches the neutral shadcn base, keeps one source of truth for contrast, and is a prerequisite for theming.                | Convention documented; migration pending |
| Dark mode           | Remove the unused `.dark` tokens, `darkMode` setting, and `next-themes`.                                          | No toggle or `dark:` usage existed, and raw palette classes would render incorrectly. Revisit after the neutral migration. | Done; support tracked in #455            |
| Upload form         | Use `Label`, `Input`, and `Select`; render panels with `Alert`. The focused validation panel uses `role="group"`. | Matches other forms; a non-live role avoids a second announcement after focus moves to the panel.                          | Convention documented; migration pending |
| Page widths         | Three tiers: form/prose `max-w-4xl`, detail `max-w-7xl`, workspace `max-w-screen-2xl`.                            | Width follows content density with a small, predictable set instead of per-page pixel values.                              | Convention documented; migration pending |
| Heading scale       | App pages: `h1` `text-2xl`, `h2` `text-lg`. Landing pages (Home, About): larger `h1`, `h2` `text-2xl`.            | Keeps data pages compact while preserving the landing pages' existing hierarchy.                                           | Convention documented; migration pending |
| Status colors       | Keep Tailwind tints (no new tokens); build `ExecutionStatusBadge` on `Badge` with shared tones.                   | Matches `Alert`; SimBoard has no brand palette that would justify status tokens.                                           | Done                                     |
| Navigation tooltips | Remove.                                                                                                           | Links already show their labels; tooltips repeated them on every hover with a hardcoded color.                             | Done                                     |
| Empty states        | Distinguish "no data" (message, optional create action) from "no matching results" (message, "Reset filters").    | Users need a way out of a filtered empty result; popover searches stay plain text.                                         | Convention documented; Cases row pending |
| Checkbox focus      | Restore `focus-visible:ring-2` with offset.                                                                       | WCAG 2.2 SC 2.4.7.                                                                                                         | Done                                     |
| Contrast            | Darken `--muted-foreground` and `--destructive`; use `text-muted-foreground` for control icons.                   | WCAG 2.2 SC 1.4.3 and 1.4.11; see measurements below.                                                                      | Done                                     |
| Decorative icons    | No code change; Lucide sets `aria-hidden` on icons without an accessible name.                                    | Only custom SVGs need the attribute, and `GitHubIcon` has it.                                                              | Done                                     |
| Notices and links   | Use `Alert` for compare-route notices and `text-blue-600` for link-styled controls.                               | One notice primitive and one link color.                                                                                   | Done                                     |
| Sorting             | Share `SortableTableHead` across header-sorted tables.                                                            | One implementation for `aria-sort`, icons, and sort labels.                                                                | Done                                     |
| Component loading   | Follow the Loading rules in `docs/design-system.md`.                                                              | One slow request should not hide the rest of the page.                                                                     | Tracked in #454                          |

## Contrast measurements

Computed with the WCAG 2.x relative-luminance formula. Normal text needs 4.5:1; UI components and large text need 3:1. Rows marked (#452) use the updated token values.

| Pair                                      | Ratio |
| ----------------------------------------- | ----- |
| `muted-foreground` on `background`        | 4.74  |
| `muted-foreground` on `muted`             | 4.35  |
| `destructive` on white                    | 3.76  |
| `slate-400` on white                      | 2.56  |
| `slate-500` on white                      | 4.76  |
| `blue-600` on white                       | 5.17  |
| `red-700` on `red-50`                     | 5.91  |
| `amber-900` on `amber-50`                 | 8.75  |
| `muted-foreground` on `background` (#452) | 5.74  |
| `muted-foreground` on `muted` (#452)      | 5.27  |
| `destructive` on white (#452)             | 4.83  |
