# Diagnostics design-system audit (#435)

Audit of the native diagnostics UI against [Frontend Design System](../../design-system.md), after rebasing onto `main` with #453, #457, and #458. Paths are relative to `frontend/src/features/diagnostics/`.

## Consistency fixes

Existing conventions cover these; no UX decision needed.

- [x] **1. Raw neutral colors.** 61 `no-restricted-syntax` lint errors (`slate-*`, `bg-white`) in `ComparePage.tsx`, `components/RunEditor.tsx`, `components/ComparisonBar.tsx`, `components/DiagnosticRunList.tsx`, and `components/DiagnosticsRunsCard.tsx`. Use semantic tokens. Blocks CI.
- [x] **2. Page width tiers.** `ComparePage.tsx` uses `max-w-[1600px]`; `ComparisonBar.tsx` uses `max-w-[1440px]`. Use the workspace tier, `max-w-screen-2xl`.
- [x] **3. Heading scale.** `h1` is `text-xl`; the variable `h2` in `ComparePage.tsx` is `text-base`; the Case details Diagnostics card title is a `div`, so that section has no `h2`. Use `text-2xl font-semibold tracking-tight` for `h1` and `text-lg font-semibold` for `h2`.
- [x] **4. Back control.** `ComparePage.tsx` uses a text link. Use an outline back button.
- [x] **5. Notices.** A local `Notice` component, red error text, and amber status paragraphs repeat state colors; one Retry button sits inside a `<p>`. Use `Alert`.
- [x] **6. Loading states.** Compare load is plain text; refetch only dims content; the Diagnostics card shows loading only in its header; case discovery uses plain text. Use `LoadingState` (`section` for first load, `inline` for refresh).
- [x] **7. Empty and no-match states.** "No plots in common", "No supported runs", and "No variables match this filter" are plain paragraphs with no reset. Use a dashed-border block and offer "Clear filter".
- [x] **8. Text links.** Run labels, source directory links, "View in Diagnostics", and "Open original image" are not `text-blue-600 hover:underline`.
- [x] **9. Identifiers.** `diagnosticIdentifier` output is not `font-mono text-xs`.
- [x] **10. Panel radius.** Plot figures and RunEditor panels use `rounded-lg`. Panels use `rounded-xl`.
- [x] **11. Elevation.** `ComparisonBar.tsx` uses a custom shadow, `backdrop-blur`, and translucent white. Use `border-t bg-card shadow-sm`.
- [x] **12. Selection limit.** Add stays enabled when a group is full, then shows a destructive toast or inline error. Disable unselected rows at the limit and explain why.
- [x] **13. Comparison actions.** Compare buttons omit the count, and the tray says "Clear all". Use `Compare (N)` and "Clear selection".
- [x] **14. Toggle styles.** Variable list and season/region/panel choices use an inverted dark fill; the tool filter uses a muted track; analysis uses `Tabs`. Pick one style, preferably the muted-track style of the tool filter.
- [x] **15. Accessibility.** Headings carry `aria-live` (`RunEditor.tsx`); controls have both `aria-label` and `aria-labelledby` (`DiagnosticRunList.tsx`); tray `aria-controls` targets an element absent while collapsed; empty `role="group"` anchor spans; low-contrast search icon in `ComparePage.tsx`. The labelled `role="group"` anchor spans stay: resource shortcuts and bookmarked hashes focus them, so they need an accessible name.
- [x] **16. Hidden selections.** Tool and analysis filters can hide added runs without telling the user.

## Decisions

New patterns the design system does not cover. Each decision lists the docs and UI follow-ups.

- **D1. Full-page comparison.** Execution comparison opens in a large `Dialog`; diagnostics comparison is a page (`/diagnostics/compare`) with a shareable URL and an image grid.
  - **Decision:** Keep the page. Diagnostics comparison needs a shareable URL, Back navigation, and room for an image grid, and it opens from the tray, Case details, and `/diagnostics`. Execution comparison stays a `Dialog`.
  - [x] Add to "Selection and comparison" in `docs/design-system.md`: one-off comparisons of a few items use a `Dialog`. Comparisons meant to be bookmarked or shared, or with large media grids, use a route with all view state in the URL, an outline Back button, and "Copy link".
