# SimBoard Frontend

The **SimBoard Frontend** is a modern web application built with **React**, **TypeScript**, and **Vite**.

It provides the user interface for browsing, comparing, and analyzing **E3SM** (Energy Exascale
Earth System Model) simulation metadata.

## Tech Stack

- **React 19** — Core UI library
- **TypeScript** — Type-safe development
- **Vite 6** — Lightning-fast build and dev environment
- **Tailwind CSS** + **shadcn** — Styling and components
- **ESLint + Prettier** — Code linting, formatting, and architectural enforcement
- **pnpm** — Dependency management

## Development Guide

For the development guide, see the [root README.md file](../README.md).
It includes information on how to get the frontend service started via bare-metal or Docker.

## Architecture

This frontend follows a **feature-based architecture** enforced by **ESLint architectural boundaries**.

### Feature Organization

- **Features are the primary unit of organization** (e.g. `features/browse`, `features/upload`)
- Domain features such as **`simulations`** and **`machines`** represent core application data
- UI-oriented features (browse, compare, home) may depend on domain features
- **Features must not depend on other features directly**
- API logic lives under `features/*/api`
- Feature-specific hooks live under `features/*/hooks`
- Shared components must be genuinely reusable and belong under `components/shared`

### Architectural Boundaries (ESLint)

The project uses **`eslint-plugin-boundaries`** to enforce architectural rules at import time.

Each file is classified into a single architectural layer based on its path:

- **`routes`** — Application routing and top-level composition
- **`feature`** — Feature modules (browse, upload, compare, etc.)
- **`ui`** — Design-system primitives and low-level UI components
- **`shared`** — Reusable composite components
- **`lib`** — Generic utilities and helpers
- **`types`** — Domain and API contract types
- **`api`** — API clients and adapters

#### Dependency Rules

- **Features are isolated**
  Features may not import or depend on other features directly.

- **Routes compose the application**
  Routes may import features, shared/UI components, and domain types.

- **UI remains presentation-only**
  UI components may depend only on utilities and types.

- **Types are globally safe**
  Type definitions may be imported from any layer.

Any import that violates these rules is reported as an ESLint error, preventing invalid architectural dependencies from being introduced.

## License

For license information, see the [root LICENSE file](../LICENSE).
