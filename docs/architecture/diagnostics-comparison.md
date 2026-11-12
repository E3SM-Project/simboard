# Diagnostics Comparison Architecture

Side-by-side comparison of published E3SM Diags and MPAS-Analysis output. This
reimplements the core comparison flow of [IICE](https://github.com/E3SM-Project/IICE),
E3SM's standalone web tool for intercomparing diagnostics runs. SimBoard never
touches model data: it reads the HTML and PNGs each tool already published, on
the public E3SM web servers.
Where IICE conventions are kept — its example comparisons, the `!case` label for
older MPAS-Analysis layouts, the panel crop windows and stylesheet widths — the
code and user docs say so at the point of use.

```text
case diagnostic link ─► discovery ─► runs ─┐
pasted run address  ───────────────────────┴─► catalog per run ─► compare ─► page
```

## Backend: `app/features/diagnostics/`

| Module             | Role                                                                                                                                                                                                                                                                                                              |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `archive.py`       | Every HTTP read. Allowlisted URL prefixes (`diagnostics_allowed_url_prefixes`), re-checked on each redirect hop; a request budget and deadline per read; a body size cap; a TTL cache. A missing page (`ABSENT`) is kept distinct from an unreachable server (`FAILED`) so outages are never cached as "no runs". |
| `discovery.py`     | Lists the runs under a case's zppy root from Apache directory listings, following only zppy's `e3sm_diags/<sub>/model_vs_*_Y1-Y2/viewer/` and `mpas_analysis/ts_*_climo_*/` layout.                                                                                                                               |
| `e3sm_diags.py`    | Reads `viewer/index.html` and each set page's `data-preview` images. Also holds the panel windows used to crop the stacked test/reference/difference composites.                                                                                                                                                  |
| `mpas_analysis.py` | Reads the `ocean/` and `sea_ice/` galleries: image, caption, section, and a description that is a season and/or region. Supports older layouts and the `!case` label convention from IICE.                                                                                                                        |
| `plots.py`         | The shared `Catalog` / `PlotSet` / `Plot` model both readers produce.                                                                                                                                                                                                                                             |
| `catalog.py`       | Picks the reader from the URL; caches complete reads.                                                                                                                                                                                                                                                             |
| `compare.py`       | Keeps the plots every run shares and groups a variable's seasons and regions.                                                                                                                                                                                                                                     |
| `api.py`           | `GET /cases/{id}/diagnostics/runs` and `POST /diagnostics/compare`.                                                                                                                                                                                                                                               |

A `Plot.key` names the same diagnostic in every run: case names, years and
model-vs-model reference prefixes are stripped from filenames, so runs line up
even when their references differ. `Plot.group` joins a variable's seasons and
regions into one row.

`POST /diagnostics/compare` reads the runs' catalogs in parallel, returns all
shared sets as a summary and one set in detail (each plot's path in every run),
and is gzipped. Parsers are tested against excerpts of real pages
in `tests/fixtures/diagnostics/`.

## Frontend: `src/features/diagnostics/`

`DiagnosticsRunsCard` (case page) and `ComparisonBar` stage runs in
localStorage (`comparisonBasket.ts`). `ComparePage` renders the compare
response; its run and visualization state is in the URL (`compareState.ts`).
`RunEditor` shares a draft between SimBoard case browsing and manual URL entry,
including IICE examples. Both diagnostics routes open this workspace; populated
links render plots directly. The global tray is hidden inside the workspace.

Case browsing uses existing case search and per-case discovery with bounded
concurrency and explicit pagination. Only discovered supported cases appear;
unsupported directories are excluded with debug logging rather than warnings.
there is no catalog-wide supported-diagnostics index. `DiagnosticRunList` serves
both case pages and workspace drafts. Resource shortcuts use source/run
directory relationships without removing original links.

The workspace synchronizes known selections with the basket, one staged kind
at a time. Browser state and drafts persist locally (`workspaceState.ts`).
Explicit comparison URLs take precedence and never import unrelated local runs.
Full run URLs and labels retain their existing query encoding.

**Compare** and **Apply changes** call the viewer's comparison API before
navigation. Successful checks populate its query cache; incompatible runs or
failed checks leave selections intact. Direct shared URLs retain viewer-side
error and compatibility handling.

## Not yet

- Catalogs are read on demand and cached in process; storing them at ingestion
  would remove the first-view wait.
- E3SM Diags `table`, `taylor`, `cmip6` and `tropical_subseasonal` sets.
