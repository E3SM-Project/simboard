# Frontend Design System

SimBoard UI conventions for the React, Tailwind CSS, and shadcn/ui frontend. Source files are authoritative; this page explains how to use them. Paths are relative to `frontend/src/` unless noted.

## Principles

- **Data first.** Pages exist to find, inspect, and compare simulation metadata. Favor dense, scannable tables and label/value grids over decoration.
- **Neutral identity.** shadcn `new-york` style on the `neutral` base color. Color signals state (status, errors, warnings, info), not branding.
- **Progressive disclosure.** Show common controls first; put secondary filters, details, and history behind collapsibles, expandable rows, popovers, and dialogs.
- **Explicit state.** Every data view handles loading, refreshing, empty, and error states, and keeps previously loaded data visible when a refresh fails.
- **Reuse before creating.** Use existing primitives and shared components. Add new ones only when a pattern repeats across features.

## Tokens

| Source                        | Defines                                                                                             |
| ----------------------------- | --------------------------------------------------------------------------------------------------- |
| `frontend/src/index.css`      | Color and radius CSS variables (`:root`, `.dark`), base styles, Markdown and editor content styles. |
| `frontend/tailwind.config.js` | Maps CSS variables to Tailwind utilities (`bg-background`, `text-muted-foreground`, `rounded-lg`).  |
| `frontend/components.json`    | shadcn style, base color, aliases, and icon library (lucide).                                       |

### Color

- Use semantic token utilities for neutral UI: `text-foreground`, `text-muted-foreground`, `bg-background`, `bg-muted`, `border-border`, `ring-ring`.
- Use `primary` for the main action and `destructive` for destructive actions (through `Button` variants).
- State colors use Tailwind palette tints (light background, matching border, dark text): `red` for errors, `amber` for warnings, `sky` or `blue` for info and active context.
  - Notices: use `Alert` (`components/ui/alert.tsx`) with `variant="error" | "warning" | "info"` instead of repeating the classes.
  - Execution status: defined once in `components/shared/ExecutionStatusBadge.tsx`. Use that component instead of restyling statuses.
- In-app text links use `text-blue-600 hover:underline`.

### Typography

- System font stack (Tailwind default). No custom fonts.
- Body and table text: `text-sm`. Secondary metadata, help text, and counts: `text-xs text-muted-foreground`.
- Label/value metadata: label `text-[13px] font-semibold text-muted-foreground`, value `text-sm text-foreground`. See `SummaryField` in `features/catalog/components/CaseConfiguration.tsx`.
- Identifiers (execution IDs, hashes, paths): `font-mono text-xs`, usually through `TableCellText` with `mono`.
- Headings: one `h1` per page, then `h2` for sections. Overview pages (Home, About) use larger hero headings than data pages.

### Spacing, radius, and elevation

- Use the Tailwind spacing scale. Page sections stack with `space-y-6`; form fields with `space-y-1` or `space-y-2`.
- Radius: controls and notices use `rounded-md` (from `--radius`); cards and panels use `rounded-xl` or `rounded-2xl`; pills use `rounded-full`.
- Elevation: surfaces use `border` plus at most `shadow-sm`. Stronger shadows are for overlays only (provided by the primitives).

## Components

| Layer      | Location                 | Use                                                                                       |
| ---------- | ------------------------ | ----------------------------------------------------------------------------------------- |
| Primitives | `components/ui/`         | shadcn/Radix building blocks. Compose them; do not fork them for one feature.             |
| Shared     | `components/shared/`     | Cross-feature UI such as `ExecutionStatusBadge` and `MarkdownContent`.                    |
| Layout     | `components/layout/`     | App shell: `NavBar`, `MobileMenu`.                                                        |
| Feature    | `features/*/components/` | Feature-specific UI. Promote to `components/shared/` only when a second feature needs it. |

Commonly used SimBoard-specific primitives:

