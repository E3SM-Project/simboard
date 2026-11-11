# Manual browser review checklist (#451)

Run `make backend-run` and `make frontend-run`.

## Cases (`/cases`)

- [x] On default load, "Latest completed run" shows a down arrow and announces as sorted descending.
- [x] Clicking each sortable header switches the arrow between up and down and reorders rows. Unsorted headers show a two-way arrow.
- [x] The expand-column header has no sort button.
- [x] Tab through headers: each sort button shows a focus ring, and Enter sorts.
- [x] Clicking "Search" focuses the search box. Clicking a filter label (for example, "Case group") focuses its dropdown.
- [x] The expand chevron opens and closes the row; its expanded state toggles in a screen reader or the accessibility inspector.
- [x] Case name links are `blue-600`.

Manual feedback:

- Applying filters and sorting columns in the case details page causes the table to rerender entirely, showing the loading data right behind it. -- it should be load icon within the table keeping the component visible as it refreshes with new data. This most likely applies to all other tables
  - Documented in `docs/design-system.md` (UI states > Loading); remaining pages listed under Known deviations.

## Case details

- [x] Edit with an invalid link and save: the "Save blocked" notice shows in red.
- [x] Compare dialog: with 2 to 5 executions selected, focus starts on the title when it opens and returns to the Compare button when it closes.
- [x] In the dialog, with fewer than 2 executions selected, the amber "Select at least two…" notice shows.

## Execution details

- [x] "Save blocked" notice in edit mode.
- [x] AI summary error (red) and fallback (amber) notices, if they can be triggered.

## Error states

Block API requests in DevTools, or stop the backend after the page loads, then refetch.

- [x] Home: refresh-error banner with Retry, above the content.
- [x] Home: production cases refresh banner, and the full "Could not load" panel.
- [ ] Cases: refresh-error banner with Retry. (Skipped: markup-only change to `Alert` with unchanged colors.)
- [ ] Case details: "Could not load more execution metadata" strip has only a top border and square corners. (Skipped: markup-only change to `Alert` with unchanged colors.)

Manual feedback: Loading should be for the individual components or tables, rather than the entire page, to provide a smoother user experience.

- Documented in `docs/design-system.md` (UI states > Loading); remaining pages listed under Known deviations.

## Visual regressions

- [x] Compare and Upload links are `blue-600`.
- [x] Upload renders correctly after the unused components were removed.
- [x] At about 390px wide, Cases filters and banners wrap without horizontal page scroll.
