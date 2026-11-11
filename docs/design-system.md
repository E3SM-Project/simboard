# Frontend Design System

SimBoard UI conventions for the React, Tailwind CSS, and shadcn/ui frontend. Source files are authoritative; this page explains how to use them. Paths are relative to `frontend/src/` unless noted.

## Principles

- **Data first.** Pages exist to find, inspect, and compare simulation metadata. Favor dense, scannable tables and label/value grids over decoration.
- **Neutral identity.** shadcn `new-york` style on the `neutral` base color. Color signals state (status, errors, warnings, info), not branding.
- **Progressive disclosure.** Show common controls first; put secondary filters, details, and history behind collapsibles, expandable rows, popovers, and dialogs.
- **Explicit, independent state.** Every data view handles loading, refreshing, empty, and error states in its own area, so one slow or failed request never blanks the rest of the page.

## Tokens

Tokens are defined in `frontend/src/index.css` (CSS variables), mapped to utilities in `frontend/tailwind.config.js`, and configured for shadcn in `frontend/components.json`. SimBoard has a light theme only; do not add `dark:` variants ([#455](https://github.com/E3SM-Project/simboard/issues/455) tracks dark mode).

- **Color:** Use semantic utilities for neutral UI, not raw `slate-*`, `gray-*`, or `bg-white`: `text-foreground` for primary text, `text-muted-foreground` for secondary text and control icons, `border-border` for borders, `bg-muted` for subtle fills, `bg-card` for panels, and `bg-background` for page surfaces. State colors are Tailwind tints, not tokens: `green` for success, `red` for errors, `amber` for warnings and in-progress states, `sky` or `blue` for info. Use `ExecutionStatusBadge` (`components/shared/`, built on `Badge`) for execution status. Text links use `text-blue-600 hover:underline`.
- **Typography:** `text-sm` for body and table text; `text-xs text-muted-foreground` for secondary metadata, help text, and counts. Identifiers (execution IDs, hashes, paths) use `font-mono text-xs`. One `h1` per page, then `h2` for sections. App pages use `text-2xl font-semibold tracking-tight` for `h1` and `text-lg font-semibold` for `h2`. Landing pages (Home, About) use a larger `h1` (`text-4xl font-bold tracking-tight`) and `text-2xl font-semibold` for `h2`.
- **Radius and elevation:** Controls use `rounded-md`; cards and panels use `rounded-xl` or `rounded-2xl`; pills use `rounded-full`. Surfaces use `border` plus at most `shadow-sm`.

## Components

| Layer      | Location                 | Use                                                                                           |
| ---------- | ------------------------ | --------------------------------------------------------------------------------------------- |
| Primitives | `components/ui/`         | shadcn/Radix building blocks. Compose them; do not fork them for one feature.                 |
| Shared     | `components/shared/`     | Cross-feature UI built from primitives, such as `ExecutionStatusBadge` and `MarkdownContent`. |
| Layout     | `components/layout/`     | App shell: `NavBar`, `MobileMenu`.                                                            |
| Feature    | `features/*/components/` | Feature-specific UI. Promote to `components/shared/` only when a second feature needs it.     |

SimBoard-specific primitives:

- `LoadingState` (`components/ui/loading-state.tsx`): loading indicator with `page`, `section`, and `inline` kinds.
- `Alert` (`components/ui/alert.tsx`): inline notice with `error`, `warning`, and `info` variants. Use it instead of repeating state-color classes. Errors use `role="alert"` and other variants `role="status"`; pass `role="group"` when the alert contains its own live regions or receives focus, to avoid duplicate announcements.
- `TableCellText` (`components/ui/table-cell-text.tsx`): truncates cell text, exposes the full value, and renders `—` for empty values.
- `SortableTableHead` (`components/ui/sortable-table-head.tsx`): sortable header cell with `aria-sort`, a direction icon, and a labeled sort button.

Use `Button size="sm"` in toolbars and tables. Override primitive classes with `className` and `cn()` only for layout, spacing, or radius, not to restyle a variant.

## Layout and navigation

- Navigation lives in `NavBar` (desktop) and `MobileMenu` (below `md`).
- Pages are centered containers in one of three width tiers:

  | Tier         | Width              | Pages                                  |
  | ------------ | ------------------ | -------------------------------------- |
  | Form / prose | `max-w-4xl`        | Upload, About                          |
  | Detail       | `max-w-7xl`        | Home, Case details, Execution details  |
  | Workspace    | `max-w-screen-2xl` | Cases, Compare; the `NavBar` container |

- Detail pages start with an outline back button, the `h1`, and right-aligned page actions. See `features/catalog/CaseDetailsPage.tsx`.
- Group page content in bordered sections or `Card`s, each with an `h2`.
- Wrap toolbars and action groups, and stack header rows below `md`.

## Tables

- Use `Table` primitives inside an `overflow-x-auto` container. Wide tables scroll horizontally instead of hiding columns; optional columns are user-controlled through column menus.
- Use `TableCellText` for variable-length values, and `table-fixed` with column widths when columns need stable widths.
- Use `@tanstack/react-table` for sorted or paginated tables (`features/catalog/CasesPage.tsx`). Simple read-only tables map rows directly.
- Use `SortableTableHead` for header-sorted tables. With TanStack, pass `column.getIsSorted()` and `column.toggleSorting()` (`features/catalog/CasesPage.tsx`).
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

- Use `Label`, `Input`, `Select`, and other primitives, not native form controls.
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

### Loading

- Use a page-level loader only while the page's own record loads (for example, the case on Case details). Otherwise render the page shell (heading, filters, toolbars) immediately.
- Each table or section with its own API request loads independently and shows its loading state inside its own container.
- Refetching after a sort, filter, or page change keeps the current rows, headers, and controls visible, with an inline indicator inside the table container. Keep previous query data while the new data loads.
- Canonical: `features/home/components/ProductionCasesTable.tsx` and the "Refreshing cases" bar in `features/catalog/CasesPage.tsx`.

| State                          | Pattern                                                                                                                                      |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Initial load                   | Page record: `LoadingState kind="page"`. Table or section: `LoadingState kind="section"` in its own area.                                    |
| Background refresh             | `LoadingState kind="inline"` inside the table or section container; existing content stays visible.                                          |
| Refresh failed, data available | `Alert variant="error"` above the content ("Could not refresh … Showing previously loaded …") with `Retry`.                                  |
| Load failed, no data           | `Alert variant="error"` in place of the content with `Retry`.                                                                                |
| No data                        | Table: one full-width empty row. Panel: a dashed-border block. Say nothing exists yet; offer a create action if the user can create one.     |
| No matching results            | Same container as "No data", with "No … match these filters." and "Reset filters". Search inside a popover uses plain text (`CommandEmpty`). |
| Transient result               | `toast` from `hooks/use-toast.ts`; `variant: 'destructive'` for failures.                                                                    |
| Pending action                 | Disable the button and change its label (`Saving…`, `Loading more…`).                                                                        |

## Accessibility

Apply these to new and changed UI.

- Show focus on custom controls with `focus-visible:ring-2 focus-visible:ring-ring`.
- Give icon-only buttons an `aria-label`. Lucide icons are `aria-hidden` by default unless given an accessible name; mark custom SVG icons `aria-hidden="true"`.
- Use `aria-pressed` for toggles, `aria-expanded` for disclosures, `aria-sort` for sorted headers, and `aria-live="polite"` for counts.
- Meet WCAG 2.2 AA contrast (4.5:1 for text; 3:1 for icons that identify controls). Do not convey state by color alone.

## Known deviations

These exist in the code but are not conventions. Do not copy them into new work:

- Raw `slate-*`, `gray-*`, and `bg-white` neutrals, mainly in catalog, compare, and upload.
- Native form controls on the Upload page, and inline state-color panels instead of `Alert` on Upload and Compare.
- Page widths and heading sizes outside the width tiers and heading scale above.
- Empty states built from raw neutrals; the Cases table empty row lacks "Reset filters".
- Whole-page loaders that wait for one section's data: Home (catalog overview), Cases (case list), and Case details (executions). Tracked in [#454](https://github.com/E3SM-Project/simboard/issues/454).

Decisions and rationale are in the [design review](github-issues/451-design-system/design-review.md#decisions-452).
