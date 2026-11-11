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

test('execution discovery distinguishes known metadata without inferring changes from hashes', async () => {
  const {
    getExecutionDiscoveryContext,
    getExecutionSummary,
    matchesExecutionSearch,
    hasCaseHashContext,
  } = await server.ssrLoadModule('/src/lib/catalog/executionDiscovery.ts');
  const candidate = (id, details = {}, caseHash = 'same') => ({
    summary: {
      id,
      executionId: `run-${id}`,
      caseHash,
      simulationStartDate: '0001-01-01',
      simulationEndDate: null,
    },
    details,
  });
  const first = candidate('1', {
    machineName: 'Machine A',
    initializationType: 'branch',
    compsetAlias: 'COMMON',
    runStartDate: '2026-10-01T12:00:00Z',
  });
  const unknown = candidate('2', { machineName: 'Unknown', initializationType: null });
  const uniform = getExecutionDiscoveryContext([first, unknown]);
  assert.deepEqual(uniform.varyingFields, []);
  assert.equal(getExecutionSummary(first, uniform).context, '');
  assert.equal(getExecutionSummary(unknown, uniform).simulationPeriod, '0001-01-01 → —');
  assert.equal(hasCaseHashContext([first.summary, unknown.summary]), false);
  const second = candidate(
    '3',
    {
      machineName: 'Machine B',
      initializationType: 'hybrid',
      compsetAlias: 'COMMON',
      runStartDate: '2026-10-02T12:00:00Z',
    },
    'other',
  );
  const missing = candidate('4', {}, null);
  const discovery = getExecutionDiscoveryContext([first, second, missing]);
  assert.deepEqual(discovery.varyingFields, ['machineName', 'initializationType']);
  assert.match(
    getExecutionSummary(second, discovery).context,
    /Run: 2026-10-02 · Machine: Machine B · Initialization: hybrid · Hash: other/,
  );
  assert.equal(getExecutionSummary(missing, discovery).context, 'Missing Case Hash');
  assert.doesNotMatch(getExecutionSummary(first, discovery).context, /COMMON|configuration/i);
  for (const query of ['run-3', 'Machine B', 'hybrid', '0001-01-01', 'other']) {
    assert.equal(matchesExecutionSearch(second, discovery, query), true);
  }
  assert.equal(matchesExecutionSearch(missing, discovery, 'missing case hash'), true);
  assert.equal(matchesExecutionSearch(first, uniform, 'same'), true);
  assert.equal(matchesExecutionSearch(first, uniform, 'COMMON'), true);
  assert.equal(matchesExecutionSearch(first, uniform, '2026-10-01'), true);
  assert.equal(
    matchesExecutionSearch(
      { ...first, details: { compsetLongName: 'UNIFORM_LONG_COMPSET' } },
      uniform,
      'UNIFORM_LONG_COMPSET',
    ),
    true,
  );
  assert.deepEqual(getExecutionDiscoveryContext([]).varyingFields, []);
  assert.equal(hasCaseHashContext([missing.summary]), false);
  assert.equal(hasCaseHashContext([first.summary, missing.summary]), true);
});

test('case selection cap and display order preserve reference through edits', async () => {
  const { toggleCaseExecution, reconcileExecutionOrder } = await server.ssrLoadModule(
    '/src/lib/catalog/executionDiscovery.ts',
  );
  let ids = [];
  for (const id of ['a', 'b', 'c', 'd', 'e', 'f']) ids = toggleCaseExecution(ids, id);
  assert.deepEqual(ids, ['a', 'b', 'c', 'd', 'e']);
  ids = toggleCaseExecution(ids, 'b');
  ids = toggleCaseExecution(ids, 'f');
  assert.deepEqual(ids, ['a', 'c', 'd', 'e', 'f']);
  const order = reconcileExecutionOrder(['c', 'a', 'd', 'e', 'b'], ids);
  assert.deepEqual(order, ['c', 'a', 'd', 'e', 'f']);
  assert.deepEqual(reconcileExecutionOrder(order, ['a', 'f']), ['a', 'f']);
  assert.deepEqual(reconcileExecutionOrder(order, []), []);
  assert.deepEqual(toggleCaseExecution(['a'], 'a'), []);
});

test('execution durations and run dates handle year zero, missing dates, and ranges', async () => {
  const { formatExecutionDuration } = await server.ssrLoadModule(
    '/src/features/catalog/caseUtils.ts',
  );
  const { formatRunDateRange } = await server.ssrLoadModule(
    '/src/lib/catalog/executionDiscovery.ts',
  );
  for (const [start, end, expected] of [
    ['2015-01-01', '2015-01-02', '1 day'],
    ['0000-02-28', '0000-03-01', '2 days'],
    ['0001-01-01', '0002-01-01', '1 year'],
    ['2015-01-01', '2015-01-01', '0 days'],
    ['2015-01-02', '2015-01-01', '—'],
    ['invalid', '2015-01-01', '—'],
    ['2015-01-01', null, '—'],
  ])
    assert.equal(
      formatExecutionDuration({ simulationStartDate: start, simulationEndDate: end }),
      expected,
    );
  assert.equal(formatRunDateRange(), '—');
  assert.equal(formatRunDateRange('2026-01-01T12:00:00Z'), '2026-01-01');
  assert.equal(formatRunDateRange(null, '2026-01-02T12:00:00Z'), '2026-01-02');
  assert.equal(formatRunDateRange('2026-01-01T12:00:00Z', '2026-01-01T13:00:00Z'), '2026-01-01');
  assert.equal(
    formatRunDateRange('2026-01-01T12:00:00Z', '2026-01-02T13:00:00Z'),
    '2026-01-01 → 2026-01-02',
  );
});

