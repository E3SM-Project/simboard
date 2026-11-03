import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, test } from 'node:test';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

let server;
let cacheDir;

before(async () => {
  cacheDir = await mkdtemp(path.join(tmpdir(), 'simboard-ssr-'));
  server = await createServer({
    mode: 'test',
    cacheDir,
    define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('https://api.example.test') },
    server: { middlewareMode: true, watch: null },
    appType: 'custom',
    ssr: {
      noExternal: ['react-router-dom', 'react-router'],
      resolve: { conditions: ['module-sync', 'node'] },
    },
  });
});

after(async () => {
  await server?.close();
  if (cacheDir) await rm(cacheDir, { recursive: true, force: true });
});

test('Case Group stays visible without opening or counting as an advanced filter', async () => {
  const { CasesPage } = await server.ssrLoadModule('/src/features/catalog/CasesPage.tsx');
  const { MemoryRouter } = await server.ssrLoadModule('react-router-dom');
  const client = new QueryClient();
  client.setQueryDefaults(['cases', 'page'], {
    initialData: { items: [], total: 0, page: 1, pageSize: 25 },
  });

  try {
    const html = renderToStaticMarkup(
      createElement(
        QueryClientProvider,
        { client },
        createElement(
          MemoryRouter,
          { initialEntries: ['/cases?caseGroup=v3.HR'] },
          createElement(CasesPage),
        ),
      ),
    );

    assert.match(html, /Case Group/);
    assert.match(html, /v3\.HR/);
    assert.ok(html.indexOf('Case Group') < html.indexOf('More filters'));
    assert.doesNotMatch(html, /More filters \(1\)/);
    assert.doesNotMatch(html, /All campaigns/);
  } finally {
    client.clear();
  }
});

test('homepage puts workflows after cases and statistics above the footer', async () => {
  const { HomePage } = await server.ssrLoadModule('/src/features/home/HomePage.tsx');
  const { MemoryRouter } = await server.ssrLoadModule('react-router-dom');
  const client = new QueryClient();
  const caseRecord = {
    id: 'case-1',
    name: 'test.case',
    caseGroup: 'v3.HR',
    machineName: 'chrysalis',
    hpcUsername: 'test.user',
    executionCount: 7,
    updatedAt: '2026-10-01T12:00:00Z',
  };
  client.setQueryData(['catalog', 'overview'], {
    totalCases: 42,
    totalExecutions: 84,
    recentCases: [caseRecord],
    machineCounts: {},
  });
  client.setQueryDefaults(['cases', 'page'], {
    initialData: { items: [caseRecord], total: 1, page: 1, pageSize: 6 },
  });

  try {
    const html = renderToStaticMarkup(
      createElement(
        QueryClientProvider,
        { client },
        createElement(MemoryRouter, null, createElement(HomePage, { machines: [], sites: [] })),
      ),
    );
    const headings = [
      'Explore E3SM Simulations',
      '>Production Cases<',
      '>Recent Cases<',
      '>Common Workflows<',
      '>Sites and Machines<',
      '>Catalog at a glance<',
      '<footer',
    ].map((text) => html.indexOf(text));

    assert.ok(headings.every((position) => position >= 0));
    assert.deepEqual(
      headings,
      [...headings].sort((left, right) => left - right),
    );
    assert.match(html, />42<\/dd>/);
    assert.match(html, />84<\/dd>/);

    const caseTables = [...html.matchAll(/<table\b[^>]*>([\s\S]*?)<\/table>/g)].slice(0, 2);
    assert.equal(caseTables.length, 2);
    for (const [, table] of caseTables) {
      const headers = [...table.matchAll(/<th\b[^>]*>(.*?)<\/th>/g)].map((match) => match[1]);
      assert.deepEqual(headers, [
        'Case Name',
        'Last Updated',
        'Details',
        'Case Group',
        'Machine',
        'HPC Username',
        'Executions',
      ]);
      const cells = [...table.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g)].map((match) =>
        match[1].replace(/<[^>]*>/g, '').trim(),
      );
      assert.deepEqual(cells, [
        caseRecord.name,
        new Date(caseRecord.updatedAt).toLocaleDateString(),
        'Open',
        caseRecord.caseGroup,
        caseRecord.machineName,
        caseRecord.hpcUsername,
        '7',
      ]);
      assert.match(table, /href="\/cases\/chrysalis\/test.user\/test.case"/);
    }
  } finally {
    client.clear();
  }
});