- `LoadingState` (`components/ui/loading-state.tsx`): loading and refresh indicator with `page`, `section`, and `inline` kinds. Announces via `role="status"`.
- `Alert` (`components/ui/alert.tsx`): inline error, warning, or info notice. Errors use `role="alert"`; others use `role="status"`. Pass layout classes (flex, padding, radius) through `className`.
- `TableCellText` (`components/ui/table-cell-text.tsx`): truncates cell text to 1–3 lines, shows the full value by `title` or tooltip, and renders `—` for empty values.
- `Button` variants: `default` for the primary action, `outline` for secondary actions, `ghost` for low-emphasis and icon actions, `destructive` for deletes, `link` for inline text actions. Use `size="sm"` in toolbars and tables.
- Override primitive classes with `className` and `cn()` (`lib/utils.ts`) only for layout or sizing, not to restyle the variant.

## Layout and navigation

- `App.tsx` renders `NavBar`, the routed page, and `Toaster`. Routes are composed in `routes/routes.tsx` from `features/*/routes.tsx`.
- Primary navigation lives in `NavBar` (desktop, `md` and up) and `MobileMenu` (below `md`). Active links use `text-foreground` with an underline border.
- Pages are centered containers: `mx-auto w-full max-w-* px-6 py-8 space-y-6`. Width follows content density, from narrow forms (Upload) to wide comparison workspaces (Compare).
- Detail pages start with a back button (`Button variant="outline" size="sm"` with `ArrowLeft`), the `h1`, and page-level actions aligned right. See `features/catalog/CaseDetailsPage.tsx`.
- Group page content in bordered sections or `Card`s, each with an `h2` heading.

## Tables

- Use `Table` primitives (`components/ui/table.tsx`) inside an `overflow-x-auto` container. Set a `min-w-*` on wide tables so they scroll instead of compressing.
- Use `TableCellText` for variable-length values. Use `table-fixed` with `colgroup` or width classes when columns need stable widths.
- Use `@tanstack/react-table` for tables with sorting, pagination, or column definitions shared across views (`features/catalog/CasesPage.tsx`, `features/home/components/LatestExecutionsTable.tsx`). Simple read-only tables map rows directly.
- Sortable headers: a `button` inside `TableHead`, with `aria-sort` on the header and a direction icon. Canonical: `ExecutionSortHeader` in `features/catalog/components/CaseExecutionsTable.tsx`.
- Expandable rows: an icon `Button` in the first column toggles a full-width detail row (`colSpan` of all columns). See `features/catalog/CasesPage.tsx`.
- Long tables use a sticky header (`sticky top-0` on `TableHeader` with a background) inside a height-limited scroll area.
- Empty results render one row spanning all columns with centered `text-muted-foreground` text.
- Pagination sits below the table: a result count on the left, `Previous`/`Next` outline buttons and the page number on the right.

## Filters and search

Canonical: the filter panel in `features/catalog/CasesPage.tsx`.

- Search input with a leading `Search` icon (`pl-9` or `pl-10`), followed by the most-used filters in a responsive grid.
- Secondary filters go in a `Collapsible` behind a "More filters" button that shows the active count.
- Show active filters as removable pills (label, value, and an `X` button with `aria-label`), plus a "Clear all" action.
- Keep filter, sort, and pagination state in URL search params so views can be shared ("Copy search").
- Use `Select` for short option lists and `SearchableFilterSelect` (`Popover` + `Command`) for long ones.
- Reset pagination when a filter changes.

## Selection and comparison

Canonical: execution selection in `features/catalog/CaseDetailsPage.tsx` and `features/catalog/components/CaseExecutionsTable.tsx`.

- Select rows with `Checkbox`, each with a descriptive `aria-label`. Disable unselected rows when the selection limit (`MAX_CASE_EXECUTIONS` in `lib/catalog/executionDiscovery.ts`) is reached.
- Show the selection count with `aria-live="polite"`, a "Clear selection" action, and a primary action that includes the count (`Compare (N)`).
- Tell users when selected items are hidden by filters.
- Selection that must survive navigation is lifted to `App.tsx` and passed through routes.
- Comparison opens in a large `Dialog`. Focus moves to the dialog title on open and returns to the triggering button on close. `ExecutionPicker` adjusts the selection inside the dialog.
- Comparison grids keep the field-label column sticky on the left and the execution headers sticky on top (`features/compare/ComparePage.tsx`).

## Metadata presentation