test('hash-group differences compare known configuration values and merge missing-hash observations', async () => {
  const { getCaseHashConfigurationDifferences } = await server.ssrLoadModule(
    '/src/features/catalog/caseUtils.ts',
  );
  const group = (caseHash, values, key = caseHash) => ({
    key,
    caseHash,
    executionIds: caseHash === 'a' ? ['1', '2', '3'] : ['4'],
    configuration: Object.fromEntries(
      Object.entries(values).map(([field, value]) => [
        field,
        { source: value == null ? null : { value }, differences: [], missingExecutionIds: [] },
      ]),
    ),
  });
  const reference = group('a', {
    compset_alias: 'COMMON',
    compset_long_name: 'COMMON_LONG',
    grid_alias: 'grid_A',
    grid_long_name: 'grid_long_A',
    git_tag: 'v3',
  });
  const identical = group('b', {
    compset_alias: 'COMMON',
    compset_long_name: 'COMMON_LONG',
    grid_alias: 'grid_A',
    grid_long_name: 'grid_long_A',
    git_tag: 'v3',
  });
  const unknown = group(
    null,
    { compset_alias: null, grid_alias: 'Unknown', git_tag: 'Unavailable' },
    'missing:one',
  );
  assert.equal(getCaseHashConfigurationDifferences([reference, identical, unknown], 'a').size, 0);
  const changed = group('b', {
    compset_alias: 'COMMON',
    compset_long_name: 'DIFFERENT_LONG',
    grid_alias: 'grid_B',
    grid_long_name: 'grid_long_B',
    git_tag: 'v4',
  });
  const differences = getCaseHashConfigurationDifferences([changed, reference, unknown], 'a');
  assert.deepEqual(
    differences.get('b').map((difference) => difference.field),
    ['compset_long_name', 'grid_alias', 'grid_long_name', 'git_tag'],
  );
  assert.equal(differences.has('a'), false);
  assert.equal(differences.has(null), false);
  assert.equal(differences.get('b')[1].baselineHash, 'a');
  assert.equal(differences.get('b')[1].baselineValue, 'grid_A');
  const fallback = getCaseHashConfigurationDifferences(
    [
      reference,
      group(null, { grid_alias: 'grid_B' }, 'missing:one'),
      group(null, { grid_alias: 'grid_C' }, 'missing:two'),
    ],
    'a',
  );
  assert.equal(fallback.get(null).length, 1);
  assert.equal(fallback.get(null)[0].value, 'grid_B · grid_C');
  const within = group('a', { grid_alias: 'grid_A' });
  within.configuration.grid_alias.differences = [{ value: 'grid_B' }];
  const matchingObservations = group('b', { grid_alias: 'grid_B' });
  matchingObservations.configuration.grid_alias.differences = [{ value: 'grid_A' }];
  assert.equal(getCaseHashConfigurationDifferences([within, matchingObservations], 'a').size, 0);
  assert.equal(getCaseHashConfigurationDifferences([within], 'a').size, 0);
  assert.equal(getCaseHashConfigurationDifferences([reference, changed], undefined).size, 0);
  assert.equal(
    getCaseHashConfigurationDifferences([group('a', {}), reference, changed], 'unknown').size,
    0,
  );
  const missingBaseline = group('a', { compset_alias: 'COMMON' });
  assert.equal(
    getCaseHashConfigurationDifferences([missingBaseline, identical, changed], 'a').size,
    0,
    'Missing baseline values never choose another group as a field baseline',
  );
  const reversed = getCaseHashConfigurationDifferences([reference, changed], 'b');
  assert.equal(reversed.has('b'), false);
  assert.equal(reversed.get('a')[1].baselineValue, 'grid_B');
  assert.equal(reversed.get('a')[1].value, 'grid_A');
});