- **D2. Global comparison tray.** `ComparisonBar.tsx` is fixed to the viewport on every page except `/diagnostics*` and sets `document.body` bottom padding.
  - **Decision:** Keep the tray. It is the only way to collect runs across Case details pages. It hides on `/diagnostics*` because the run editor shows the same selection inline.
  - [x] Document it as the only fixed bottom bar: starts collapsed, uses `border-t bg-card shadow-sm`, and pads content so it never covers anything. Other features do not add fixed bars.
  - Keep the `document.body` padding. No layout shell exists to hold an in-flow spacer, and a spacer would need the same height measurement.
- **D3. Discovery state storage.** Case browser search, selected case, page, and tool/analysis filters persist in `localStorage` (`workspaceState.ts`), not URL search params.
  - **Decision:** Keep `localStorage` and document it as an exception to the URL-state rule. The case browser is a resumable workspace, not a shareable view. `/diagnostics` and `/diagnostics/compare` share `ComparePage`, and the browser also runs inside the "Edit runs" dialog, so discovery params would pollute the shareable comparison URL. "Back to Diagnostics" relies on stored state to restore the user's place. Comparison view state (runs, set, plot, variable filter) stays in the URL.
  - [ ] Stop persisting `page`. Restoring it as `initialPageParam` (`RunEditor.tsx:546`) loads page N without pages 1 to N−1, with no way back except changing the search. Restore from page 1 instead, and if the saved `caseId` is not loaded, show it pinned above the list.
- **D4. Case browser paging.** "Load more cases" differs from the Previous/Next pagination convention.
  - **Decision:** Keep "Load more". Each API page of 10 cases is filtered on the client to cases with supported runs, so Previous/Next would often show empty or short pages.
  - [x] Add to `docs/design-system.md`: use Previous/Next for server-filtered results and "Load more" when results are filtered on the client after fetching.
  - [ ] Show progress next to the button, for example "Checked 30 of 212 cases · 4 with diagnostics", so users know how far the search has gone.
- **D5. Vocabulary and shortcuts.** UI text mixes "tray", "active runs", "selected runs", "staged", "Comparison Group", and "Diagnostic category". `j`/`k` and arrow-key variable stepping is not discoverable.
  - **Decision:** Use one term per concept in UI text. Code names (`tray`, `basket`, `staged`) may stay.

    | Concept                       | Current               | Use                                                                   |
    | ----------------------------- | --------------------- | --------------------------------------------------------------------- |
    | Runs collected across pages   | tray, comparison tray | "selection" ("Remove a run from your selection first.")               |
    | Runs picked, not yet compared | selected runs, staged | **Selected runs**                                                     |
    | Runs shown in the plot grid   | active runs           | **Compared runs** (header: "3 compared · 5 selected")                 |
    | Grouping by diagnostic kind   | Comparison Group      | **Comparison group**, with an `Info` tooltip on why groups cannot mix |
    | Plot set picker               | Diagnostic category   | **Plot set** (matches e3sm_diags "set" and the API's `sets`)          |

  - [ ] Apply the terms in `ComparePage.tsx`, `RunEditor.tsx`, `ComparisonBar.tsx`, `DiagnosticsRunsCard.tsx`, and their tests.
  - [ ] Show a hint under the variable list ("`j`/`k` or ↑/↓ to change variable", `text-xs text-muted-foreground`, keys in `<kbd>`) and set `aria-keyshortcuts` on the list.
  - [x] Add to `docs/design-system.md`: every keyboard shortcut has a visible hint and is ignored while focus is in an input or overlay. The guard at `ComparePage.tsx:235-244` already does the latter.
