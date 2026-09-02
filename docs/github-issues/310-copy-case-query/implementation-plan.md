# Issue 310: Persist and Copy Case Searches

## Recommendation and Complexity

**Recommendation: implement.** This is a contained frontend usability and
shareability improvement that resolves a concrete navigation regression: users
currently lose their Cases search when they leave the page or reload it.

**Complexity: moderate.** The change has a small implementation surface and
does not need API, database, or dependency changes. Its risk lies in correctly
synchronizing two-way URL and React state without loops, avoiding a browser
history entry per search keystroke, and maintaining the existing pagination and
detail-page return flows.

Estimated implementation scope:

- Primary change: `frontend/src/features/catalog/CasesPage.tsx`.
- Optional small catalog-local URL-state helper if extraction makes the page
  clearer.
- No backend changes, migrations, or new packages.

## Goal

Make the Cases page search result set durable and shareable. A URL for
`/cases` must represent its filters and relevant table state, restore that
state when loaded directly or through browser navigation, and be copyable from
the page.

## Scope

### In

- Hydrate Cases filters, sort, pagination, and page size from `/cases` query
  parameters.
- Keep the URL synchronized with applied Cases search state.
- Preserve filtered search URLs when navigating from Cases to a case or
  execution detail page and back.
- Add an accessible copy-search action that copies the canonical absolute URL
  and reports success or failure.
- Validate malformed URL state and fall back safely to page defaults.
- Verify linting, type checking, build, pre-commit hooks, and key browser
  workflows.

### Out

- Backend API, database, schema, or migration changes.
- Changes to the execution Browse page URL behavior.
- Serializing transient UI state such as the expanded case row or advanced
  filters disclosure state.
- Introducing a frontend test runner or dependencies only for this change.
- Changing case or execution detail-page share-link behavior.

## Current State

`frontend/src/features/catalog/CasesPage.tsx` owns local state for case-name
search, case group, execution-context filters, sorting, and pagination. It
passes these values to `useCases` and `useCaseFilterOptions`, but none is read
from or written to the page URL.

The page already sends `location.pathname + location.search` as `state.from`
when linking to case and execution details. Detail pages already use that
state for their Back controls. Once `/cases` owns its query string, this flow
will return users to the same query without changes to detail-page routes.

`frontend/src/features/browse/BrowsePage.tsx` is a local precedent for
`useSearchParams` hydration and synchronization. Reuse its behavioral ideas,
not imports, because frontend feature boundaries prohibit direct cross-feature
dependencies.

## URL Contract

Use the existing frontend names for query parameters:

| URL parameter | Cases state | API query field |
| --- | --- | --- |
| `search` | case-name search | `search` |
| `caseGroup` | case group | `caseGroup` |
| `machineId` | machine | `machineId` |
| `hpcUsername` | HPC username | `hpcUsername` |
| `campaign` | campaign | `campaign` |
| `simulationType` | simulation type | `simulationType` |
| `initializationType` | initialization type | `initializationType` |
| `compiler` | compiler | `compiler` |
| `gitTag` | git tag | `gitTag` |
| `sortBy` | table sort field | mapped API sort field |
| `sortOrder` | table sort direction | `sortOrder` |
| `page` | one-based page | `page` |
| `pageSize` | rows per page | `pageSize` |

Examples:

```text
/cases?search=amip&machineId=<machine-id>&hpcUsername=user&campaign=FY26
/cases?search=amip&sortBy=name&sortOrder=asc&page=2&pageSize=50
```

Canonical serialization omits defaults:

- Empty filter values are omitted.
- `page` is omitted for the first page.
- `pageSize` is omitted for the default size.
- `sortBy` and `sortOrder` are omitted for the default latest-run descending
  sort.

The advanced-filter panel may open automatically when an advanced filter is
present in a direct URL, but its open/closed state is not itself serialized.
Expanded table rows remain local UI state.

## Implementation Plan

### 1. Add catalog-owned URL parsing and serialization

**Primary file:** `frontend/src/features/catalog/CasesPage.tsx`

Keep helpers in the page unless their size makes a catalog-local module such as
`caseSearchParams.ts` clearer. Do not place Cases-specific state helpers in the
Browse feature.

1. Define the managed filter keys, default page size, supported page-size
   values, and default sort.
2. Add pure functions to parse:
   - non-empty text values;
   - positive integer page values;
   - only supported page sizes;
   - valid table sort IDs and `asc`/`desc` directions.
3. Add a deserializer that returns the case-name, case group,
   `CaseExecutionFilters`, `SortingState`, and pagination state represented by
   `URLSearchParams`.
4. Add one canonical serializer for the same values. It must URL-encode values
   through `URLSearchParams`, omit defaults, and be the sole source for both
   router updates and the copy action.
5. Ignore unknown query parameters. Invalid known values must use safe defaults
   rather than producing an invalid table/API request.

### 2. Make Cases URL state the durable source of truth

**File:** `frontend/src/features/catalog/CasesPage.tsx`

