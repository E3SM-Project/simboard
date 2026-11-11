# Diagnostics design-system audit (#435)

Audit of the native diagnostics UI against [Frontend Design System](../../design-system.md), after rebasing onto `main` with #453, #457, and #458. Paths are relative to `frontend/src/features/diagnostics/`.

## Consistency fixes

Existing conventions cover these; no UX decision needed.

- [x] **1. Raw neutral colors.** 61 `no-restricted-syntax` lint errors (`slate-*`, `bg-white`) in `ComparePage.tsx`, `components/RunEditor.tsx`, `components/ComparisonBar.tsx`, `components/DiagnosticRunList.tsx`, and `components/DiagnosticsRunsCard.tsx`. Use semantic tokens. Blocks CI.
- [x] **2. Page width tiers.** `ComparePage.tsx` uses `max-w-[1600px]`; `ComparisonBar.tsx` uses `max-w-[1440px]`. Use the workspace tier, `max-w-screen-2xl`.
- [x] **3. Heading scale.** `h1` is `text-xl`; the variable `h2` in `ComparePage.tsx` is `text-base`; the Case details Diagnostics card title is a `div`, so that section has no `h2`. Use `text-2xl font-semibold tracking-tight` for `h1` and `text-lg font-semibold` for `h2`.
- [x] **4. Back control.** `ComparePage.tsx` uses a text link. Use an outline back button.
- [ ] **5. Notices.** A local `Notice` component, red error text, and amber status paragraphs repeat state colors; one Retry button sits inside a `<p>`. Use `Alert`.
- [ ] **6. Loading states.** Compare load is plain text; refetch only dims content; the Diagnostics card shows loading only in its header; case discovery uses plain text. Use `LoadingState` (`section` for first load, `inline` for refresh).
- [ ] **7. Empty and no-match states.** "No plots in common", "No supported runs", and "No variables match this filter" are plain paragraphs with no reset. Use a dashed-border block and offer "Clear filter".
- [ ] **8. Text links.** Run labels, source directory links, "View in Diagnostics", and "Open original image" are not `text-blue-600 hover:underline`.
- [ ] **9. Identifiers.** `diagnosticIdentifier` output is not `font-mono text-xs`.
- [x] **10. Panel radius.** Plot figures and RunEditor panels use `rounded-lg`. Panels use `rounded-xl`.
- [x] **11. Elevation.** `ComparisonBar.tsx` uses a custom shadow, `backdrop-blur`, and translucent white. Use `border-t bg-card shadow-sm`.
- [ ] **12. Selection limit.** Add stays enabled when a group is full, then shows a destructive toast or inline error. Disable unselected rows at the limit and explain why.
- [ ] **13. Comparison actions.** Compare buttons omit the count, and the tray says "Clear all". Use `Compare (N)` and "Clear selection".
- [ ] **14. Toggle styles.** Variable list and season/region/panel choices use an inverted dark fill; the tool filter uses a muted track; analysis uses `Tabs`. Pick one style, preferably the muted-track style of the tool filter.
- [ ] **15. Accessibility.** Headings carry `aria-live` (`RunEditor.tsx`); controls have both `aria-label` and `aria-labelledby` (`DiagnosticRunList.tsx`); tray `aria-controls` targets an element absent while collapsed; empty `role="group"` anchor spans; low-contrast search icon in `ComparePage.tsx`.
- [ ] **16. Hidden selections.** Tool and analysis filters can hide added runs without telling the user.

## Decisions needed

New patterns the design system does not cover. Decide, then document in `docs/design-system.md` or change the UI.

- **D1. Full-page comparison.** Execution comparison opens in a large `Dialog`; diagnostics comparison is a page (`/diagnostics/compare`) with a shareable URL and an image grid.
- **D2. Global comparison tray.** `ComparisonBar.tsx` is fixed to the viewport on every page except `/diagnostics*` and sets `document.body` bottom padding.
- **D3. Discovery state storage.** Case browser search, selected case, page, and tool/analysis filters persist in `localStorage` (`workspaceState.ts`), not URL search params.
- **D4. Case browser paging.** "Load more cases" differs from the Previous/Next pagination convention.
- **D5. Vocabulary and shortcuts.** UI text mixes "tray", "active runs", "selected runs", "staged", "Comparison Group", and "Diagnostic category". `j`/`k` and arrow-key variable stepping is not discoverable.
