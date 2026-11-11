# Frontend Design System

SimBoard UI conventions for the React, Tailwind CSS, and shadcn/ui frontend. Source files are authoritative; this page explains how to use them. Paths are relative to `frontend/src/` unless noted.

## Principles

- **Data first.** Pages exist to find, inspect, and compare simulation metadata. Favor dense, scannable tables and label/value grids over decoration.
- **Neutral identity.** shadcn `new-york` style on the `neutral` base color. Color signals state (status, errors, warnings, info), not branding.
- **Progressive disclosure.** Show common controls first; put secondary filters, details, and history behind collapsibles, expandable rows, popovers, and dialogs.
- **Explicit state.** Every data view handles loading, refreshing, empty, and error states, and keeps previously loaded data visible when a refresh fails.

## Tokens

Tokens are defined in `frontend/src/index.css` (CSS variables), mapped to utilities in `frontend/tailwind.config.js`, and configured for shadcn in `frontend/components.json`.

- **Color:** Use semantic utilities (`text-foreground`, `text-muted-foreground`, `bg-background`, `bg-muted`, `border-border`) for neutral UI. State colors are Tailwind tints: `red` for errors, `amber` for warnings, `sky` or `blue` for info. Use `ExecutionStatusBadge` (`components/shared/`) for execution status. Text links use `text-blue-600 hover:underline`.
- **Typography:** `text-sm` for body and table text; `text-xs text-muted-foreground` for secondary metadata, help text, and counts. Identifiers (execution IDs, hashes, paths) use `font-mono text-xs`. One `h1` per page, then `h2` for sections.
- **Radius and elevation:** Controls use `rounded-md`; cards and panels use `rounded-xl` or `rounded-2xl`; pills use `rounded-full`. Surfaces use `border` plus at most `shadow-sm`.

## Components

| Layer      | Location                 | Use                                                                                       |
| ---------- | ------------------------ | ----------------------------------------------------------------------------------------- |
| Primitives | `components/ui/`         | shadcn/Radix building blocks. Compose them; do not fork them for one feature.             |
| Shared     | `components/shared/`     | Cross-feature UI such as `ExecutionStatusBadge` and `MarkdownContent`.                    |
| Layout     | `components/layout/`     | App shell: `NavBar`, `MobileMenu`.                                                        |
| Feature    | `features/*/components/` | Feature-specific UI. Promote to `components/shared/` only when a second feature needs it. |

SimBoard-specific primitives:

- `LoadingState` (`components/ui/loading-state.tsx`): loading indicator with `page`, `section`, and `inline` kinds.
- `Alert` (`components/ui/alert.tsx`): inline notice with `error`, `warning`, and `info` variants. Use it instead of repeating state-color classes.
- `TableCellText` (`components/ui/table-cell-text.tsx`): truncates cell text, exposes the full value, and renders `—` for empty values.

Use `Button size="sm"` in toolbars and tables. Override primitive classes with `className` and `cn()` only for layout, spacing, or radius, not to restyle a variant.

## Layout and navigation

- Navigation lives in `NavBar` (desktop) and `MobileMenu` (below `md`).
- Pages are centered `max-w-*` containers whose width follows content density, from narrow forms (Upload) to wide workspaces (Compare).
- Detail pages start with an outline back button, the `h1`, and right-aligned page actions. See `features/catalog/CaseDetailsPage.tsx`.
- Group page content in bordered sections or `Card`s, each with an `h2`.
- Wrap toolbars and action groups, and stack header rows below `md`.

## Tables

- Use `Table` primitives inside an `overflow-x-auto` container. Wide tables scroll horizontally instead of hiding columns; optional columns are user-controlled through column menus.
- Use `TableCellText` for variable-length values, and `table-fixed` with column widths when columns need stable widths.
- Use `@tanstack/react-table` for sorted or paginated tables (`features/catalog/CasesPage.tsx`). Simple read-only tables map rows directly.
- Sortable headers: a `button` inside `TableHead`, with `aria-sort` and a direction icon. Canonical: `ExecutionSortHeader` in `features/catalog/components/CaseExecutionsTable.tsx`.
- Expandable rows: an icon `Button` with `aria-expanded` toggles a full-width detail row. See `features/catalog/CasesPage.tsx`.
- Long tables use a sticky header inside a height-limited scroll area.
- Pagination sits below the table: result count on the left, `Previous`/`Next` and the page number on the right.

## Filters and search

