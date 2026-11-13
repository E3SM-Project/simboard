import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, test } from 'node:test';
import { URLSearchParams } from 'node:url';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

let server;
let cacheDir;
let utils;

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
  utils = await server.ssrLoadModule('/src/features/operations/operationsUtils.ts');
});

after(async () => {
  await server?.close();
  if (cacheDir) await rm(cacheDir, { recursive: true, force: true });
});

const run = (overrides = {}) => ({
  id: 'run',
  status: 'succeeded',
  started_at: '2026-11-13T00:00:00Z',
  finished_at: '2026-11-13T00:05:00Z',
  failure_reason: null,
  failure_message: null,
  failure_status_code: null,
  upload_failures: null,
  ...overrides,
});

const job = (id, scanMode, health, overrides = {}) => ({
  id,
  machine_name: id.split('-')[0],
  scan_mode: scanMode,
  max_silence_minutes: 45,
  max_duration_minutes: 60,
  health,
  last_reported_at: '2026-11-13T00:05:00Z',
  latest_completed_run: run(),
  active_run: null,
  active_run_count: 0,
  latest_upload_run: null,
  ...overrides,
});

const JOBS = [
  job('chrysalis-staging', 'staging', 'healthy', {
    latest_upload_run: run({
      upload_failures: {
        counts: { 413: 2, network: 1 },
        cases: [
          { case_path: '/staging/case-a', status_code: 413, attempts: 1, message: 'Too large' },
          { case_path: '/staging/case-b', status_code: null, attempts: 3, message: 'Timed out' },
        ],
        truncated: true,
      },
    }),
  }),
  job('chrysalis-archive', 'archive', 'failed', {
    latest_completed_run: run({
      status: 'failed',
      failure_reason: 'api_request',
      failure_message: 'State request failed.',
      failure_status_code: 503,
    }),
  }),
  job('perlmutter-staging', 'staging', 'stale'),
  job('perlmutter-diagnostics', 'diagnostics', 'stale', {
    last_reported_at: null,
    latest_completed_run: null,
  }),
];

test('filters ignore unknown values and default to the last 7 days', () => {
  const parse = (query, sites = ['LCRC', 'NERSC']) =>
    utils.parseOperationsFilters(new URLSearchParams(query), sites);

  assert.deepEqual(parse('job_type=archive&site=LCRC&range=30'), {
    jobType: 'archive',
    siteName: 'LCRC',
    rangeDays: 30,
  });
  assert.deepEqual(parse('job_type=other&site=OLCF&range=5'), {
    jobType: undefined,
    siteName: undefined,
    rangeDays: 7,
  });
  // The site list may not have loaded yet.
  assert.equal(parse('site=LCRC', []).siteName, 'LCRC');
});

test('date windows cover whole UTC days through today', () => {
  const now = new Date('2026-11-13T23:30:00-08:00');
  assert.deepEqual(utils.utcDateWindow(7, now), {
    startDate: '2026-11-08',
    endDate: '2026-11-15',
  });
});

test('never-reported, stale, and failed jobs are distinct statuses', () => {
  assert.deepEqual(JOBS.map(utils.getJobStatus), ['healthy', 'failed', 'stale', 'never_reported']);
  assert.equal(
    utils.getJobDetails(JOBS[1]),
    'API request failed (HTTP 503): State request failed.',
  );
  // JOBS last reported at 00:05; the staging silence limit is 45 minutes.
  const now = new Date('2026-11-13T03:00:00Z');
  assert.equal(utils.getJobDetails(JOBS[2], now), 'No report for over 45 min');
  assert.equal(
    utils.getJobDetails({ ...JOBS[2], latest_completed_run: JOBS[1].latest_completed_run }, now),
    'No report for over 45 min; last run: API request failed (HTTP 503): State request failed.',
  );
  // An archive job that reported recently is stale only because its run overran.
  assert.equal(
    utils.getJobDetails(
      job('x-archive', 'archive', 'stale', {
        max_silence_minutes: 1560,
        max_duration_minutes: 720,
      }),
      now,
    ),
    'Run exceeded 12 h without finishing',
  );
  assert.equal(utils.getJobDetails(JOBS[3]), 'No report received');
  assert.equal(utils.getJobDetails(JOBS[0]), null);
  assert.equal(
    utils.getJobDetails(
      job('x-staging', 'staging', 'running', {
        active_run: run({ status: 'running', started_at: '2026-11-13T01:02:00Z' }),
        active_run_count: 2,
      }),
    ),
    'Started 2026-11-13 01:02 UTC (2 active runs)',
  );
});

