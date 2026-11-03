import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

let server;

before(async () => {
  server = await createServer({
    mode: 'test',
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