Canonical: the filter panel in `features/catalog/CasesPage.tsx`.

- A labeled search input with a leading `Search` icon, followed by the most-used filters.
- Secondary filters go in a `Collapsible` behind "More filters", which shows the active count.
- Show active filters as removable pills, plus a "Clear all" action.
- Keep filter, sort, and pagination state in URL search params so views can be shared.
- Use `Select` for short option lists and `SearchableFilterSelect` for long ones.
- Reset pagination when a filter changes.

## Selection and comparison

Canonical: execution selection in `features/catalog/CaseDetailsPage.tsx` and `features/catalog/components/CaseExecutionsTable.tsx`.

- Select rows with labeled `Checkbox`es. Disable unselected rows at the selection limit (`MAX_CASE_EXECUTIONS` in `lib/catalog/executionDiscovery.ts`).
- Show a live selection count, a "Clear selection" action, and a primary action with the count (`Compare (N)`).
- Tell users when selected items are hidden by filters.
- Comparison opens in a large `Dialog` that focuses its title on open and returns focus to the trigger on close.
- Comparison grids keep field labels sticky on the left and execution headers sticky on top (`features/compare/ComparePage.tsx`).

## Metadata presentation

- Use `dl`/`dt`/`dd` in a responsive grid. See `CaseConfigurationSummary` and `SummaryField` in `features/catalog/components/CaseConfiguration.tsx`.
- Show missing values as `—` or "Unset", never blank.
- Let long values wrap; break identifiers anywhere.
- Explain domain terms with an `Info` icon button that opens a `Tooltip`, labeled `About {label}`.

## Forms and editing

- Pair `Label` (with `htmlFor`) and its control; link help text with `aria-describedby`. See the Case Group field in `features/catalog/CaseDetailsPage.tsx`.
- Edit mode is explicit: `Edit` switches to inputs with `Cancel` and `Save Changes`. Disable save while saving or when nothing changed, and show progress in the label (`Saving…`).
- When editing is unavailable, explain why: "Log In to Edit" for signed-out users, or a disabled button with a tooltip.
- Show validation errors next to their fields, and an `Alert` for server-side errors.

## Dialogs and overlays

| Need                                          | Use                                   |
| --------------------------------------------- | ------------------------------------- |
| Focused task or large workspace               | `Dialog` with title and description   |
| Anchored picker or small panel                | `Popover` (with `Command` for search) |
| Short definition or full value on hover/focus | `Tooltip`                             |
| Action menu or column visibility              | `DropdownMenu`                        |
| Inline show/hide content                      | `Collapsible`, `Accordion`, or `Tabs` |

## UI states

| State                          | Pattern                                                                                                                |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| Initial load                   | `LoadingState kind="page"` or `kind="section"`.                                                                        |
| Background refresh             | `LoadingState kind="inline"` above the content, which stays visible.                                                   |
| Refresh failed, data available | `Alert variant="error"` above the content ("Could not refresh … Showing previously loaded …") with `Retry`.            |
| Load failed, no data           | `Alert variant="error"` in place of the content with `Retry`.                                                          |
| No data or no matching results | Table: one full-width empty row. Panel: a dashed-border block with a message and, when filters apply, "Reset filters". |
| Transient result               | `toast` from `hooks/use-toast.ts`; `variant: 'destructive'` for failures.                                              |
| Pending action                 | Disable the button and change its label (`Saving…`, `Loading more…`).                                                  |

## Accessibility

Apply these to new and changed UI.

- Show focus on custom controls with `focus-visible:ring-2 focus-visible:ring-ring`.
- Give icon-only buttons an `aria-label`; mark decorative icons `aria-hidden="true"`.
- Use `aria-pressed` for toggles, `aria-expanded` for disclosures, `aria-sort` for sorted headers, and `aria-live="polite"` for counts.
- Meet WCAG 2.2 AA contrast (4.5:1 for text; 3:1 for icons that identify controls). Do not convey state by color alone.

## Known deviations

These exist in the code but are not conventions. Do not copy them into new work:

- Raw `slate-*` and `gray-*` neutrals; prefer semantic tokens.
- Native form controls on the Upload page.
- Inline state-color classes instead of `Alert`.
- `text-blue-700` on link-styled controls.

The full list, including accessibility gaps and open design decisions, is tracked in [#452](https://github.com/E3SM-Project/simboard/issues/452). Rationale is in the [design review](github-issues/451-design-system/design-review.md).