test('failed uploads use full counts and flag truncated case lists', () => {
  const { rows, truncatedJobs, total } = utils.getFailedUploads(JOBS);
  assert.equal(total, 3);
  assert.deepEqual(
    rows.map((row) => [row.jobId, row.case_path]),
    [
      ['chrysalis-staging', '/staging/case-a'],
      ['chrysalis-staging', '/staging/case-b'],
    ],
  );
  assert.deepEqual(truncatedJobs, [{ jobId: 'chrysalis-staging', shown: 2, total: 3 }]);
  assert.deepEqual(
    utils.filterJobs(JOBS, 'archive').map((item) => item.id),
    ['chrysalis-archive'],
  );
});

test('daily failure counts are limited to the window and pivoted by category', () => {
  const counts = [
    { day: '2026-11-01', machine_name: 'chrysalis', category: 'server', count: 9 },
    { day: '2026-11-10', machine_name: 'chrysalis', category: 'auth', count: 1 },
    { day: '2026-11-10', machine_name: 'chrysalis', category: 'unavailable', count: 2 },
    { day: '2026-11-12', machine_name: 'perlmutter', category: 'auth', count: 4 },
  ];
  const { rows, categories } = utils.getDailyFailureRows(counts, {
    startDate: '2026-11-08',
    endDate: '2026-11-15',
  });
  assert.deepEqual(categories, ['auth', 'unavailable']);
  assert.deepEqual(rows, [
    { day: '2026-11-12', machineName: 'perlmutter', counts: { auth: 4 }, total: 4 },
    { day: '2026-11-10', machineName: 'chrysalis', counts: { auth: 1, unavailable: 2 }, total: 3 },
  ]);
});

test('rejection errors are joined with their fields', () => {
  assert.equal(
    utils.formatRejectionErrors([
      { field: 'case_name', code: 'missing', message: 'Required.' },
      { message: 'Bad timing file.' },
    ]),
    'case_name: Required.; Bad timing file.',
  );
});

const renderPage = async ({ role, query = '', seed }) => {
  const { AuthContext } = await server.ssrLoadModule('/src/auth/context.ts');
  const { MemoryRouter } = await server.ssrLoadModule('react-router-dom');
  const { OperationsDashboardPage } = await server.ssrLoadModule(
    '/src/features/operations/OperationsDashboardPage.tsx',
  );
  const { operationsQueryKeys } = await server.ssrLoadModule(
    '/src/features/operations/hooks/useOperations.ts',
  );
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
  seed?.(client, operationsQueryKeys);
  const auth = {
    user: { id: '1', email: 'a@example.test', role, is_active: true },
    loading: false,
    isAuthenticated: true,
    loginWithGithub: () => {},
    logout: async () => {},
    refreshUser: async () => true,
  };
  const html = renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client },
      createElement(
        AuthContext.Provider,
        { value: auth },
        createElement(
          MemoryRouter,
          { initialEntries: [`/admin/operations${query}`] },
          createElement(OperationsDashboardPage, {
            sites: [{ id: 's1', name: 'LCRC', createdAt: '', updatedAt: '' }],
          }),
        ),
      ),
    ),
  );

  return { html, client };
};

const seedData = (client, keys, siteName, jobs = JOBS) => {
  const { startDate, endDate } = utils.utcDateWindow(7);
  client.setQueryData(keys.jobs(siteName), { jobs, upload_failure_daily_counts: [] });
  client.setQueryData(keys.summary(siteName, startDate, endDate), {
    rows: [
      {
        day: startDate,
        machine: 'chrysalis',
        case_id: 'c1',
        case_name: 'v3.LR.piControl',
        hpc_username: 'ac.user',
        new_executions: 2,
      },
    ],
    totals: { new_executions: 2, distinct_cases: 1 },
  });
  client.setQueryData(keys.rejected(siteName), { executions: [], total: 0 });
};