1. Add `useSearchParams` alongside the existing location handling.
2. Initialize query-backed state from parsed search parameters rather than
   hardcoded local defaults.
3. Add a URL-to-state effect keyed to `searchParams`. It must update all
   query-backed state for direct URL loads and browser Back/Forward navigation.
4. Add a single state-to-URL effect using the canonical serializer. Use
   `setSearchParams` with `{ replace: true }` so typing does not create one
   browser history entry per character.
5. Guard initial render and URL-to-state updates to prevent feedback loops.
   Compare canonical managed parameters before writing where practical.
6. Continue applying the existing 300 ms case-name debounce before updating the
   server query and canonical `search` parameter. The input remains responsive;
   the URL represents the applied search.
7. Reset to the first page when filters or sorting change. The serialized URL
   must delete `page` after this reset.
8. Clamp a requested page after the result total is available. If clamped, the
   canonical URL must update to the valid page.

### 3. Preserve existing filter and table interactions

**File:** `frontend/src/features/catalog/CasesPage.tsx`

Route existing interactions through the synchronized state without changing
their current semantic behavior:

1. Case-name input, primary filters, and advanced execution-context filters.
2. The table-row case-group quick filter.
3. Active-filter-pill removal and Clear all.
4. Sort header clicks and Previous/Next paging.
5. Clear all resets filters and page 1, closes advanced filters as today, and
   removes filter query parameters. It may retain explicitly selected sort and
   page size because they are table preferences rather than filters.
6. Keep selected values visible even when current filter-option data does not
   include them; the existing select rendering already supports that direct-link
   scenario.

### 4. Add copy-search behavior and feedback

**File:** `frontend/src/features/catalog/CasesPage.tsx`

1. Import the `Copy` icon and the existing shared `toast` function.
2. Implement `handleCopySearch` using the canonical serializer to build an
   absolute URL from `window.location.origin` and the `/cases` path.
3. Copy it with `navigator.clipboard.writeText`.
4. On success, show a toast titled `Search link copied` with a concise message
   that the link restores the current case search.
5. On clipboard failure, show a destructive toast titled `Unable to copy search
   link` and direct the user to copy the browser address manually.
6. Add a labeled `Copy search` button beside More filters and Clear all. It
   should be a `type="button"`, include the icon and accessible name, and be
   enabled when the canonical managed query has at least one parameter.

### 5. Verify return navigation without altering details pages

**Files inspected, no expected change:**

- `frontend/src/features/catalog/CaseDetailsPage.tsx`
- `frontend/src/features/catalog/ExecutionDetailsPage.tsx`

Verify that the existing `state.from` behavior now transports a populated
`/cases?...` URL. The Back link on a case or execution detail page must return
to the same filters, sorting, page, and page size.

## Acceptance Criteria

- A direct `/cases?...` URL restores all supported filters, sorting,
  pagination, and page size.
- Applied changes update the URL with encoded, canonical query parameters.
- Refreshing a filtered Cases page preserves the applied result set.
- Browser Back/Forward rehydrates Cases state instead of leaving stale filters.
- Leaving a Cases search for a case or execution detail and using Back restores
  the original `/cases?...` view.
- Copy search copies a complete, absolute URL that opens the same Cases view in
  a new tab.
- Clipboard success and failure both give clear feedback.
- Invalid pages, page sizes, sort values, and unknown parameters do not crash
  the page or issue malformed API requests.
- Default values and empty filters do not add unnecessary query parameters.

## Verification

Run from the repository root after implementation:

```bash
make frontend-lint
pnpm --dir frontend run type-check
make frontend-build
make pre-commit-run
```

Manually verify in a local seeded environment:

1. Load `/cases` without parameters and confirm default filters, sort, and page.
2. Apply every filter type, including a case name containing whitespace and URL
   reserved characters. Confirm displayed state, URL, and results agree.
3. Refresh the filtered page and open its copied URL in a fresh tab; confirm the
   complete view restores.
4. Change sort, page size, and page; confirm the copied URL reproduces them.
5. Open a case and an execution from that page, then use Back; confirm the
   filtered Cases URL and table state return.
6. Use browser Back/Forward between two distinct Cases URLs and confirm state
   hydrates without reset loops.
7. Remove an individual filter, use the table-row case-group quick filter, and
   use Clear all; confirm relevant URL values disappear and every filter change
   resets pagination correctly.
8. Test malformed URLs such as nonnumeric `page`, unsupported `pageSize`, and
   invalid sort values; confirm safe defaults.
9. Confirm the success toast after copying; where clipboard permissions can be
   denied, confirm the destructive fallback toast.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| URL/state effects repeatedly update each other | Use one canonical serializer, initial/hydration guards, and equality checks before router writes. |
| Search typing produces excessive history entries | Synchronize with `replace: true` and retain the existing debounce. |
| A requested page is beyond the filtered total | Clamp after result totals load and update the canonical URL. |
| Stale filter options hide a direct-link selection | Retain the existing selected-option fallback in filter selects. |
| Clipboard access is unavailable | Catch failures and show a clear manual-copy fallback toast. |
