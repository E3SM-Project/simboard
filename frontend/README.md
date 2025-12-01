# SimBoard Frontend

The **SimBoard Frontend** is a modern web application built with **React**, **TypeScript**, and **Vite**.

It provides the user interface for browsing, comparing, and analyzing **E3SM** (Energy Exascale Earth System Model) simulation metadata.

---

## 🚀 Developer Quickstart

Get started in **five simple commands**:

```bash
# 1. Navigate to the frontend directory
cd frontend

# 2. Install dependencies
make install

# 3. Start the development server
make dev

# 4. Open the app in your browser
open http://127.0.0.1:5173

# 5. Run lint and type checks (optional)
make lint
make type-check
```

The development server uses **Vite** with hot module reloading (HMR).
Changes to components, styles, or configuration apply instantly in your browser.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [🧰 Makefile Commands](#-makefile-commands)

  - [Setup & Environment](#setup--environment)
  - [Development & Build](#development--build)
  - [Code Quality](#code-quality)
  - [Example Workflow](#example-workflow)

- [Expanding the ESLint Configuration](#expanding-the-eslint-configuration)
- [License](#license)

---

## Tech Stack

- **React 19** — Core UI library
- **TypeScript** — Type-safe development
- **Vite 6** — Lightning-fast build and dev environment
- **Tailwind CSS** + **shadcn** — Styling and components
- **ESLint + Prettier** — Code linting and formatting
- **pnpm** — Dependency management

---

## 🧰 Makefile Commands

This project includes a **frontend Makefile** that wraps common commands for development and CI.
All commands use **pnpm** under the hood.

Run `make help` to view available commands.

### Setup & Environment

| Command        | Description                                 | Equivalent Command                |
| -------------- | ------------------------------------------- | --------------------------------- |
| `make install` | Install all frontend dependencies via pnpm. | `pnpm install`                    |
| `make clean`   | Remove build artifacts and node_modules.    | `rm -rf node_modules dist .turbo` |

---

### Development & Build

| Command           | Description                                 | Equivalent Command |
| ----------------- | ------------------------------------------- | ------------------ |
| `make dev`        | Start the Vite development server with HMR. | `pnpm dev`         |
| `make build`      | Build the project for production.           | `pnpm build`       |
| `make preview`    | Preview the production build locally.       | `pnpm preview`     |
| `make type-check` | Run TypeScript type checking.               | `pnpm type-check`  |

---

### Code Quality

| Command           | Description                                    | Equivalent Command |
| ----------------- | ---------------------------------------------- | ------------------ |
| `make lint`       | Run ESLint checks on all source files.         | `pnpm lint`        |
| `make fix`        | Automatically fix lint issues.                 | `pnpm lint:fix`    |
| `make ci`         | Run CI checks (lint + type-check).             | `pnpm ci`          |
| `make pre-commit` | Run pre-commit checks (lint:fix + type-check). | `pnpm pre-commit`  |

---

### Example Workflow

```bash
# 1. Install dependencies
make install

# 2. Start local dev server
make dev

# 3. Build for production
make build

# 4. Run quality checks
make lint
make type-check
```

---

## Expanding the ESLint Configuration

If you are developing a production-grade application, you can enable **type-aware lint rules** for better code quality and consistency.

```js
export default tseslint.config({
  extends: [
    // Replace basic recommendations with stricter, type-aware configs
    ...tseslint.configs.recommendedTypeChecked,
    // Optionally enable stricter or stylistic rules
    ...tseslint.configs.strictTypeChecked,
    ...tseslint.configs.stylisticTypeChecked,
  ],
  languageOptions: {
    parserOptions: {
      project: ['./tsconfig.node.json', './tsconfig.app.json'],
      tsconfigRootDir: import.meta.dirname,
    },
  },
});
```

You can also install React-specific ESLint plugins for improved linting:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x';
import reactDom from 'eslint-plugin-react-dom';

export default tseslint.config({
  plugins: {
    'react-x': reactX,
    'react-dom': reactDom,
  },
  rules: {
    ...reactX.configs['recommended-typescript'].rules,
    ...reactDom.configs.recommended.rules,
  },
});
```

## License

For license information, see the [root LICENSE file](../LICENSE).
