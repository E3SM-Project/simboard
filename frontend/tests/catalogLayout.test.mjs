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

test('simulated duration chooses units without converting mixed calendars to years', async () => {
  const { formatSimulatedDuration, describeSimulatedDuration } = await server.ssrLoadModule(
    '/src/features/catalog/caseUtils.ts',
  );
  const duration = {
    days: 365,
    months: 12,
    years: 1,
    calendars: ['gregorian'],
    calendarAssumed: false,
    partial: false,
    excludedExecutionCount: 0,
  };
  for (const [days, months, years, expected] of [
    [0, 0, 0, '0 days'],
    [6, 6 / 31, 6 / 372, '6 days'],
    [1, 1 / 31, 1 / 372, '1 day'],
    [7, 7 / 31, 7 / 372, '1 week'],
    [28, 1, 1 / 12, '1 month'],
    [365, 12, 1, '1 year'],
    [730, 24, 2, '2 years'],
    [14, null, null, '2 weeks'],
    [10000, null, null, '1,428.57 weeks'],
  ]) {
    assert.equal(formatSimulatedDuration({ ...duration, days, months, years }), expected);
  }
  assert.equal(formatSimulatedDuration(), 'Unavailable');
  assert.equal(
    formatSimulatedDuration({
      ...duration,
      days: 10000,
      months: null,
      years: null,
      calendars: ['gregorian', 'noleap'],
    }),
    '10,000 days',
  );
  assert.equal(
    formatSimulatedDuration({ ...duration, days: null, partial: true }),
    'Unavailable (partial)',
  );
  assert.match(
    describeSimulatedDuration({ ...duration, calendarAssumed: true }),
    /stored Gregorian date convention/,
  );
  assert.match(
    describeSimulatedDuration({ ...duration, partial: true, excludedExecutionCount: 2 }),
    /2 execution\(s\) excluded/,
  );
  assert.match(
    describeSimulatedDuration({ ...duration, calendars: ['gregorian', 'noleap'] }),
    /Mixed model calendars/,
  );
  assert.match(describeSimulatedDuration(duration), /Overlaps and retries count separately/);
});

test('configuration baseline uses most frequent known hash with deterministic hash ties', async () => {
  const { getConfigurationBaseline } = await server.ssrLoadModule(
    '/src/features/catalog/caseUtils.ts',
  );
  const first = { key: 'z-key', caseHash: 'aaa', executionIds: ['1', '2'] };
  const tied = { key: 'a-key', caseHash: 'zzz', executionIds: ['3', '4'] };
  const larger = { key: 'b-key', caseHash: 'bbb', executionIds: ['5', '6', '7'] };
  const missing = { key: 'missing', caseHash: null, executionIds: ['8', '9', '10', '11'] };
  assert.equal(getConfigurationBaseline([first, tied]), first);
  assert.equal(getConfigurationBaseline([tied, first]), first);
  assert.equal(getConfigurationBaseline([first, larger]), larger);
  assert.equal(getConfigurationBaseline([first, missing]), first);
  assert.equal(getConfigurationBaseline([missing]), undefined);
  assert.equal(getConfigurationBaseline([]), undefined);
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

    assert.match(html, /Case group/);
    assert.match(html, /v3\.HR/);
    assert.ok(html.indexOf('Case group') < html.indexOf('More filters'));
    assert.doesNotMatch(html, /More filters \(1\)/);
    assert.doesNotMatch(html, /All campaigns/);
  } finally {
    client.clear();
  }
});

