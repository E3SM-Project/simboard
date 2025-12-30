import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import boundaries from 'eslint-plugin-boundaries';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import simpleImportSort from 'eslint-plugin-simple-import-sort';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import path from 'node:path';

export default [
  // --------------------------------------------------
  // Ignore patterns
  // --------------------------------------------------
  {
    ignores: [
      'dist',
      'src/components/ui/**',
      'src/components/ui/use-toast.ts',
      'src/components/examples/**', // auto-generated examples
    ],
  },

  // --------------------------------------------------
  // Base JS + TS
  // --------------------------------------------------
  js.configs.recommended,
  // TypeScript recommended (array of flat configs)
  ...tseslint.configs.recommended,
  // Prettier: disable conflicting stylistic rules
  prettier,

  // --------------------------------------------------
  // Frontend project rules
  // --------------------------------------------------
  {
    files: ['src/**/*.{js,jsx,ts,tsx}'],

    languageOptions: {
      parser: tseslint.parser,
      ecmaVersion: 'latest',
      sourceType: 'module',

      globals: {
        ...globals.browser,
        window: 'readonly',
        document: 'readonly',
      },

      // REQUIRED for monorepo + path aliases
      parserOptions: {
        project: path.resolve('./tsconfig.json'),
        tsconfigRootDir: path.resolve('.'),
      },
    },

    settings: {
      react: { version: 'detect' },

      // REQUIRED: resolve @/ aliases
      'import/resolver': {
        typescript: {
          project: path.resolve('./tsconfig.json'),
        },
      },

      // ----------------------------------------------
      // Architectural boundaries (feature-based)
      // ----------------------------------------------
      'boundaries/elements': [
        // Feature modules (entire subtree)
        { type: 'feature', pattern: 'src/features/**' },

        // Design system / UI primitives
        { type: 'ui', pattern: 'src/components/ui/**' },

        // Shared composite components
        { type: 'shared', pattern: 'src/components/shared/**' },

        // Utilities
        { type: 'lib', pattern: 'src/lib/**' },

        // Domain / API contract types
        { type: 'types', pattern: 'src/types/**' },

        // API client & adapters
        { type: 'api', pattern: 'src/api/**' },

        // App-level routing & composition
        { type: 'routes', pattern: 'src/routes/**' },
      ],
    },

    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      'simple-import-sort': simpleImportSort,
      boundaries,
    },

    rules: {
      // React
      ...react.configs.recommended?.rules,
      ...reactHooks.configs.recommended?.rules,
      'react/react-in-jsx-scope': 'off',

      // Fast refresh
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // Imports
      'simple-import-sort/imports': 'error',
      'simple-import-sort/exports': 'error',

      // TypeScript
      '@typescript-eslint/no-unused-vars': 'warn',
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      '@typescript-eslint/no-explicit-any': 'warn',

      // Import hygiene:
      // - Prefer absolute imports (@/) over deep relative paths
      // - Discourage deep cross-feature imports (boundaries handle final enforcement)
      'no-restricted-imports': [
        'warn',
        {
          patterns: [
            // --------------------------------------------
            // Deep relative imports (fragile)
            // --------------------------------------------
            '../..',
            '../../*',
            '../../..',
            '../../../*',
            '../../../..',
            '../../../../*',

            // --------------------------------------------
            // Deep cross-feature imports (early guardrail)
            // Allow domain feature: simulations
            // --------------------------------------------
            '@/features/*/*/*',
            '!@/features/simulations/**',
            '!@/features/machines/**',
          ],
        },
      ],
      // ----------------------------------------------
      // Architectural enforcement
      // ----------------------------------------------
      'boundaries/element-types': [
        'error',
        {
          default: 'allow',
          rules: [
            {
              from: 'feature',
              disallow: ['feature'],
              message:
                'Features must not import other features. Use shared components or hooks instead.',
            },
            {
              from: 'hook',
              disallow: ['api-client'],
              message: 'Hooks must not import the API client directly. Use feature API modules.',
            },
            {
              from: 'ui',
              disallow: ['feature-api'],
              message:
                'UI components must not import feature API modules directly. Use hooks instead.',
            },
          ],
        },
      ],
    },
  },
];
