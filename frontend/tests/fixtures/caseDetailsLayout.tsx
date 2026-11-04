import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { api } from '../../src/api/api';
import { AuthContext } from '../../src/auth/context';
import { CaseDetailsPage } from '../../src/features/catalog/CaseDetailsPage';
import { CasesPage } from '../../src/features/catalog/CasesPage';
import { formatSimulationCoverage } from '../../src/features/catalog/caseUtils';
import { CaseArtifactsTable } from '../../src/features/catalog/components/CaseArtifactsTable';
import {
  CaseConfigurationDetails,
  CaseConfigurationSummary,
} from '../../src/features/catalog/components/CaseConfiguration';
import { HomePage } from '../../src/features/home/HomePage';
import '../../src/index.css';
import { useCaseExecutions } from '../../src/lib/catalog/hooks/useCaseExecutions';
import { catalogQueryKeys } from '../../src/lib/catalog/queryKeys';
import type { CaseDetailOut, ConfigurationFieldOut } from '../../src/types';

const client = new QueryClient({
  defaultOptions: { queries: { staleTime: Infinity, retry: false } },
});
const requests: string[] = [];
api.defaults.adapter = async (config) => {
  requests.push(config.url ?? '');
  return {
    config,
    status: 200,
    statusText: 'OK',
    headers: {},
    data: { items: [], total: 0, page: 1, pageSize: 10 },
  };
};
const executions = [1, 2, 3].map((number) => ({
  id: `execution-${number}`,
  executionId: `run-${number}`,
  caseHash: 'test-hash',
  status: 'completed',
  simulationStartDate: `000${number}-01-01`,
  simulationEndDate: `000${number + 1}-01-01`,
  initializationType: number === 1 ? 'hybrid' : 'startup',
  runStartDate: number === 3 ? null : `2026-10-0${number}T12:00:00Z`,
  runEndDate: number === 3 ? null : `2026-10-0${number}T13:00:00Z`,
}));
const record = {
  id: 'case-1',
  name: 'test.case',
  caseGroup: 'v3.HR',
  simulationType: 'production',
  diagnosticsTiers: [],
  machineNames: ['chrysalis'],
  hpcUsernames: ['test.user'],
  description: null,
  keyFeatures: null,
  knownIssues: null,
  notesMarkdown: null,
  updatedAt: '2026-10-01T12:00:00Z',
  artifacts: [],
  links: [{ id: 'link-1', kind: 'docs', label: 'Case docs', url: 'https://example.test/docs' }],
  sourceDirectories: [{ id: 'source-1', kind: 'archive', path: '/archive/test.case' }],
  executions,
  sharedConfiguration: {
    compset_alias: { value: 'SHARED-COMPSET', varies: false, incomplete: false },
    grid_alias: { value: 'SHARED-GRID', varies: false, incomplete: false },
    git_tag: { value: 'v3', varies: false, incomplete: false },
  },
  simulationCoverage: { years: 1234.5, partial: true, excludedExecutionCount: 1 },
  latestExecution: { executionId: 'run-105', runEndDate: '2026-11-02T12:00:00Z' },
};
client.setQueryData(['cases', 'readable-detail', 'chrysalis', 'test.user', 'test.case'], record);
client.setQueryDefaults(['executions', 'case'], {
  initialData: {
    pages: [{ items: executions, total: 3, page: 1, pageSize: 100 }],
    pageParams: [1],
  },
});
const root = createRoot(document.getElementById('root')!);

function FixtureCasePage() {
  const [selectedIds, setSelectedIds] = useState<Record<string, string[]>>({});

  return (
    <CaseDetailsPage
      selectedCaseExecutionIdsByCase={selectedIds}
      setSelectedCaseExecutionIdsForCase={(caseId, ids) => setSelectedIds({ [caseId]: ids })}
      renderCompareSection={() => <p>Comparison fixture</p>}
    />
  );
}

function check(condition: unknown, message: string) {
  if (!condition) throw new Error(message);
}

function LocationProbe() {
  const location = useLocation();

  return <output id="filter-url">{location.search}</output>;
}

async function waitFor(checkReady: () => unknown) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (checkReady()) return;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error('Timed out waiting for rendered case details');
}