for (const latestExecution of [
  { runEndDate: '2026-09-02T12:00:00Z', runStartDate: '2026-09-01T12:00:00Z' },
  { runEndDate: null, runStartDate: '2026-09-01T12:00:00Z' },
  { runEndDate: null, runStartDate: null },
  null,
]) {
  test(`homepage uses execution dates and preserves layout: ${JSON.stringify(latestExecution)}`, async () => {
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
      latestExecution,
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
        '>Recent Production Cases<',
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
      assert.match(html, /href="\/cases\?simulationType=production"/);
      assert.doesNotMatch(html, />Production Cases<|Last Updated/);
      const productionQuery = client
        .getQueryCache()
        .find({ queryKey: ['cases', 'page'], exact: false });
      assert.deepEqual(productionQuery.queryKey[2], {
        page: 1,
        pageSize: 6,
        simulationType: 'production',
        recentExecution: true,
        sortBy: 'latest_run_activity',
        sortOrder: 'desc',
      });

      const caseTables = [...html.matchAll(/<table\b[^>]*>([\s\S]*?)<\/table>/g)].slice(0, 2);
      assert.equal(caseTables.length, 2);
      for (const [markup, table] of caseTables) {
        assert.match(markup, /<table\b[^>]*class="[^"]*\bmin-w-\[1100px\] table-fixed\b/);
        const tablePosition = html.indexOf(markup);
        assert.match(html.slice(0, tablePosition), /<div class="relative w-full overflow-auto">$/);
        const headers = [...table.matchAll(/<th\b[^>]*>(.*?)<\/th>/g)].map((match) => match[1]);
        assert.deepEqual(headers, [
          'Case Name',
          'Last Execution',
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
          latestExecution?.runEndDate || latestExecution?.runStartDate
            ? new Date(
                latestExecution.runEndDate ?? latestExecution.runStartDate,
              ).toLocaleDateString()
            : '—',
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
}

test('recent production cases explain an empty result', async () => {
  const { ProductionCasesTable } = await server.ssrLoadModule(
    '/src/features/home/components/ProductionCasesTable.tsx',
  );
  const client = new QueryClient();
  client.setQueryDefaults(['cases', 'page'], {
    initialData: { items: [], total: 0, page: 1, pageSize: 6 },
  });

  try {
    const html = renderToStaticMarkup(
      createElement(QueryClientProvider, { client }, createElement(ProductionCasesTable)),
    );
    assert.match(
      html,
      /No production cases have a completed execution in the last six calendar months\./,
    );
  } finally {
    client.clear();
  }
});

test('simulation date sorting handles year zero, ties, and does not mutate input', async () => {
  const { sortCaseExecutions } = await server.ssrLoadModule('/src/features/catalog/caseUtils.ts');
  const executions = Object.freeze([
    { summary: { id: 'c', simulationStartDate: '2018-06-15' } },
    { summary: { id: 'b', simulationStartDate: '0000-01-01' } },
    { summary: { id: 'a', simulationStartDate: '0000-01-01' } },
  ]);

  assert.deepEqual(
    sortCaseExecutions(executions, { key: 'simulation', direction: 'asc' }).map(
      ({ summary }) => summary.id,
    ),
    ['a', 'b', 'c'],
  );
  assert.deepEqual(
    sortCaseExecutions(executions, { key: 'simulation', direction: 'desc' }).map(
      ({ summary }) => summary.id,
    ),
    ['c', 'a', 'b'],
  );
  assert.deepEqual(
    executions.map(({ summary }) => summary.id),
    ['c', 'b', 'a'],
  );
});

test('run date sorting uses end/start fallback and keeps missing or invalid dates last', async () => {
  const { sortCaseExecutions } = await server.ssrLoadModule('/src/features/catalog/caseUtils.ts');
  const executions = [
    { summary: { id: 'missing' } },
    { summary: { id: 'invalid' }, details: { runEndDate: 'bad-date' } },
    {
      summary: { id: 'later' },
      details: { runStartDate: '2026-01-01T00:00:00Z', runEndDate: '2026-01-03T00:00:00Z' },
    },
    { summary: { id: 'earlier' }, details: { runStartDate: '2026-01-02T00:00:00Z' } },
  ];

  assert.deepEqual(
    sortCaseExecutions(executions, { key: 'run', direction: 'asc' }).map(
      ({ summary }) => summary.id,
    ),
    ['earlier', 'later', 'invalid', 'missing'],
  );
  assert.deepEqual(
    sortCaseExecutions(executions, { key: 'run', direction: 'desc' }).map(
      ({ summary }) => summary.id,
    ),
    ['later', 'earlier', 'invalid', 'missing'],
  );
  assert.deepEqual(sortCaseExecutions([], { key: 'run', direction: 'asc' }), []);
});
