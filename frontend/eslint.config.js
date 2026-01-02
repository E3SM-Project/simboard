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
      // build output
      'dist',

      // generated / vendor UI
      'src/components/ui/**',
      'src/components/ui/use-toast.ts',
      'src/components/examples/**',

      // tooling / config files
      'tailwind.config.js',
      'postcss.config.js',
      'vite.config.ts',
    ],
  },
  // --------------------------------------------------
  // Base JS + TS
  // --------------------------------------------------
  js.configs.recommended,
  ...tseslint.configs.recommended,
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

      parserOptions: {
        project: path.resolve('./tsconfig.json'),
        tsconfigRootDir: path.resolve('.'),
      },
    },

    settings: {
      react: { version: 'detect' },

      'import/resolver': {
        typescript: {
          project: path.resolve('./tsconfig.json'),
        },
      },

      // ----------------------------------------------
      // Architectural boundaries (definitions only)
      // ----------------------------------------------
      'boundaries/elements': [
        { type: 'feature', pattern: 'src/features/**' },
        { type: 'ui', pattern: 'src/components/ui/**' },
        { type: 'shared', pattern: 'src/components/shared/**' },
        { type: 'lib', pattern: 'src/lib/**' },
        { type: 'types', pattern: 'src/types/**' },
        { type: 'api', pattern: 'src/api/**' },
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

      // Import hygiene (relative only)
      'no-restricted-imports': [
        'warn',
        {
          patterns: ['../..', '../../*', '../../..', '../../../*', '../../../..', '../../../../*'],
        },
      ],

      // ----------------------------------------------
      // Architectural boundaries
      // ----------------------------------------------
      'boundaries/element-types': [
        'error',
        {
          default: 'disallow',
          rules: [
            {
              from: 'feature',
              allow: ['ui', 'shared', 'lib', 'types', 'api'],
            },
            {
              from: 'routes',
              allow: ['feature', 'ui', 'shared', 'types'],
            },
            {
              from: 'ui',
              allow: ['lib', 'types'],
            },
          ],
        },
      ],
    },
  },
];
