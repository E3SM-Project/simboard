# SimBoard Frontend

The **SimBoard Frontend** is a modern web application built with **React**, **TypeScript**, and **Vite**.

It provides the user interface for browsing, comparing, and analyzing **E3SM** (Energy Exascale
Earth System Model) simulation metadata.

## Tech Stack

> ℹ️ **Note:** The frontend runs as a Docker container.

- **React 19** — Core UI library
- **TypeScript** — Type-safe development
- **Vite 6** — Lightning-fast build and dev environment
- **Tailwind CSS** + **shadcn** — Styling and components
- **ESLint + Prettier** — Code linting and formatting
- **pnpm** — Dependency management

## Development Guide

For the development guide, see the [root README.md file](../README.md). It includes
information on how to get the frontend service started via Docker.

## 🧰 Frontend Makefile Commands

This directory includes a **frontend Makefile**.

In `/frontend`, run `make help` to view all available commands

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
