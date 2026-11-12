# Diagnostics code audit (#435)

Triage of the [PR #437 code review](https://github.com/E3SM-Project/simboard/pull/437#issuecomment-6693859182), written against `1c26fac`. Rechecked against `ea793ce`. Backend paths are relative to `backend/app/features/diagnostics/`; frontend paths to `frontend/src/features/diagnostics/`.

## To fix

- [x] **C1. Deadline does not bound HTTP waits (review item 2, medium).** `with_http_fetcher` builds the client with a fixed `diagnostics_request_timeout_seconds` (`archive.py:211-212`), and `client.stream` (`archive.py:188-199`) does not shorten it to the remaining budget. A response arriving after the deadline is still classified by `_classify`, so a late 404 reads as `ABSENT` instead of `FAILED`. Pass a per-request timeout capped at the remaining time, and return `FAILED` when the deadline passes before the headers are handled.
- [x] **C2. Malformed address fails the whole comparison (review item 3, medium).** `urlsplit` raises `ValueError: Invalid IPv6 URL` for `https://[/viewer/`. `read_catalog_cached` and `read_catalog` call `is_run_url` / `is_viewer_url` before any guard (`catalog.py:10-15`, `catalog.py:27`), so `POST /diagnostics/compare` returns HTTP 500. The frontend regex `isRunUrl` (`compareState.ts:99-103`) accepts the address, and shared links bypass it anyway. Return a per-run `unrecognized_url` error instead.
- [ ] **C3. Unused ETag/304 path (review simplification).** `compare_runs` hashes the response and answers `If-None-Match` with 304 (`api.py:100-104`). Browsers do not cache `POST` responses and the frontend sends no conditional requests, so the path never runs. Remove it, its test (`test_compare.py::test_supports_conditional_requests`), and "with an ETag" in `docs/architecture/diagnostics-comparison.md:37`.
- [ ] **C4. Stale `Plots` docstring (found during triage).** `ComparePage.tsx:707-709` says the shared reference panel is shown once. The code now shows one reference panel per distinct run image and reference.

## Already resolved

- **References shown as shared (review item 1, high).** Each run keeps its own reference: per-run reference panels and captions in `Plots` (`ComparePage.tsx:711-795`), and the heading reads "per-run references" when they differ (`ComparePage.tsx:581-583`). Browser tests cover distinct and same-name references (`frontend/tests/fixtures/diagnosticsWorkspace.tsx`, "distinct references retained" and "same-name references retain distinct published images").
- **Browser tests for reference rendering and failure states (review validation).** Covered by the fixture above, including unavailable plots, failed catalogs with Retry, and incompatible runs.

## Not adopting

- **Replace custom radio buttons with existing controls.** `Choice` (`ComparePage.tsx:652-695`) already implements the radio-group pattern: roving `tabIndex`, arrow keys, Home/End. No Radix radio or toggle-group primitive is installed, and adding a dependency to replace about 40 tested lines is not worth it. Design audit item 14 settled its style.
- **Show whole images instead of cropped panels.** Run/Reference/Difference panels are core to the IICE comparison flow, are implemented, and are tested. The crop windows come from IICE (documented in `docs/architecture/diagnostics-comparison.md`).
- **Defer cross-tab synchronization.** It is a small `storage` listener (`comparisonBasket.ts:63-70`) with tests. Removing it would save nothing.

## Issue #435 closure (not code)

The review rates IICE inventory and effort/maintenance assessment as partial. These belong in #435 or a revised set of acceptance criteria, not in this PR's code. The issue owner decides.