test('only admins see the Operations navigation item', async () => {
  const { AuthContext } = await server.ssrLoadModule('/src/auth/context.ts');
  const { MemoryRouter } = await server.ssrLoadModule('react-router-dom');
  const { NavBar } = await server.ssrLoadModule('/src/components/layout/NavBar.tsx');
  const render = (role) =>
    renderToStaticMarkup(
      createElement(
        AuthContext.Provider,
        {
          value: {
            user: { id: '1', email: 'a@example.test', role, is_active: true },
            loading: false,
            isAuthenticated: true,
            loginWithGithub: () => {},
            logout: async () => {},
            refreshUser: async () => true,
          },
        },
        createElement(MemoryRouter, null, createElement(NavBar)),
      ),
    );

  const adminHtml = render('admin');
  assert.match(adminHtml, /title="Admins only"[^>]*href="\/admin\/operations"/);
  assert.match(adminHtml, /\(admins only\)/);
  for (const role of ['user', 'service_account'])
    assert.doesNotMatch(render(role), /\/admin\/operations/);
});

test('non-admins see an access notice and the page creates no data queries', async () => {
  const { html, client } = await renderPage({ role: 'user' });
  assert.match(html, /Administrators only/);
  assert.doesNotMatch(html, /Job Health/);
  assert.equal(client.getQueryCache().getAll().length, 0);
});

test('admins see every section with status counts, details, and empty states', async () => {
  const { html } = await renderPage({
    role: 'admin',
    seed: (client, keys) => seedData(client, keys),
  });
  for (const heading of [
    'Job Health',
    'Failed Uploads',
    'Recent Ingestions',
    'Rejected Executions',
  ])
    assert.match(html, new RegExp(`<h2[^>]*>${heading}</h2>`));

  const tile = (label) => html.match(new RegExp(`<dt[^>]*>${label}</dt><dd[^>]*>(\\d+)</dd>`))[1];
  assert.deepEqual(['Healthy', 'Running', 'Failed', 'Stale', 'Never reported'].map(tile), [
    '1',
    '0',
    '1',
    '1',
    '1',
  ]);
  // Tiles are colored only when their count is nonzero.
  const tileClass = (label) =>
    html.match(
      new RegExp(`<div class="([^"]*)"><svg(?:(?!<div class).)*?<dt[^>]*>${label}</dt>`),
    )[1];
  assert.match(tileClass('Failed'), /border-red-200/);
  assert.match(tileClass('Running'), /bg-muted/);
  assert.doesNotMatch(tileClass('Running'), /blue/);
  assert.match(html, /Updated \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC/);
  assert.match(html, />Refresh<\/button>/);
  assert.doesNotMatch(html, /Reset filters/);
  assert.match(html, /API request failed \(HTTP 503\): State request failed\./);
  assert.match(html, /3 failed uploads/);
  assert.match(html, /Showing 2 of 3 failed cases for/);
  assert.match(html, /No failed uploads in the last 7 days\./);
  assert.match(html, /href="\/cases\/chrysalis\/ac.user\/v3.LR.piControl"/);
  assert.match(html, /2 new executions/);
  assert.match(html, /No executions are currently rejected\./);
});

test('job type and site filters narrow sections and offer a reset', async () => {
  const { html, client } = await renderPage({
    role: 'admin',
    query: '?job_type=archive&site=LCRC',
    // The API filters by site, so seed only LCRC (chrysalis) jobs.
    seed: (queryClient, keys) =>
      seedData(
        queryClient,
        keys,
        'LCRC',
        JOBS.filter((item) => item.machine_name === 'chrysalis'),
      ),
  });
  assert.deepEqual(
    client
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey[2]),
    ['LCRC', 'LCRC', 'LCRC'],
  );
  assert.match(html, /chrysalis-archive/);
  assert.doesNotMatch(html, /chrysalis-staging/);
  // With no failed cases or daily counts, one empty block replaces both tables.
  assert.match(html, /border-dashed[^>]*>No failed uploads match these filters\./);
  assert.doesNotMatch(html, /Daily failure counts/);
  assert.match(html, /No rejected executions match these filters\./);
  assert.match(html, /Reset filters/);
});

test('sections show the API error detail when loading fails', async () => {
  const { OperationsSection } = await server.ssrLoadModule(
    '/src/features/operations/components/OperationsSection.tsx',
  );
  const { Activity } = await server.ssrLoadModule('lucide-react');
  const html = renderToStaticMarkup(
    createElement(OperationsSection, {
      title: 'Job Health',
      description: 'Latest status.',
      icon: Activity,
      query: {
        data: undefined,
        isError: true,
        isFetching: false,
        refetch: () => {},
        error: { isAxiosError: true, response: { data: { detail: "Site 'X' not found." } } },
      },
      children: () => null,
    }),
  );
  assert.match(html, /Could not load job health\. Site &#x27;X&#x27; not found\./);
  assert.match(html, /Retry/);
});