async function run() {
  const expectedWidth = Number(new URLSearchParams(location.search).get('width'));
  check(
    window.innerWidth === expectedWidth,
    `Expected viewport ${expectedWidth}, got ${window.innerWidth}`,
  );
  await checkHomepage();
  await checkCasesFilters();
  for (const role of ['anonymous', 'editor', 'loading-admin', 'admin']) {
    const user =
      role === 'anonymous'
        ? null
        : {
            id: 'user-1',
            email: 'user@example.test',
            is_superuser: role.includes('admin'),
            is_active: true,
            is_verified: true,
            can_edit_managed_content: true,
          };
    root.render(
      <QueryClientProvider client={client}>
        <AuthContext.Provider
          value={{
            user,
            loading: role === 'loading-admin',
            isAuthenticated: !!user,
            loginWithGithub: () => {},
            logout: async () => {},
            refreshUser: async () => true,
          }}
        >
          <MemoryRouter key={role} initialEntries={['/cases/chrysalis/test.user/test.case']}>
            <Routes>
              <Route path="/cases/:machine/:hpcUsername/:caseName" element={<FixtureCasePage />} />
            </Routes>
          </MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>,
    );
    await waitFor(() => document.querySelector('h1')?.textContent === record.name);
    await new Promise((resolve) => setTimeout(resolve, 50));

    const developer = [...document.querySelectorAll('details')].find(
      (element) => element.querySelector('summary')?.textContent === 'Developer Details',
    );
    check(Boolean(developer) === (role === 'admin'), `Developer Details visibility: ${role}`);
    if (developer) {
      check(!developer.open, 'Developer Details must start collapsed');
      developer.querySelector('summary')!.click();
      check(developer.open, 'Developer Details must expand');
      check(
        developer.textContent?.includes('/archive/test.case'),
        'Source directory must remain available',
      );
    }
    const headings = [...document.querySelectorAll('h2, h3')].map((element) => element.textContent);
    check(
      headings.filter((text) => text === 'Case Metadata').length === 1,
      'One Case Metadata heading',
    );
    for (const text of ['Simulated years covered', 'Latest execution', 'Machines', 'HPC users']) {
      const label = [...document.querySelectorAll('div')].find(
        (element) => element.childElementCount === 0 && element.textContent === text,
      );
      check(label, `Metadata label exists: ${text}`);
      const style = getComputedStyle(label!);
      check(style.textTransform === 'none', `Metadata label uses sentence case: ${text}`);
      check(
        style.letterSpacing === 'normal' || style.letterSpacing === '0px',
        `Metadata label has normal spacing: ${text}`,
      );
    }
    check(
      document.body.textContent?.includes('Page updated:'),
      'Page update timestamp near header',
    );
    const metadata = document.querySelector('[aria-label="Shared configuration"]')!;
    check(
      metadata.textContent?.includes('SHARED-COMPSET'),
      'Shared alias appears beneath metadata',
    );
    check(metadata.textContent?.includes('SHARED-GRID'), 'Shared grid appears beneath metadata');
    check(metadata.textContent?.includes('v3'), 'Existing model tag appears in summary');
    const stats = metadata.nextElementSibling!;
    check(
      stats.textContent?.startsWith('Simulated years covered'),
      'Coverage is first summary statistic',
    );
    check(
      stats.textContent?.includes('1,234.5 (partial)'),
      'Use server coverage, not loaded execution intervals',
    );
    check(stats.textContent?.includes('2026-11-02'), 'Latest run date differs from page update');
    check(
      stats.querySelector('a')?.getAttribute('href')?.endsWith('/run-105'),
      'Latest run can be outside loaded page',
    );
    check(!stats.textContent?.includes('Case hash groups'), 'Hash count removed from summary');
    check(!stats.textContent?.includes('Executions'), 'Execution count removed from summary');
    const notes = [...document.querySelectorAll('label')].find(
      (element) => element.textContent === 'Notes',
    );
    check(
      (notes?.nextElementSibling?.getBoundingClientRect().height ?? Infinity) < 50,
      'Empty notes stay compact',
    );
    const resources = document.querySelector('a[href="https://example.test/docs"]');
    check(
      resources && resources.getBoundingClientRect().width < Math.min(400, window.innerWidth - 48),
      'Single resource stays compact',
    );
    check(
      document.documentElement.scrollWidth <= window.innerWidth,
      'No page-wide horizontal overflow',
    );
    check(requests.length === 0, 'History must not fetch before opening');
    const history = [...document.querySelectorAll('button')].find((element) =>
      element.textContent?.includes('Change History'),
    );
    check(history, 'Change history exists');
    check(
      history!.closest('section') === document.querySelector('#root > div > section:last-child'),
      'History is last section',
    );
  }

  const table = document.querySelector('table')!;
  check(
    [...table.querySelectorAll('th')].map((element) => element.textContent).join('|') ===
      'Select|Simulation dates|Initialization|Run dates|Execution ID|Case Hash',
    'Flat execution column order',
  );
  const row = table.tBodies[0].rows[0];
  check(row.cells[1].textContent === '0001-01-01 → 0002-01-01', 'Simulation dates match column');
  check(row.cells[2].textContent === 'hybrid', 'Initialization value stays unchanged');
  check(row.cells[3].textContent === '2026-10-01 → 2026-10-01', 'Run dates match column');
  check(row.cells[4].textContent === 'run-1', 'Oldest simulation stays first');
  check(row.cells[5].textContent === 'test-hash', 'Hash matches column');
  check(
    row.cells[4].querySelector('a')?.getAttribute('href')?.endsWith('/run-1'),
    'Execution link retained',
  );

  const simulationHeader = table.querySelectorAll('th')[1];
  const runHeader = table.querySelectorAll('th')[3];
  check(
    simulationHeader.getAttribute('aria-sort') === 'ascending',
    'Simulation sort starts ascending',
  );
  check(!runHeader.hasAttribute('aria-sort'), 'Unsorted run header omits aria-sort');
  check(!table.textContent?.includes('first)'), 'No oldest/latest-first header text');
  simulationHeader.querySelector('button')!.click();
  await waitFor(() => table.tBodies[0].rows[0].cells[4].textContent === 'run-3');
  check(
    simulationHeader.getAttribute('aria-sort') === 'descending',
    'Simulation sort toggles descending',
  );
  runHeader.querySelector('button')!.click();
  await waitFor(() => table.tBodies[0].rows[0].cells[4].textContent === 'run-1');
  check(runHeader.getAttribute('aria-sort') === 'ascending', 'Run sort starts ascending');
  check(!simulationHeader.hasAttribute('aria-sort'), 'Previously sorted header omits aria-sort');
  runHeader.querySelector('button')!.click();
  await waitFor(() => table.tBodies[0].rows[0].cells[4].textContent === 'run-2');
  check(table.tBodies[0].rows[2].cells[4].textContent === 'run-3', 'Missing run dates remain last');
  const activeQuery = client
    .getQueryCache()
    .getAll()
    .find((query) => query.queryKey[0] === 'executions' && query.getObserversCount() > 0);
  const params = activeQuery!.queryKey[4] as { sortBy: string; sortOrder: string };
  check(
    params.sortBy === 'run_activity' && params.sortOrder === 'desc',
    'Fetch uses selected sort',
  );

  for (const checkbox of table.querySelectorAll<HTMLButtonElement>('[role="checkbox"]')) {
    checkbox.click();
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  const compare = [...document.querySelectorAll('button')].find(
    (element) => element.textContent === 'Compare Case Executions',
  )!;
  check(!compare.disabled, 'Selection still enables comparison');
  compare.click();
  await waitFor(() => document.body.textContent?.includes('Comparison fixture'));

  const grouped = [...document.querySelectorAll('button')].find(
    (element) => element.textContent === 'Grouped by Case Hash',
  )!;
  grouped.click();
  await waitFor(() => document.querySelector('table table'));
  const groupTable = document.querySelector('table table')!;
  check(
    [...groupTable.querySelectorAll('th')].map((element) => element.textContent).join('|') ===
      'Select|Simulation dates|Initialization|Run dates|Execution ID',
    'Grouped execution column order',
  );
  check(
    groupTable.querySelector('[role="checkbox"]')?.getAttribute('aria-checked') === 'true',
    'Grouping retains selection',
  );
  check(
    groupTable.querySelectorAll('th')[3].getAttribute('aria-sort') === 'descending',
    'Grouping retains run sort',
  );
  groupTable.querySelectorAll('th')[1].querySelector('button')!.click();
  await waitFor(() => groupTable.tBodies[0].rows[0].cells[4].textContent === 'run-1');
  const flat = [...document.querySelectorAll('button')].find(
    (element) => element.textContent === 'All executions',
  )!;
  flat.click();
  await waitFor(() => !document.querySelector('table table'));
  check(
    document.querySelectorAll('th')[1].getAttribute('aria-sort') === 'ascending',
    'Flat view retains grouped simulation sort',
  );
  check(
    document.querySelector('[role="checkbox"]')?.getAttribute('aria-checked') === 'true',
    'Sorting retains selection',
  );

  const runAscKey = [
    'executions',
    'case',
    record.id,
    'infinite',
    {
      caseId: record.id,
      pageSize: 100,
      sortBy: 'run_activity',
      sortOrder: 'asc',
    },
  ];
  client.removeQueries({ queryKey: runAscKey, exact: true });
  client.setQueryDefaults(runAscKey, { initialData: undefined });
  const originalAdapter = api.defaults.adapter;
  let finishFetch = () => {};
  let fetchStarted = false;
  const pendingFetch = new Promise<void>((resolve) => {
    finishFetch = resolve;
  });
  api.defaults.adapter = async (config) => {
    fetchStarted = true;
    await pendingFetch;
    return {
      config,
      status: 200,
      statusText: 'OK',
      headers: {},
      data: { items: executions, total: 3, page: 1, pageSize: 100 },
    };
  };
  const pendingSortButton = document.querySelectorAll('th')[3].querySelector('button')!;
  pendingSortButton.focus();
  pendingSortButton.click();
  await waitFor(() => fetchStarted);
  check(
    document.querySelector('h1')?.textContent === record.name,
    'Sorting does not replace the page with a loader',
  );
  check(
    document.querySelector('table')?.tBodies[0].rows.length === 3,
    'Rows stay visible while sort data loads',
  );
  check(document.activeElement === pendingSortButton, 'Sort header keeps keyboard focus');
  check(
    document.body.textContent?.includes('Comparison fixture'),
    'Comparison stays visible while sorting',
  );
  finishFetch();
  await waitFor(() => client.getQueryState(runAscKey)?.status === 'success');
  api.defaults.adapter = originalAdapter;

  const edit = [...document.querySelectorAll('button')].find(
    (element) => element.textContent === 'Edit',
  )!;
  edit.click();
  await waitFor(() => document.getElementById('case-group'));
  check(
    (document.getElementById('case-group') as HTMLInputElement).value === record.caseGroup,
    'Editing retains Case Group',
  );
  const cancel = [...document.querySelectorAll('button')].find(
    (element) => element.textContent === 'Cancel',
  )!;
  cancel.click();
  await waitFor(() => !document.getElementById('case-group'));

  const history = [...document.querySelectorAll('button')].find((element) =>
    element.textContent?.includes('Change History'),
  )!;
  history.click();
  await waitFor(() => requests.length === 1);
  check(requests[0].includes('/history'), 'Opening history fetches history only');
  await checkArtifactsScrolling();
  await checkExecutionPlaceholders();
  await checkConfigurationComparison();
}

async function checkConfigurationComparison() {
  const observation = (value: string, executionId: string, runDate: string | null) => ({
    value,
    executionId,
    executionUuid: executionId,
    runDate,
  });
  const field = (value: string | null, executionId: string): ConfigurationFieldOut => ({
    source: value == null ? null : observation(value, executionId, '2026-01-01T00:00:00Z'),
    differences: [],
    missingExecutionIds: value == null ? [executionId] : [],
  });
  const firstConfiguration = {
    compset_alias: field('shared-alias', 'run-1'),
    grid_alias: field('grid-one', 'run-1'),
    git_tag: field(null, 'run-1'),
    compset_long_name: field('LONG_'.repeat(100), 'run-1'),
    grid_long_name: field('grid-long', 'run-1'),
  };
  firstConfiguration.grid_alias.differences.push(observation('later-grid', 'run-2', null));
  const configured: CaseDetailOut = {
    ...record,
    createdAt: record.updatedAt,
    simulationType: 'production',
    executions: [],
    links: [],
    sourceDirectories: [],
    latestExecution: null,
    sharedConfiguration: {
      compset_alias: { value: 'shared-alias', varies: false, incomplete: false },
      grid_alias: { value: null, varies: true, incomplete: true },
      git_tag: { value: null, varies: false, incomplete: true },
      compset_long_name: {
        value: firstConfiguration.compset_long_name.source!.value,
        varies: false,
        incomplete: false,
      },
      grid_long_name: { value: 'grid-long', varies: false, incomplete: false },
    },
    configurationGroups: [
      {
        key: 'one',
        caseHash: 'hash-'.repeat(40),
        executionIds: ['run-1', 'run-2'],
        configuration: firstConfiguration,
        coverage: { years: 20, partial: false, excludedExecutionCount: 0 },
      },
      {
        key: 'missing:run-3',
        caseHash: null,
        executionIds: ['run-3'],
        configuration: { ...firstConfiguration, grid_alias: field(null, 'run-3') },
        coverage: { years: null, partial: true, excludedExecutionCount: 1 },
      },
    ],
  };
  const identity = { machineName: 'chrysalis', hpcUsername: 'test.user', caseName: record.name };
  root.render(
    <MemoryRouter>
      <div className="min-w-0 p-6">
        <CaseConfigurationSummary record={configured} />
        <CaseConfigurationDetails record={configured} identity={identity} />
      </div>
    </MemoryRouter>,
  );
  await waitFor(() => document.querySelector('[data-case-configuration]'));
  const summary = document.querySelector('[aria-label="Shared configuration"]')!;
  check(summary.textContent?.includes('shared-alias'), 'Summary retains shared values');
  check(summary.textContent?.includes('Varies by Case Hash'), 'Summary flags differing values');
  check(summary.textContent?.includes('Unavailable'), 'Summary marks missing model tag');
  const details = document.querySelector<HTMLDetailsElement>('[data-case-configuration]')!;
  check(!details.open, 'Configuration details start collapsed');
  details.querySelector('summary')!.click();
  const comparison = details.querySelector('[data-configuration-differences]')!;
  check(
    comparison.querySelectorAll('tbody tr').length === 1,
    'Comparison contains only differing fields',
  );
  check(
    comparison.querySelector('tbody th')?.textContent === 'Grid alias',
    'Missing values count as a difference',
  );
  check(
    !comparison.textContent?.includes('Compset alias'),
    'Shared fields excluded from comparison',
  );
  check(
    comparison.textContent?.includes('Missing Case Hash: run-3'),
    'Hashless execution keeps identity',
  );
  check(comparison.textContent?.includes('Unavailable'), 'Missing value stays explicit');
  check(
    comparison.querySelector('a')?.getAttribute('href')?.endsWith('/run-1'),
    'Baseline links to its source',
  );
  const changes = comparison.querySelector<HTMLDetailsElement>('tbody td details')!;
  changes.querySelector('summary')!.click();
  check(changes.textContent?.includes('later-grid'), 'Later differences remain available');
  check(changes.textContent?.includes('Run date unavailable'), 'Undated provenance stays explicit');
  const group = details.querySelector<HTMLDetailsElement>('[data-configuration-group]')!;
  group.querySelector('summary')!.click();
  check(
    group.textContent?.includes('Simulated years covered: 20'),
    'Per-hash coverage remains available',
  );
  check(
    group.textContent?.includes('LONG_'.repeat(100)),
    'Full shared configuration remains available',
  );
  check(
    document.documentElement.scrollWidth <= window.innerWidth,
    'Expanded config has no page-wide overflow',
  );
  check(
    formatSimulationCoverage({ years: 0, partial: false, excludedExecutionCount: 0 }) === '0',
    'Zero coverage is valid',
  );
  check(
    formatSimulationCoverage({ years: null, partial: true, excludedExecutionCount: 1 }) ===
      'Unavailable (partial)',
    'Unknown coverage is not zero',
  );
  check(
    formatSimulationCoverage(undefined) === 'Unavailable',
    'Older response does not fabricate coverage',
  );
  const agreeing = {
    ...configured,
    configurationGroups: configured.configurationGroups!.slice(0, 1),
    sharedConfiguration: {
      ...configured.sharedConfiguration,
      grid_alias: { value: 'grid-one', varies: false, incomplete: false },
    },
  };
  root.render(
    <MemoryRouter>
      <CaseConfigurationDetails record={agreeing} identity={identity} />
    </MemoryRouter>,
  );
  await waitFor(() => !document.querySelector('[data-configuration-differences]'));
  check(
    document.body.textContent?.includes('No configuration differences'),
    'Agreement does not produce a redundant comparison table',
  );
  check(
    document.querySelector('[data-configuration-group]'),
    'Agreement retains full per-hash details',
  );
}

async function checkExecutionPlaceholders() {
  for (const caseId of ['placeholder-case', 'other-case']) {
    client.setQueryDefaults(catalogQueryKeys.executions.case(caseId), { initialData: undefined });
  }
  const params = {
    caseId: 'placeholder-case',
    pageSize: 100,
    sortBy: 'simulation_start',
    sortOrder: 'asc' as const,
  };
  client.setQueryData(catalogQueryKeys.executions.caseInfinite(params.caseId, params), {
    pages: [{ items: executions, total: 3, page: 1, pageSize: 100 }],
    pageParams: [1],
  });
  const originalAdapter = api.defaults.adapter;
  let finishFetch = () => {};
  const pendingFetch = new Promise<void>((resolve) => {
    finishFetch = resolve;
  });
  api.defaults.adapter = async (config) => {
    await pendingFetch;
    return {
      config,
      status: 200,
      statusText: 'OK',
      headers: {},
      data: { items: [], total: 0, page: 1, pageSize: 100 },
    };
  };

  try {
    root.render(
      <QueryClientProvider client={client}>
        <ExecutionProbe caseId={params.caseId} sortOrder="asc" />
      </QueryClientProvider>,
    );
    await waitFor(
      () => document.querySelector('output')?.textContent === 'placeholder-case:asc:3:false',
    );
    root.render(
      <QueryClientProvider client={client}>
        <ExecutionProbe caseId={params.caseId} sortOrder="desc" />
      </QueryClientProvider>,
    );
    await waitFor(
      () => document.querySelector('output')?.textContent === 'placeholder-case:desc:3:true',
    );
    root.render(
      <QueryClientProvider client={client}>
        <ExecutionProbe caseId="other-case" sortOrder="desc" />
      </QueryClientProvider>,
    );
    await waitFor(
      () => document.querySelector('output')?.textContent === 'other-case:desc:0:false',
    );
  } finally {
    finishFetch();
    api.defaults.adapter = originalAdapter;
  }
}

function ExecutionProbe({ caseId, sortOrder }: { caseId: string; sortOrder: 'asc' | 'desc' }) {
  const query = useCaseExecutions(caseId, { sortBy: 'simulation_start', sortOrder });

  return (
    <output>{`${caseId}:${sortOrder}:${query.data.length}:${query.isPlaceholderData}`}</output>
  );
}

async function checkArtifactsScrolling() {
  const artifacts = Array.from({ length: 30 }, (_, index) => ({
    id: `artifact-${index}`,
    kind: 'output' as const,
    label: `Artifact ${String(index).padStart(2, '0')}`,
    uri: `https://example.test/output/${index}`,
    executionIds: ['run-1'],
  }));
  let selectedIds: string[] = [];
  root.render(
    <CaseArtifactsTable
      artifacts={artifacts}
      totalArtifactCount={artifacts.length}
      onFilterExecutionIds={(ids) => {
        selectedIds = ids;
      }}
    />,
  );
  await waitFor(() => document.querySelector('table')?.tBodies[0].rows.length === 30);

  const table = document.querySelector('table')!;
  const scroller = table.parentElement!;
  const description =
    document.getElementById('artifacts-heading')!.parentElement!.nextElementSibling!;
  check(
    description.textContent?.includes(
      'Files, directories, and scripts recorded for executions in this case.',
    ),
    'Artifacts description explains the recorded resources',
  );
  check(
    description.textContent?.includes('linked executions') && !scroller.contains(description),
    'Artifacts description stays above the scroll area',
  );
  const limit = 28 * parseFloat(getComputedStyle(document.documentElement).fontSize);
  check(
    scroller.clientHeight <= limit && scroller.scrollHeight > scroller.clientHeight,
    'Long artifact tables scroll within 28rem',
  );
  const search = document.querySelector<HTMLInputElement>(
    '[aria-label="Search artifact names or paths"]',
  )!;
  check(
    !scroller.contains(search) &&
      !scroller.contains(document.querySelector('[aria-label="Filter artifacts by type"]')),
    'Search and type filters stay outside artifact scrolling',
  );

  scroller.scrollTop = 200;
  await new Promise((resolve) => setTimeout(resolve, 20));
  check(scroller.scrollTop > 0, 'Artifact rows can scroll vertically');
  check(
    [...table.querySelectorAll('th')].every(
      (cell) =>
        Math.abs(cell.getBoundingClientRect().top - scroller.getBoundingClientRect().top) <= 1 &&
        getComputedStyle(cell).backgroundColor === 'rgb(248, 250, 252)',
    ),
    'Artifact header cells stay at the top with opaque backgrounds while scrolling',
  );
  if (window.innerWidth < 680) {
    scroller.scrollLeft = 100;
    check(scroller.scrollLeft > 0, 'Artifacts retain horizontal scrolling on mobile');
  }

  const artifactSort = table.querySelectorAll('th')[1].querySelector('button')!;
  artifactSort.click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  artifactSort.click();
  await waitFor(() => table.tBodies[0].rows[0].cells[1].textContent?.includes('Artifact 29'));
  table
    .querySelector<HTMLButtonElement>('[aria-label="Filter executions linked to Artifact 29"]')!
    .click();
  check(selectedIds.join() === 'run-1', 'Artifact execution filtering still works');

  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(
    search,
    'Artifact 00',
  );
  search.dispatchEvent(new Event('input', { bubbles: true }));
  await waitFor(() => table.tBodies[0].rows.length === 1);
  check(
    scroller.clientHeight < limit && scroller.scrollHeight <= scroller.clientHeight,
    'Filtered short tables size naturally',
  );

  root.render(
    <CaseArtifactsTable artifacts={[]} totalArtifactCount={0} onFilterExecutionIds={() => {}} />,
  );
  await waitFor(() => document.body.textContent?.includes('No execution artifacts available.'));
  check(!document.querySelector('table'), 'Empty artifacts do not reserve table space');
}

async function checkHomepage() {
  const cases = Array.from({ length: 6 }, (_, index) => ({
    id: `home-${index}`,
    name: `production.case.${index}`,
    caseGroup: 'v3.HR',
    machineName: 'chrysalis',
    hpcUsername: 'test.user',
    executionCount: 7,
    updatedAt: '2030-01-01T12:00:00Z',
    latestExecution: {
      runEndDate: '2026-10-02T12:00:00Z',
      runStartDate: '2026-10-01T12:00:00Z',
    },
  }));
  const productionParams = {
    page: 1,
    pageSize: 6,
    simulationType: 'production',
    recentExecution: true,
    sortBy: 'latest_run_activity',
    sortOrder: 'desc',
  };
  client.setQueryData(['cases', 'page', productionParams], {
    items: cases,
    total: 10,
    page: 1,
    pageSize: 6,
  });
  client.setQueryData(['catalog', 'overview'], {
    totalCases: 10,
    totalExecutions: 70,
    recentCases: cases,
    machineCounts: {},
  });
  root.render(
    <QueryClientProvider client={client}>
      <MemoryRouter key="homepage">
        <Routes>
          <Route path="/" element={<HomePage machines={[]} sites={[]} />} />
          <Route path="/cases" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() => document.querySelector('h1')?.textContent === 'Explore E3SM Simulations');
  for (const table of [...document.querySelectorAll('table')].slice(0, 2)) {
    check(table.tBodies[0].rows.length === 6, 'Homepage case tables show six cases');
    check(
      table.tHead?.rows[0].cells[1].textContent === 'Last Execution',
      'Homepage uses execution dates',
    );
    check(
      table.tBodies[0].rows[0].cells[1].textContent ===
        new Date(cases[0].latestExecution.runEndDate).toLocaleDateString(),
      'Homepage does not display audit dates',
    );
    if (window.innerWidth < 1100) {
      const scroller = table.parentElement!;
      scroller.scrollLeft = 100;
      check(scroller.scrollLeft > 0, 'Homepage tables scroll horizontally on narrow screens');
    }
  }
  const browse = [...document.querySelectorAll('a')].find(
    (link) => link.textContent === 'Browse Production Cases',
  )!;
  browse.click();
  await waitFor(
    () => document.querySelector('#filter-url')?.textContent === '?simulationType=production',
  );
  client.removeQueries({ queryKey: ['cases', 'page', productionParams], exact: true });
}

async function checkCasesFilters() {
  client.setQueryDefaults(['cases', 'page'], {
    initialData: { items: [], total: 100, page: 2, pageSize: 25 },
  });
  client.setQueryDefaults(['cases', 'filter-options'], {
    initialData: { caseGroups: ['v3.HR'], machines: [], hpcUsernames: [], campaigns: [] },
  });
  root.render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/cases?page=2']}>
        <CasesPage />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await waitFor(() => document.querySelector('[aria-label="Case group"]'));
  const search = document.querySelector<HTMLInputElement>('[placeholder="Search case name…"]')!;
  const filters = [...document.querySelectorAll<HTMLButtonElement>('button[role="combobox"]')];
  check(filters.length === 4, 'Four primary dropdowns');
  const searchBounds = search.getBoundingClientRect();
  const bounds = filters.map((element) => element.getBoundingClientRect());
  if (window.innerWidth >= 1280) {
    check(
      bounds.every((rect) => rect.top === searchBounds.top && rect.width >= 200),
      'Five roomy fields on desktop',
    );
    check(searchBounds.width > bounds[0].width, 'Search is wider than dropdowns');
  } else if (window.innerWidth >= 640) {
    check(searchBounds.bottom < bounds[0].top, 'Search spans its own row');
    check(
      bounds[0].top === bounds[1].top &&
        bounds[2].top === bounds[3].top &&
        bounds[2].top > bounds[0].top,
      'Two dropdowns per intermediate row',
    );
  } else {
    check(
      bounds.every((rect, index) => rect.top > (index ? bounds[index - 1].top : searchBounds.top)),
      'One field per mobile row',
    );
  }
  const more = [...document.querySelectorAll('button')].find(
    (element) => element.textContent === 'More filters',
  )!;
  check(
    more.getBoundingClientRect().top > Math.max(...bounds.map((rect) => rect.bottom)),
    'Actions below filters',
  );
  const label = search.closest('.space-y-2')!.querySelector('label')!;
  check(getComputedStyle(label).textTransform === 'none', 'Sentence-case filter labels');
  check(document.documentElement.scrollWidth <= window.innerWidth, 'No Cases horizontal overflow');

  const groupHelp = document.querySelector<HTMLButtonElement>('[aria-label="About Case group"]')!;
  groupHelp.focus({ preventScroll: true });
  await waitFor(() => groupHelp.getAttribute('aria-describedby'));
  const tooltip = document.getElementById(groupHelp.getAttribute('aria-describedby')!)!;
  check(tooltip?.getAttribute('role') === 'tooltip', 'Keyboard focus opens the tooltip');
  check(
    tooltip.textContent?.includes('members of an ensemble run'),
    'Case Group tooltip explains ensemble grouping',
  );
  check(
    tooltip.textContent?.includes('browse those cases together'),
    'Case Group tooltip explains its use',
  );
  check(
    groupHelp.getAttribute('aria-describedby') === tooltip.id,
    'Tooltip is linked to its keyboard trigger',
  );
  groupHelp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  await waitFor(() => groupHelp.getAttribute('data-state') === 'closed');

  filters[0].click();
  await waitFor(() => document.querySelector('[role="option"][data-value="v3.HR"]'));
  document.querySelector<HTMLDivElement>('[role="option"][data-value="v3.HR"]')!.click();
  await waitFor(() =>
    document.getElementById('filter-url')?.textContent?.includes('caseGroup=v3.HR'),
  );
  check(
    !document.getElementById('filter-url')!.textContent!.includes('page='),
    'Filter changes reset pagination',
  );
  check(
    more.getAttribute('aria-expanded') === 'false',
    'Case Group does not expand advanced filters',
  );

  let copied = '';
  const originalWriteText = navigator.clipboard.writeText;
  try {
    navigator.clipboard.writeText = async (value: string) => {
      copied = value;
    };
    document.querySelector<HTMLButtonElement>('[aria-label="Copy search link"]')!.click();
    await waitFor(() => copied.includes('caseGroup=v3.HR'));
  } finally {
    navigator.clipboard.writeText = originalWriteText;
  }
  more.click();
  await waitFor(() => document.querySelector('[aria-label="Campaign"]'));
  const clear = [...document.querySelectorAll('button')].find(
    (element) => element.textContent === 'Clear all',
  )!;
  clear.click();
  await waitFor(() => document.getElementById('filter-url')?.textContent === '');
  check(filters[0].textContent?.includes('All case groups'), 'Clear all resets Case Group');
  check(more.getAttribute('aria-expanded') === 'false', 'Clear all collapses advanced filters');
}

run()
  .then(() => {
    const output = parent.document.createElement('output');
    output.id = 'test-result';
    output.textContent = 'passed';
    parent.document.body.append(output);
  })
  .catch((error) => {
    const output = parent.document.createElement('output');
    output.id = 'test-result';
    output.textContent = error.stack;
    parent.document.body.append(output);
  });
