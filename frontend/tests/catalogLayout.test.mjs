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

test('configuration token differences preserve values and leave shared tokens unmarked', async () => {
  const { getConfigurationDiffParts } = await server.ssrLoadModule(
    '/src/features/catalog/caseUtils.ts',
  );
  for (const [reference, value, changedText] of [
    ['20TRSOI_EAM%CMIP6_ELM', 'SSP245SOI_EAM%CMIP6_ELM', 'SSP245SOI'],
    ['A_B_C', 'X_B_Y', 'XY'],
    ['A_B_C', 'A_X_B_C', 'X_'],
    ['A_B_C', 'A_C', 'A_C'],
    ['A_B', 'A%B', '%'],
    ['v3.1', 'v3.2', '2'],
    ['/root/old/model', '/root/new/model', 'new'],
    ['WCYCL20TR', 'WCYCLSSP245', 'WCYCLSSP245'],
    ['A  B', 'A B', ' '],
    ['A_B', 'A_B', ''],
    [null, 'A_B', 'A_B'],
    ['A_B', '', ''],
  ]) {
    const parts = getConfigurationDiffParts(value, reference);
    assert.equal(parts.map((part) => part.text).join(''), value);
    assert.equal(
      parts
        .filter((part) => part.changed)
        .map((part) => part.text)
        .join(''),
      changedText,
    );
  }
  const longReference = 'A_'.repeat(1000);
  const longValue = 'B_'.repeat(1000);
  assert.deepEqual(getConfigurationDiffParts(longValue, longReference), [
    { text: longValue, changed: true },
  ]);
  assert.deepEqual(getConfigurationDiffParts('', 'A_B'), []);
});

test('execution comparison normalizes missing values and artifact identities', async () => {
  const { comparisonValueText } = await server.ssrLoadModule('/src/features/compare/utils.tsx');
  for (const value of [null, undefined, '', []]) {
    assert.equal(comparisonValueText(value), '—');
  }
  assert.equal(comparisonValueText(0), '0');
  assert.equal(comparisonValueText(false), 'false');
  assert.equal(comparisonValueText(['b', 'a']), comparisonValueText(['a', 'b']));
  assert.equal(
    comparisonValueText([{ id: 'a', uri: '/output/shared', createdAt: '2026-01-01' }]),
    comparisonValueText([{ id: 'b', uri: '/output/shared', createdAt: '2026-02-02' }]),
  );
  assert.notEqual(
    comparisonValueText([{ uri: '/output/a' }]),
    comparisonValueText([{ uri: '/output/b' }]),
  );
});

test('configuration table labels its reference and marks only changed values', async () => {
  const { CaseConfigurationDetails } = await server.ssrLoadModule(
    '/src/features/catalog/components/CaseConfiguration.tsx',
  );
  const { MemoryRouter } = await server.ssrLoadModule('react-router-dom');
  const field = (value) => ({
    source:
      value == null ? null : { value, executionUuid: 'run-1', executionId: 'run-1', runDate: null },
    differences: [],
    missingExecutionIds: [],
  });
  const reference = '20TRSOI_EAM%CMIP6_ELM';
  const groups = [reference, reference, 'SSP245SOI_EAM%CMIP6_ELM', null].map((value, index) => ({
    key: `hash-${index}`,
    caseHash: `hash-${index}`,
    executionIds: index === 0 ? ['run-1', 'run-2'] : ['run-3'],
    configuration: { compset_long_name: field(value) },
  }));
  groups[0].configuration.compset_long_name.differences.push({
    value: '20TRSOI_EAM%CMIP5_ELM',
    executionUuid: 'reference-alternate',
    executionId: 'reference-alternate',
    runDate: null,
  });
  groups[2].configuration.compset_long_name.differences.push({
    value: 'SSP370SOI_EAM%CMIP6_ELM',
    executionUuid: 'other-alternate',
    executionId: 'other-alternate',
    runDate: null,
  });
  const html = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(CaseConfigurationDetails, {
        record: { configurationGroups: groups },
        identity: { machineName: 'machine', hpcUsername: 'user', caseName: 'case' },
      }),
    ),
  );
  const headers = [...html.matchAll(/<th\b[^>]*scope="col"[^>]*>([\s\S]*?)<\/th>/g)].map(
    (match) => match[1],
  );
  const disclosure = html.match(/<details\b[^>]*id="case-configuration-differences"[^>]*>/)?.[0];
  assert.ok(disclosure);
  assert.doesNotMatch(disclosure, /\bopen(?:=|\s|>)/);
  assert.match(html, /<summary\b[^>]*><h3\b[^>]*id="case-configuration-differences-title"/);
  assert.match(headers[1], /Reference/);
  assert.equal(headers.filter((header) => header.includes('Reference')).length, 1);
  const cells = [...html.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g)].map((match) => match[1]);
  assert.doesNotMatch(cells[0], /<mark/);
  assert.match(cells[0], /20TRSOI_EAM%CMIP5_ELM/);
  assert.doesNotMatch(cells[1], /<mark/);
  assert.match(cells[2], /<mark\b[^>]*>SSP245SOI<\/mark>/);
  assert.match(cells[2], /<mark\b[^>]*>SSP370SOI<\/mark>/);
  assert.match(cells[2], /class="sr-only select-none">Differs from reference column\./);
  assert.doesNotMatch(html, /<mark\b[^>]*aria-label=/);
  assert.doesNotMatch(cells[2], /<mark\b[^>]*>[^<]*(?:EAM|CMIP6|ELM)/);
  assert.match(cells[2], /title="Reference value: 20TRSOI_EAM%CMIP6_ELM"/);
  assert.match(cells[3], /<mark\b[^>]*>Unavailable<\/mark>/);
});