test('discovery hash groups use execution count then full hash for deterministic display baselines', async () => {
  const { sortCaseHashGroups } = await server.ssrLoadModule('/src/features/catalog/caseUtils.ts');
  const groups = [
    { caseHash: 'b', executions: ['1', '2'] },
    { caseHash: null, executions: ['3', '4'] },
    { caseHash: 'c', executions: ['5', '6', '7'] },
    { caseHash: 'a', executions: ['8', '9'] },
  ];
  assert.deepEqual(
    sortCaseHashGroups(groups).map((group) => group.caseHash),
    ['c', 'a', 'b', null],
  );
  assert.deepEqual(
    sortCaseHashGroups([...groups].reverse()).map((group) => group.caseHash),
    ['c', 'a', 'b', null],
  );
  assert.deepEqual(
    groups.map((group) => group.caseHash),
    ['b', null, 'c', 'a'],
  );
  assert.equal(
    sortCaseHashGroups([
      { caseHash: null, executions: ['1', '2', '3'] },
      { caseHash: 'a', executions: ['4'] },
    ])[0].caseHash,
    null,
    'A larger fallback group sorts first rather than silently selecting another baseline',
  );
});

test('execution metadata sorting keeps unknowns last without mutating candidates', async () => {
  const { sortCaseExecutions } = await server.ssrLoadModule('/src/features/catalog/caseUtils.ts');
  const candidates = [
    {
      summary: { id: 'b', executionId: 'run-2' },
      details: { machineName: 'Unknown', initializationType: 'startup' },
    },
    {
      summary: { id: 'a', executionId: 'run-1' },
      details: { machineName: 'Machine A', initializationType: 'hybrid' },
    },
  ];
  for (const direction of ['asc', 'desc'])
    assert.equal(
      sortCaseExecutions(candidates, { key: 'machine', direction }).at(-1).summary.id,
      'b',
    );
  assert.equal(
    sortCaseExecutions(candidates, { key: 'initialization', direction: 'asc' })[0].summary.id,
    'a',
  );
  assert.equal(
    sortCaseExecutions(candidates, { key: 'executionId', direction: 'desc' })[0].summary.id,
    'b',
  );
  assert.deepEqual(
    candidates.map(({ summary }) => summary.id),
    ['b', 'a'],
  );
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

test('alert announces errors assertively and lets layout classes override defaults', async () => {
  const { Alert } = await server.ssrLoadModule('/src/components/ui/alert.tsx');
  const render = (props) => renderToStaticMarkup(createElement(Alert, props, 'Notice'));

  const error = render({ variant: 'error', className: 'rounded-none p-6' });
  assert.match(error, /role="alert"/);
  assert.match(error, /bg-red-50/);
  assert.match(error, /rounded-none/);
  assert.doesNotMatch(error, /rounded-md|p-3/);

  assert.match(render({ variant: 'warning' }), /role="status"[^>]*bg-amber-50/);
  assert.match(render({}), /role="status"[^>]*bg-sky-50/);
});

test('cases table exposes sort state and labels its filters', async () => {
  const { CasesPage } = await server.ssrLoadModule('/src/features/catalog/CasesPage.tsx');
  const { MemoryRouter } = await server.ssrLoadModule('react-router-dom');
  const client = new QueryClient();
  client.setQueryDefaults(['cases', 'page'], {
    initialData: {
      items: [{ id: 'case-1', name: 'case-a', executionCount: 1 }],
      total: 1,
      page: 1,
      pageSize: 25,
    },
  });

  try {
    const html = renderToStaticMarkup(
      createElement(
        QueryClientProvider,
        { client },
        createElement(
          MemoryRouter,
          { initialEntries: ['/cases?sortBy=name&sortOrder=asc'] },
          createElement(CasesPage),
        ),
      ),
    );

    assert.equal(html.match(/aria-sort="/g)?.length, 1);
    assert.match(html, /<th[^>]*aria-sort="ascending"[^>]*><button[^>]*>Case Name/);
    assert.doesNotMatch(html, /[▲▼]/);
    assert.match(html, /aria-label="Expand executions" aria-expanded="false"/);
    assert.match(html, /<label for="cases-search"/);
    assert.match(html, /<input[^>]*id="cases-search"/);
    assert.match(html, /<label for="cases-filter-case-group"/);
    assert.match(html, /<button[^>]*id="cases-filter-case-group"/);
  } finally {
    client.clear();
  }
});

test('cases table shows the default latest-run sort on a sortable header', async () => {
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
        createElement(MemoryRouter, { initialEntries: ['/cases'] }, createElement(CasesPage)),
      ),
    );

    assert.match(html, /<th[^>]*aria-sort="descending"[^>]*><button[^>]*>Latest completed run<svg/);
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

test('execution status badge maps statuses to shared tones with a readable fallback', async () => {
  const { ExecutionStatusBadge } = await server.ssrLoadModule(
    '/src/components/shared/ExecutionStatusBadge.tsx',
  );
  const render = (status) => renderToStaticMarkup(createElement(ExecutionStatusBadge, { status }));

  const running = render('RUNNING');
  assert.match(running, /^<div class="[^"]*bg-amber-50[^"]*"/);
  assert.match(running, /aria-hidden="true"/);
  assert.match(running, />Running<\/div>$/);

  const fallback = render('archived');
  assert.match(fallback, /bg-muted text-muted-foreground/);
  assert.match(fallback, />Archived<\/div>$/);
  assert.doesNotMatch(fallback, /<svg/);
});
