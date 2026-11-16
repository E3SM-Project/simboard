# Manual browser review checklist (#452)

Run `make backend-run` and `make frontend-run`. Automated tests already cover sort state, labels, required fields, empty-state text, status badge tones, and sticky-header opacity.

## Overall look

- [x] Pages keep their slate look: table headers, toolbars, and filter panels have the same light fills as before, and nothing turned pure gray.
- [x] Buttons, inputs, dropdowns, and dialogs have a slight cool tint; primary buttons are dark slate rather than black.
- [x] Secondary text (descriptions, counts, metadata) is readable and slightly darker than before.
- [x] Code blocks in Markdown content (for example, execution notes) are dark with light text.
- [x] No page shows a translucent sticky surface.
- [x] Hovering a nav link shows no tooltip.

## Keyboard focus

- [x] Tab through the Case details executions table and the Compare dialog: selection checkboxes, sort buttons, and Compare section toggles (including the sticky label column) all show a visible focus ring.

## Compare (Case details dialog)

- [ ] When a selected execution's details fail to load (block its request in DevTools), the amber notice appears above the grid with "Retry execution details", and the Hide/Remove icon buttons in column headers show a hover change.

## Upload

- [x] The Machine dropdown opens and selects with mouse and keyboard.
- [ ] Choosing an unsupported file shows the error under the file input and no green "Selected …" notice; "Clear file" resets it.
- [x] Uploading an invalid archive scrolls to and focuses the red validation panel with a visible focus ring; a screen reader reads it once.
- [x] A successful upload shows the green "Archive ingested" notice and the created executions table.

## Layout

- [x] Widths and headings look right: About is narrower, Case and Execution details are 1280px, Cases is 1536px, and app-page headings match in size.
- [ ] At about 390px wide, Cases, Case details, the Compare dialog, and Upload have no horizontal page scroll.