- Use `dl`/`dt`/`dd` for label/value metadata, in a responsive grid (`grid-cols-1 sm:grid-cols-2 lg:grid-cols-4`). See `CaseConfigurationSummary` in `features/catalog/components/CaseConfiguration.tsx`.
- Show missing values as `—` or "Unset", never as blank space.
- Allow long values to wrap (`[overflow-wrap:anywhere]` or `break-all` for identifiers).
- Explain domain terms with an `Info` icon button that opens a `Tooltip`. The button needs an `aria-label` such as `About {label}`.

## Forms and editing

- Pair `Label` (with `htmlFor`) and `Input`, `Textarea`, or `Select`. Link help text with `aria-describedby`. See the Case Group field in `features/catalog/CaseDetailsPage.tsx`.
- Edit mode is explicit: an `Edit` button switches to inputs, replaced by `Cancel` and `Save Changes`. Disable save while saving or when nothing has changed, and show progress in the label (`Saving…`).
- When editing is unavailable, explain why: a "Log In to Edit" action for signed-out users, or a disabled button with a tooltip for users without access.
- Show validation errors next to their fields, and a summary notice for server-side errors.

## Dialogs and overlays

| Need                                          | Use                                   |
| --------------------------------------------- | ------------------------------------- |
| Focused task or large workspace               | `Dialog`                              |
| Anchored picker or small panel                | `Popover` (with `Command` for search) |
| Short definition or full value on hover/focus | `Tooltip`                             |
| Action menu or column visibility              | `DropdownMenu`                        |
| Inline show/hide content                      | `Collapsible`, `Accordion`, or `Tabs` |

Every dialog has a `DialogTitle` and `DialogDescription`, and returns focus to its trigger on close.

## UI states

| State                          | Pattern                                                                                                                       |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| Initial page load              | `LoadingState kind="page"` or `kind="section"`.                                                                               |
| Background refresh             | `LoadingState kind="inline"` above the content, which stays visible.                                                          |
| Refresh failed, data available | `Alert variant="error"` above the content: "Could not refresh … Showing previously loaded …" with a `Retry` button.           |
| Load failed, no data           | `Alert variant="error"` in place of the content with a `Retry` button.                                                        |
| No data or no matching results | Table: a full-width empty row. Panel: a dashed-border block with a message and, when filters apply, a "Reset filters" action. |
| Transient result               | `toast` from `hooks/use-toast.ts` (for example, link copied or upload failed). Use `variant: 'destructive'` for failures.     |
| Pending action                 | Disable the button and change its label (`Saving…`, `Loading more…`).                                                         |

## Responsive behavior

- Design mobile-first with Tailwind breakpoints. `md` switches the navigation; `sm`, `lg`, and `xl` widen grids.
- Wrap toolbars and action groups (`flex flex-wrap gap-2`); stack header rows below `md` (`flex-col md:flex-row`).
- Tables scroll horizontally instead of hiding columns. Optional columns are user-controlled (column visibility menus).

## Accessibility

- Rely on Radix primitives for focus management, keyboard support, and ARIA on dialogs, popovers, menus, selects, and tabs.
- Show focus on custom controls with `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`.
- Every icon-only button has an `aria-label`; decorative icons use `aria-hidden="true"`.
- Use `aria-pressed` for toggle buttons, `aria-expanded` for disclosure buttons, `aria-sort` for sorted headers, and `role="status"` or `aria-live="polite"` for counts and loading text.
- Keep text at WCAG 2.2 AA contrast (4.5:1 for normal text). Do not convey state by color alone; status badges pair color with a label and icon.

## Known deviations

These exist in the code but are not conventions. Do not copy them into new work. Proposed fixes are in the [design review](github-issues/451-design-system/design-review.md).

- Neutral colors mix raw `slate-*` (catalog, compare), raw `gray-*` (upload), and semantic tokens. Prefer semantic tokens for new neutral UI until [#452](https://github.com/E3SM-Project/simboard/issues/452) decides the target.
- `.dark` tokens exist but dark mode is not supported (no toggle, many `bg-white` surfaces). Tracked in #452.
- The Upload page uses native form controls instead of shadcn primitives. Tracked in #452.
- Page container widths and `h1` sizes vary per page. Tracked in #452.
- Upload's validation and result panels and the compare-route notice panels still inline their state colors instead of using `Alert`.
- Some files are unused: `App.css`, `features/compare/ComparePage.css`, `components/examples/`, `components/ui/multi-select.tsx`, and several `features/upload/components/` files.
