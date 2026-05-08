---
name: frontend-engineer
description: Build or modify SimBoard frontend UI in the existing React, TypeScript, Vite, Tailwind, and shadcn codebase while respecting feature boundaries and existing data-flow patterns.
---

# Frontend Engineer

## Overview

Implement SimBoard frontend behavior in the existing React, TypeScript, Vite, Tailwind, and shadcn codebase. Match the touched area's patterns instead of introducing new frontend architecture.

## Use When

- Adding or modifying pages, routes, components, hooks, or API modules in `frontend/src`
- Wiring backend data into cases, runs, compare, upload, or docs flows
- Improving responsive behavior, state handling, or UX in existing screens

## Workflow

1. Inspect the target feature, route file, API module, hooks, and nearby UI before editing.
2. Reuse the current feature structure and boundary-safe import patterns.
3. Match the touched area's data-fetching style instead of forcing a repo-wide abstraction change.
4. Preserve app-level shared state flows when relevant, especially selection state threaded through `frontend/src/App.tsx` and `frontend/src/routes/routes.tsx`.
5. Validate with `make frontend-lint` and `pnpm --dir frontend run type-check`.

## Repo Rules

- Use TypeScript and the `@/` path alias.
- Follow `frontend/eslint.config.js`, especially the `eslint-plugin-boundaries` rules.
- Keep route builders in `frontend/src/features/*/routes.tsx` and compose them in `frontend/src/routes/routes.tsx`.
- Keep API calls in `frontend/src/api/api.ts` or feature-local modules such as `frontend/src/features/*/api/*`.
- Keep feature-specific stateful logic in `frontend/src/features/*/hooks/`.
- Reuse `frontend/src/components/shared/*` only for genuinely cross-feature UI.
- Treat `frontend/src/components/ui/**` as low-level primitives, not a place for broad rewrites.
- The repo includes React Query, but several active hooks still use `useEffect` plus local state; follow the local pattern in the touched area.
- Preserve auth and app-shell behavior in `frontend/src/App.tsx`, `frontend/src/auth/**`, and `frontend/src/components/layout/**`.

## Guardrails

- Do not add direct cross-feature imports.
- Do not put API calls directly into presentational components when the feature already has an API or hook layer.
- Do not add a new component library, state library, or test framework as routine work.
- Do not break local HTTPS, logout handling, or API base URL behavior.