test('case metadata keeps compset alias and long name aligned with execution fields', async () => {
  const { CaseConfigurationSummary } = await server.ssrLoadModule(
    '/src/features/catalog/components/CaseConfiguration.tsx',
  );
  const execution = { compsetAlias: 'F2010', compsetLongName: '2000_EAM_ELM_MPASSI_MPASO' };
  const values = {
    compset_alias: execution.compsetAlias,
    compset_long_name: execution.compsetLongName,
  };
  const record = {
    machineNames: ['machine'],
    hpcUsernames: ['user'],
    latestExecution: null,
    configurationGroups: [
      {
        key: 'one',
        caseHash: 'aaa',
        executionIds: ['run-1'],
        configuration: Object.fromEntries(
          Object.entries(values).map(([key, value]) => [
            key,
            {
              source: { value, executionUuid: 'run-1', executionId: 'run-1' },
              differences: [],
              missingExecutionIds: [],
            },
          ]),
        ),
      },
    ],
  };
  for (const sharedConfiguration of [
    undefined,
    Object.fromEntries(
      Object.entries(values).map(([key, value]) => [
        key,
        { value, varies: false, incomplete: false },
      ]),
    ),
  ]) {
    const html = renderToStaticMarkup(
      createElement(CaseConfigurationSummary, { record: { ...record, sharedConfiguration } }),
    );
    const fields = Object.fromEntries(
      [...html.matchAll(/<dt\b[^>]*>([^<]+)<\/dt><dd\b[^>]*>([\s\S]*?)<\/dd>/g)].map((match) => [
        match[1],
        match[2],
      ]),
    );
    assert.equal(fields['Compset Alias'], execution.compsetAlias);
    assert.equal(fields['Compset Long Name'], execution.compsetLongName);
  }
});

test('case summary links only differing configuration fields to compact comparison rows', async () => {
  const { CaseConfigurationSummary, CaseConfigurationDetails } = await server.ssrLoadModule(
    '/src/features/catalog/components/CaseConfiguration.tsx',
  );
  const { MemoryRouter } = await server.ssrLoadModule('react-router-dom');
  const field = (value) => ({
    source:
      value == null ? null : { value, executionUuid: 'run-1', executionId: 'run-1', runDate: null },
    differences: [],
    missingExecutionIds: value == null ? ['run-1'] : [],
  });
  const configuration = {
    compset_alias: field('shared-alias'),
    compset_long_name: field('shared-long-name'),
    grid_alias: field('shared-grid'),
    grid_long_name: field('shared-grid-long'),
  };
  const first = { key: 'one', caseHash: 'aaa', executionIds: ['run-1'], configuration };
  const record = {
    machineNames: ['machine'],
    hpcUsernames: ['user'],
    latestExecution: null,
    sharedConfiguration: Object.fromEntries(
      Object.entries(configuration).map(([name, entry]) => [
        name,
        { value: entry.source.value, varies: false, incomplete: false },
      ]),
    ),
  };
  const identity = { machineName: 'machine', hpcUsername: 'user', caseName: 'case' };
  for (const changedField of [
    'compset_alias',
    'compset_long_name',
    'grid_alias',
    'grid_long_name',
    null,
  ]) {
    const second = {
      ...first,
      key: 'two',
      caseHash: 'bbb',
      configuration: changedField
        ? { ...configuration, [changedField]: field(null) }
        : configuration,
    };
    const current = { ...record, configurationGroups: [first, second] };
    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        null,
        createElement(
          'div',
          null,
          createElement(CaseConfigurationSummary, { record: current, identity }),
          createElement(CaseConfigurationDetails, { record: current, identity }),
        ),
      ),
    );
    assert.doesNotMatch(html, /Expand metadata|Baseline:|data-configuration-group/);
    if (changedField) {
      assert.match(html, /Only configuration fields that differ between case hashes are shown\./);
      assert.match(html, /Case hashes identify CIME case instances\./);
      assert.match(html, /1 execution/);
      const body = html.match(/<tbody\b[^>]*>([\s\S]*?)<\/tbody>/)[1];
      assert.match(html, /href="#case-configuration-differences"/);
      assert.match(html, new RegExp(`aria-controls="case-configuration-${changedField}"`));
      assert.match(html, /id="case-configuration-differences" tabindex="-1"/);
      assert.match(body, new RegExp(`id="case-configuration-${changedField}"`));
      assert.equal((body.match(/scope="row"/g) ?? []).length, 1);
      assert.match(body, /Unavailable/);
    } else {
      assert.doesNotMatch(html, /Differs by case hash/);
      assert.doesNotMatch(html, /data-case-configuration|<table/);
    }
  }
  for (const configurationGroups of [undefined, [], [first]]) {
    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        null,
        createElement(CaseConfigurationDetails, {
          record: { ...record, configurationGroups },
          identity,
        }),
      ),
    );
    assert.equal(html, '');
  }
  const varyingConfiguration = {
    ...configuration,
    grid_alias: {
      ...configuration.grid_alias,
      differences: [
        { value: 'later-grid', executionUuid: 'run-2', executionId: 'run-2', runDate: null },
      ],
    },
  };
  const html = renderToStaticMarkup(
    createElement(
      MemoryRouter,
      null,
      createElement(CaseConfigurationSummary, {
        record: {
          ...record,
          configurationGroups: [
            { ...first, configuration: varyingConfiguration },
            { ...first, key: 'two', caseHash: 'bbb' },
          ],
        },
        identity,
      }),
    ),
  );
  assert.doesNotMatch(html, /Differs by case hash/);
  assert.match(html, /title="Source execution: run-1"/);
  assert.match(html, /Changes within Case Hash/);
  assert.match(html, /later-grid/);
  assert.match(html, /href="\/cases\/machine\/user\/case\/run-2"/);
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
