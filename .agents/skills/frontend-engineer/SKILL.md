---
name: frontend-engineer
description: Build or modify SimBoard frontend UI in the existing React, TypeScript, Vite, Tailwind, and shadcn codebase while respecting feature boundaries and existing data-flow patterns.
---

# Frontend Engineer

## Purpose

Implement SimBoard frontend behavior and UI in code. Work inside the existing React 19 + TypeScript + Vite app without introducing new architectural patterns unless the repo already uses them in the touched area.

## When To Use

- Adding or modifying pages, routes, components, hooks, or API modules in `frontend/src`
- Wiring new backend data into browse, compare, upload, docs, or simulation detail flows
- Improving responsive behavior, loading/error states, and interaction details in existing screens
- Refactoring frontend code to better fit the repo's current architecture

## Inputs Expected

- The requested user-facing behavior
- Target routes, screens, or feature directories
- Relevant backend contract or endpoint details
- Acceptance criteria, visual constraints, and any auth requirements

## Outputs Required

- Minimal code changes in `frontend/src/**`
- Any required backend follow-up called out explicitly
- Validation notes for lint/type-check or other commands that were run
- Brief explanation of the chosen implementation approach when multiple options exist

## Repo-Specific Conventions

- Use TypeScript and the `@/` path alias defined in `frontend/tsconfig.json`.
- Follow the frontend boundary rules in `frontend/eslint.config.js`.
- Put route definitions in feature route files such as `frontend/src/features/*/routes.tsx`, and compose them in `frontend/src/routes/routes.tsx`.
- Keep API calls in `frontend/src/api/api.ts` or feature-local modules like `frontend/src/features/simulations/api/api.ts`.
- Keep feature-specific stateful logic in `frontend/src/features/*/hooks/`.
- Reuse `frontend/src/components/shared/*` for UI that is genuinely cross-feature. Do not move feature-specific UI there just to avoid imports.
- Treat `frontend/src/components/ui/**` as low-level primitives. Extend or reuse them rather than inventing parallel button/input/modal stacks.
- Inspect the nearby feature before choosing data-fetching style. The repo includes `@tanstack/react-query`, but several current hooks still use `useEffect` plus local state. Match the touched area instead of forcing a new abstraction.
- Preserve existing auth and app-shell wiring in `frontend/src/App.tsx`, `frontend/src/auth/**`, and `frontend/src/components/layout/**`.
- Prefer `make frontend-lint` and `pnpm --dir frontend run type-check` after TypeScript changes.

## Constraints / Anti-Patterns

- Do not add direct cross-feature imports.
- Do not put API calls directly into presentational components when the feature already has an API/hook layer.
- Do not add a new component library, state library, or frontend test framework as part of routine work.
- Do not rewrite generated-style UI primitives in `components/ui` unless the task specifically requires it.
- Do not break local HTTPS assumptions in `frontend/vite.config.ts` or auth/logout behavior in `frontend/src/api/api.ts`.
- Do not leave placeholder UI in production-facing routes unless the task is explicitly for scaffolding.

## Example Task

Implement a richer `/docs` experience by replacing the placeholder `frontend/src/features/docs/DocsPage.tsx`, keeping the route in `frontend/src/features/docs/routes.tsx`, and reusing shared layout and existing UI primitives rather than creating a separate mini-app.
