# SimBoard Frontend

The frontend is a React single-page application for browsing, comparing, and uploading E3SM simulation metadata.

## Responsibilities

- route composition and page-level UI
- case and simulation browsing
- side-by-side comparison
- authenticated upload flow
- cookie-based browser auth integration

## Architecture Notes

The frontend uses feature-based organization and enforces import boundaries with ESLint.

- `src/routes/` composes top-level routes.
- `src/features/*/` contains feature modules such as `browse`, `simulations`, `compare`, and `upload`.
- `src/features/*/api/` contains feature-specific API calls.
- `src/features/*/hooks/` contains feature-specific hooks.
- `src/components/shared/` is for reusable shared components.
- `src/components/ui/` is for lower-level UI primitives.

Feature modules should not import directly from other feature modules. This is enforced at lint time by `eslint-plugin-boundaries` — if you see an ESLint error about an invalid cross-feature import, move the shared code to `src/components/shared/` or `src/lib/`.

## Important Locations

```text
frontend/src/routes/            top-level route composition
frontend/src/features/browse/   run browser and filters
frontend/src/features/simulations/
                                cases, runs, and detail pages
frontend/src/features/compare/  side-by-side comparison UI
frontend/src/features/upload/   authenticated archive upload flow
frontend/src/auth/              auth provider, callback, protected routes
frontend/src/components/        layout, shared, and UI components
frontend/src/api/               shared Axios client and auth-state glue
```

## Developer Commands

Run these from the repo root:

```bash
make frontend-run
make frontend-lint
pnpm --dir frontend run type-check
```

For repo-wide setup and contributor workflow, see [docs/developer/README.md](../docs/developer/README.md).
