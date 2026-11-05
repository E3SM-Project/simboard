import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { api } from '../../src/api/api';
import { AuthContext } from '../../src/auth/context';
import { CaseDetailsPage } from '../../src/features/catalog/CaseDetailsPage';
import { CasesPage } from '../../src/features/catalog/CasesPage';
import { describeSimulatedDuration } from '../../src/features/catalog/caseUtils';
import { CaseArtifactsTable } from '../../src/features/catalog/components/CaseArtifactsTable';
import {
  CaseConfigurationDetails,
  CaseConfigurationSummary,
} from '../../src/features/catalog/components/CaseConfiguration';
import { HomePage } from '../../src/features/home/HomePage';
import '../../src/index.css';
import { useCaseExecutions } from '../../src/lib/catalog/hooks/useCaseExecutions';
import { catalogQueryKeys } from '../../src/lib/catalog/queryKeys';
import { CaseCompareRoute } from '../../src/routes/CaseCompareRoute';
import type {
  CaseDetailOut,
  ConfigurationFieldOut,
  ExecutionOut,
  SimulationDurationOut,
} from '../../src/types';

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
const duration = (overrides: Partial<SimulationDurationOut> = {}): SimulationDurationOut => ({
  days: 365,
  months: 12,
  years: 1,
  calendars: ['gregorian'],
  calendarAssumed: false,
  partial: false,
  excludedExecutionCount: 0,
  ...overrides,
});
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
  simulatedDuration: duration({
    days: 730,
    months: 24,
    years: 2,
    partial: true,
    excludedExecutionCount: 1,
    calendarAssumed: true,
  }),
  latestExecution: { executionId: 'run-105', runEndDate: '2026-11-02T12:00:00Z' },
};
client.setQueryData(['cases', 'readable-detail', 'chrysalis', 'test.user', 'test.case'], record);
client.setQueryData(catalogQueryKeys.cases.detail(record.id), record);
executions.forEach((execution, index) =>
  client.setQueryData(catalogQueryKeys.executions.detail(execution.id), {
    ...execution,
    caseName: record.name,
    machine: { name: 'chrysalis' },
    hpcUsername: 'test.user',
    simulationStartDate: '0001-01-01',
    simulationEndDate: '0002-01-01',
    initializationType: 'hybrid',
    runStartDate: null,
    runEndDate: null,
    compiler: index === 1 ? 'gnu' : null,
    groupedArtifacts: {},
    artifacts: [
      {
        id: 'output',
        kind: 'output',
        uri: `/archive/${'long-path-segment/'.repeat(15)}${index === 2 ? 'alternate' : 'reference'}/run`,
      },
    ],
  }),
);
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
      renderCompareSection={({ caseId, onClose }) => (
        <CaseCompareRoute
          caseId={caseId}
          onClose={onClose}
          selectedCaseExecutionIdsByCase={selectedIds}
          setSelectedCaseExecutionIdsForCase={(id, ids) => setSelectedIds({ [id]: ids })}
        />
      )}
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

async function waitFor(checkReady: () => unknown, message = 'rendered case details') {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (checkReady()) return;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error(`Timed out waiting for ${message}`);
}

async function run() {
  const expectedWidth = Number(new URLSearchParams(location.search).get('width'));
  check(
    window.innerWidth === expectedWidth,
    `Expected viewport ${expectedWidth}, got ${window.innerWidth}`,
  );
  if (!new URLSearchParams(location.search).has('capture')) {
    await checkHomepage();
    await checkCasesFilters();
  }
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
    const summaryLabels = [
      'Latest Execution',
      'Total Simulated Duration',
      'Machine',
      'HPC Username',
      'Compset Alias',
      'Compset Long Name',
      'Grid Alias',
      'Grid Long Name',
    ];
    for (const text of summaryLabels) {
      const label = [...document.querySelectorAll('dt')].find(
        (element) => element.textContent === text,
      );
      check(label, `Metadata label exists: ${text}`);
      const style = getComputedStyle(label!);
      check(
        style.fontSize === '13px' && style.fontWeight === '600',
        `Metadata label uses muted semibold typography: ${text}`,
      );
      const valueStyle = getComputedStyle(label!.parentElement!.querySelector('dd')!);
      check(
        valueStyle.fontSize === '14px' && valueStyle.fontWeight === '400',
        `Metadata value uses normal primary typography: ${text}`,
      );
      check(
        style.color !== valueStyle.color,
        `Metadata label and value have distinct color hierarchy: ${text}`,
      );
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
    const metadata = document.querySelector('[aria-label="Case summary"]')!;
    const metadataCard = document.querySelector('[data-case-metadata]')!;
    const identityLabels = [...metadataCard.querySelectorAll('label')].filter((label) =>
      ['Case Group', 'Case Classification'].includes(label.textContent ?? ''),
    );
    check(identityLabels.length === 2, 'Group and classification appear once in Case Metadata');
    const identityBounds = identityLabels.map((label) => label.getBoundingClientRect());
    const summaryColumns = [...metadata.children].map((field) => field.getBoundingClientRect());
    check(
      Math.abs(identityBounds[0].left - summaryColumns[0].left) < 1,
      'Case Group aligns with first metadata column',
    );
    if (window.innerWidth >= 640) {
      check(
        Math.abs(identityBounds[1].left - summaryColumns[1].left) < 1,
        'Case Classification aligns with adjacent second metadata column',
      );
      check(
        Math.abs(identityBounds[0].top - identityBounds[1].top) < 1,
        'Case context fields share first row',
      );
    } else {
      check(
        identityBounds[1].top > identityBounds[0].top,
        'Case context fields stack in order on mobile',
      );
    }
    check(
      ![...metadataCard.querySelectorAll('h2, h3')].some((heading) =>
        ['Case Context', 'Execution Summary', 'Model Configuration'].includes(
          heading.textContent ?? '',
        ),
      ),
      'Metadata rows remain compact without redundant subtitles',
    );
    check(
      identityLabels[0].getBoundingClientRect().top < metadata.getBoundingClientRect().top,
      'Case identity row precedes execution and configuration rows',
    );
    for (const label of identityLabels) {
      const labelStyle = getComputedStyle(label);
      const valueStyle = getComputedStyle(label.nextElementSibling!);
      check(
        labelStyle.fontSize === '13px' && labelStyle.fontWeight === '600',
        'Case identity labels match metadata typography',
      );
      check(
        valueStyle.fontSize === '14px' && valueStyle.fontWeight === '400',
        'Case identity values match metadata typography',
      );
    }
    const descriptiveDetails = [...document.querySelectorAll('h2')]
      .find((heading) => heading.textContent === 'Case Notes')!
      .closest('section')!;
    check(
      [...descriptiveDetails.querySelectorAll('label')]
        .map((label) => label.textContent)
        .join('|') === 'Description|Key Features|Known Issues|Notes',
      'Case Notes contains only descriptive fields in requested order',
    );
    const featureLabel = [...descriptiveDetails.querySelectorAll('label')].find(
      (label) => label.textContent === 'Key Features',
    )!;
    const issuesLabel = [...descriptiveDetails.querySelectorAll('label')].find(
      (label) => label.textContent === 'Known Issues',
    )!;
    if (window.innerWidth >= 768) {
      check(
        Math.abs(
          featureLabel.getBoundingClientRect().top - issuesLabel.getBoundingClientRect().top,
        ) < 1,
        'Features and issues align side by side',
      );
    } else {
      check(
        featureLabel.getBoundingClientRect().top < issuesLabel.getBoundingClientRect().top,
        'Features precede issues on mobile',
      );
    }
    check(
      metadata.textContent?.includes('SHARED-COMPSET'),
      'Shared alias appears beneath metadata',
    );
    check(metadata.textContent?.includes('SHARED-GRID'), 'Shared grid appears beneath metadata');
    check(!metadata.textContent?.includes('v3'), 'Model tag stays out of primary summary');
    check(
      [...metadata.querySelectorAll('dt')].map((label) => label.textContent).join('|') ===
        summaryLabels.join('|'),
      'Summary preserves exact reading order',
    );
    const fields = [...metadata.children].map((element) => element.getBoundingClientRect());
    const columns = window.innerWidth >= 1024 ? 4 : window.innerWidth >= 640 ? 2 : 1;
    fields.forEach((field, index) => {
      check(
        Math.abs(field.height - fields[index - (index % columns)].height) < 1,
        'Summary fields align within each row',
      );
      if (index % columns !== 0) {
        check(Math.abs(field.top - fields[index - 1].top) < 1, 'Summary row labels align');
        check(field.left > fields[index - 1].left, 'Summary reads left to right');
      } else if (index > 0) {
        check(field.top > fields[index - 1].top, 'Summary reads top to bottom');
      }
    });
    const stats = metadata;
    check(
      stats.textContent?.startsWith('Latest Execution'),
      'Latest execution is first summary statistic',
    );
    check(
      stats.textContent?.includes('2 years (partial)'),
      'Use server duration, not coverage or loaded execution intervals',
    );
    check(stats.textContent?.includes('2026-11-02'), 'Latest run date differs from page update');
    check(
      stats.querySelector('a')?.getAttribute('href')?.endsWith('/run-105'),
      'Latest run can be outside loaded page',
    );
    check(!stats.textContent?.includes('Case hash groups'), 'Hash count removed from summary');
    check(!stats.textContent?.includes('Executions'), 'Execution count removed from summary');
    check(
      stats.textContent?.includes('Gregorian calendar assumed'),
      'Calendar assumption is visible',
    );
    if (role === 'anonymous') {
      const durationTrigger = stats.querySelector<HTMLElement>('[tabindex="0"]')!;
      durationTrigger.focus();
      await waitFor(() => document.querySelector('[role="tooltip"]'));
      check(
        document.querySelector('[role="tooltip"]')?.textContent ===
          describeSimulatedDuration(record.simulatedDuration),
        'Duration tooltip explains cumulative semantics and exclusions',
      );
      durationTrigger.blur();
    }
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
  const toolbar = document.querySelector<HTMLElement>('[data-execution-toolbar]')!;
  if (innerWidth >= 900)
    check(
      toolbar.getBoundingClientRect().height < 150,
      'Execution toolbar stays compact on laptops',
    );
  check(!toolbar.textContent?.includes('Actions'), 'Toolbar avoids redundant section labels');
  check(
    [...table.querySelectorAll('th')].map((element) => element.textContent).join('|') ===
      'Select|Simulation dates|Initialization|Run dates|Execution ID',
    'Flat execution column order',
  );
  const row = table.tBodies[0].rows[0];
  check(row.cells[1].textContent === '0001-01-01 → 0002-01-01', 'Simulation dates match column');
  check(row.cells[2].textContent === 'hybrid', 'Initialization value stays unchanged');
  check(row.cells[3].textContent === '2026-10-01', 'Same-day run dates remain compact');
  check(row.cells[4].querySelector('a')?.textContent === 'run-1', 'Oldest simulation stays first');
  check(
    ![...document.querySelectorAll('button')].some(
      (button) => button.textContent === 'Group by Case Hash',
    ),
    'Single hash hides grouping controls',
  );
  check(
    row.cells[4].textContent?.includes('Details · Varies'),
    'Known initialization variation is discoverable',
  );
  row.cells[4].querySelector('summary')!.click();
  check(
    row.cells[4].textContent?.includes('Machine: —'),
    'Unavailable metadata uses shared placeholder',
  );
  row.cells[4].querySelector('summary')!.click();
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
  await waitFor(
    () => table.tBodies[0].rows[0].cells[4].querySelector('a')?.textContent === 'run-3',
  );
  check(
    simulationHeader.getAttribute('aria-sort') === 'descending',
    'Simulation sort toggles descending',
  );
  runHeader.querySelector('button')!.click();
  await waitFor(
    () => table.tBodies[0].rows[0].cells[4].querySelector('a')?.textContent === 'run-1',
  );
  check(runHeader.getAttribute('aria-sort') === 'ascending', 'Run sort starts ascending');
  check(!simulationHeader.hasAttribute('aria-sort'), 'Previously sorted header omits aria-sort');
  runHeader.querySelector('button')!.click();
  await waitFor(
    () => table.tBodies[0].rows[0].cells[4].querySelector('a')?.textContent === 'run-2',
  );
  check(
    table.tBodies[0].rows[2].cells[4].querySelector('a')?.textContent === 'run-3',
    'Missing run dates remain last',
  );
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
    (element) => element.textContent === 'Compare (3)',
  )!;
  check(!compare.disabled, 'Selection still enables comparison');
  compare.click();
  await waitFor(() => document.querySelector('[data-case-comparison]'));
  await checkExecutionComparison(compare);
  await checkPickerSelectionLimits();

  const groupedRecord = {
    ...record,
    executions: [
      ...executions,
      { ...executions[2], id: 'missing-hash', executionId: 'fallback-run', caseHash: null },
    ],
  };
  client.setQueryData(
    catalogQueryKeys.cases.readableDetail('chrysalis', 'test.user', 'test.case'),
    groupedRecord,
  );
  client.setQueryData(catalogQueryKeys.cases.detail(record.id), groupedRecord);
  client.setQueryData(catalogQueryKeys.executions.detail('missing-hash'), {
    ...client.getQueryData<ExecutionOut>(catalogQueryKeys.executions.detail('execution-3')),
    id: 'missing-hash',
    executionId: 'fallback-run',
  });
  await waitFor(() =>
    [...document.querySelectorAll('button')].find(
      (element) => element.textContent === 'Group by Case Hash',
    ),
  );
  const grouped = [...document.querySelectorAll('button')].find(
    (element) => element.textContent === 'Group by Case Hash',
  )!;
  grouped.click();
  await waitFor(() => document.querySelector('table table'));
  const groupTable = document.querySelector('table table')!;
  check(
    [...document.querySelector('table')!.tHead!.rows[0].cells]
      .map((cell) => cell.textContent?.trim())
      .join('|') === 'Case Hash|Executions|Simulation window|Actions',
    'Hash groups use concise contextual columns',
  );
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
  const fallbackGroup = [
    ...document.querySelectorAll<HTMLButtonElement>('button[aria-expanded]'),
  ].find((button) => button.textContent?.includes('Missing Case Hash'))!;
  fallbackGroup.click();
  await waitFor(() => document.querySelector('[aria-label="Select fallback-run for compare"]'));
  document
    .querySelector<HTMLButtonElement>('[aria-label="Select fallback-run for compare"]')!
    .click();
  await waitFor(
    () =>
      document
        .querySelector('[aria-label="Select fallback-run for compare"]')
        ?.getAttribute('aria-checked') === 'true',
  );
  [...document.querySelectorAll<HTMLButtonElement>('button')]
    .find((button) => button.textContent === 'Compare (3)')!
    .click();
  await waitFor(() => document.querySelector('[aria-label="Remove fallback-run"]'));
  const hashDialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
  [...hashDialog.querySelectorAll<HTMLButtonElement>('button')]
    .find((button) => button.textContent?.includes('Edit executions'))!
    .click();
  await waitFor(() => document.querySelector('[aria-label="Compare fallback-run"]'));
  const hashPicker = document.querySelector<HTMLElement>('[aria-label="Select executions"]')!;
  check(
    hashPicker.textContent?.includes('Hash: test-hash') &&
      hashPicker.textContent?.includes('Missing Case Hash'),
    'Picker preserves conditional known and fallback hash context',
  );
  hashPicker.querySelector<HTMLButtonElement>('[aria-label="Compare fallback-run"]')!.click();
  await waitFor(() => !hashDialog.querySelector('[aria-label="Remove fallback-run"]'));
  [...hashPicker.querySelectorAll<HTMLButtonElement>('button')]
    .find((button) => button.textContent === 'Done')!
    .click();
  await waitFor(
    () => !document.querySelector('[aria-label="Select executions"][data-state="open"]'),
  );
  hashDialog.querySelector<HTMLButtonElement>(':scope > button')!.click();
  await waitFor(() => !document.querySelector('[data-case-comparison]'));
  check(
    document
      .querySelector('[aria-label="Select fallback-run for compare"]')
      ?.getAttribute('aria-checked') === 'false',
    'Cross-group picker edits synchronize table',
  );
  groupTable.querySelectorAll('th')[1].querySelector('button')!.click();
  await waitFor(
    () => groupTable.tBodies[0].rows[0].cells[4].querySelector('a')?.textContent === 'run-1',
  );
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
  client.setQueryData(['cases', 'readable-detail', 'chrysalis', 'test.user', 'test.case'], record);
  client.setQueryData(catalogQueryKeys.cases.detail(record.id), record);
  await waitFor(
    () =>
      ![...document.querySelectorAll('button')].some(
        (element) => element.textContent === 'Group by Case Hash',
      ),
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
  check(!compare.disabled, 'Comparison selection stays available while sorting');
  finishFetch();
  await waitFor(() => client.getQueryState(runAscKey)?.status === 'success');
  api.defaults.adapter = originalAdapter;

  const edit = [...document.querySelectorAll('button')].find(
    (element) => element.textContent === 'Edit',
  )!;
  edit.click();
  await waitFor(() => document.getElementById('case-group'));
  check(
    document.getElementById('case-group')!.closest('[data-case-metadata]'),
    'Case Group editor lives in Case Metadata',
  );
  check(
    document.querySelector('[aria-label="Case classification"]')!.closest('[data-case-metadata]'),
    'Classification editor lives in Case Metadata',
  );
  check(
    (document.getElementById('case-group') as HTMLInputElement).value === record.caseGroup,
    'Editing retains Case Group',
  );
  const groupInput = document.getElementById('case-group') as HTMLInputElement;
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(
    groupInput,
    'temporary-group',
  );
  groupInput.dispatchEvent(new Event('input', { bubbles: true }));
  await waitFor(() =>
    [...document.querySelectorAll<HTMLButtonElement>('button')].some(
      (button) => button.textContent === 'Save Changes' && !button.disabled,
    ),
  );
  const cancel = [...document.querySelectorAll('button')].find(
    (element) => element.textContent === 'Cancel',
  )!;
  cancel.click();
  await waitFor(() => !document.getElementById('case-group'));
  check(
    document.querySelector('[data-case-metadata]')?.textContent?.includes(record.caseGroup),
    'Cancel restores original Case Group in metadata',
  );
  check(
    !document.querySelector('[data-case-metadata]')?.textContent?.includes('temporary-group'),
    'Cancel discards edits from relocated metadata field',
  );

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

async function checkExecutionComparison(compareButton: HTMLButtonElement) {
  const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
  const workspace = dialog.querySelector<HTMLElement>('[data-case-comparison]')!;
  const region = workspace.querySelector<HTMLElement>('[aria-label="Execution comparison"]')!;
  const button = (text: string) =>
    [...workspace.querySelectorAll('button')].find((item) => item.textContent === text)!;
  const rows = () =>
    [...region.querySelectorAll('tbody tr')].filter((row) => row.querySelector('td'));
  const changed = () => region.querySelectorAll('[data-different="true"]').length;
  const bounds = dialog.getBoundingClientRect();
  check(bounds.width <= innerWidth * 0.95 && bounds.left > 0, 'Dialog leaves page context visible');
  check(bounds.height <= innerHeight * 0.91 && bounds.top > 0, 'Dialog fits inside viewport');
  check(bounds.height < innerHeight * 0.8, 'Short comparison does not fill viewport');
  check(
    document.activeElement?.textContent === 'Compare case executions',
    'Initial focus lands on dialog title',
  );
  check(document.body.getAttribute('data-scroll-locked'), 'Modal locks background scrolling');
  check(
    dialog.getAttribute('aria-labelledby') === dialog.querySelector('h2')?.id,
    'Dialog has an accessible title',
  );
  compareButton.focus();
  check(
    dialog.contains(document.activeElement),
    'Modal contains focus when background control receives focus',
  );
  check(
    button('Differences (2)').getAttribute('aria-pressed') === 'true',
    'Differences selected by default',
  );
  check(rows().length === 2, 'Only two differing fields appear');
  workspace.querySelector<HTMLButtonElement>('[aria-label="Use run-1 as reference"]')!.click();
  await waitFor(() => changed() === 2);
  const group = [...workspace.querySelectorAll<HTMLButtonElement>('button')].find((item) =>
    item.textContent?.includes('Locations'),
  )!;
  group.click();
  await waitFor(() => rows().length === 1);
  check(button('Differences (2)'), 'Collapsing a group preserves difference count');
  group.click();
  await waitFor(() => rows().length === 2);
  if (new URLSearchParams(location.search).get('capture') === 'differences') {
    document.body.dataset.captureReady = 'true';
    await new Promise(() => {});
  }
  check(
    region.textContent?.includes('Differs from reference column.'),
    'Differences have non-color cue',
  );
  const copy = region.querySelector<HTMLButtonElement>('[aria-label="Copy path"]')!;
  check(
    copy && copy.parentElement?.getAttribute('title')?.includes('long-path-segment'),
    'Full clamped path remains accessible',
  );
  let copied = '';
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: {
      writeText: async (value: string) => {
        copied = value;
      },
    },
  });
  copy.click();
  check(copied.endsWith('/run') && copied.length > 200, 'Copy retains entire path');

  button('All fields').click();
  await waitFor(() => rows().length > 20);
  check(changed() === 2, 'All fields keeps identical values neutral and differences highlighted');
  if (new URLSearchParams(location.search).get('capture') === 'all') {
    document.body.dataset.captureReady = 'true';
    await new Promise(() => {});
  }
  check(region.scrollHeight > region.clientHeight, 'Long table scrolls within dialog');
  const corner = region.querySelector<HTMLElement>('thead th')!;
  region.scrollTop = 180;
  region.scrollLeft = 500;
  await new Promise((resolve) => setTimeout(resolve, 20));
  check(
    Math.abs(corner.getBoundingClientRect().top - region.getBoundingClientRect().top) < 3,
    'Execution headers stay sticky vertically',
  );
  check(
    Math.abs(corner.getBoundingClientRect().left - region.getBoundingClientRect().left) < 3,
    'Field header stays sticky horizontally',
  );
  check(document.documentElement.scrollWidth <= innerWidth, 'Comparison causes no page overflow');

  workspace.querySelector<HTMLButtonElement>('[aria-label="Use run-2 as reference"]')!.click();
  await waitFor(() =>
    region.querySelector('thead th:nth-child(2)')?.textContent?.includes('run-2'),
  );
  check(changed() === 3, 'Changing reference updates highlighted values');
  button('Differences (2)').click();
  await waitFor(() => rows().length === 2);
  workspace.querySelector<HTMLButtonElement>('[aria-label="Hide run-2"]')!.click();
  await waitFor(() => button('Differences (1)'), 'one difference after hide');
  check(changed() === 1, 'Hiding reference updates count and highlights');
  button('Show run-2').click();
  await waitFor(() => button('Differences (2)'), 'two differences after show');
  workspace.querySelector<HTMLButtonElement>('[aria-label="Remove run-3"]')!.click();
  await waitFor(() => button('Differences (1)'), 'one difference after remove');
  check(!region.textContent?.includes('run-3'), 'Remove updates selected columns');
  workspace.querySelector<HTMLButtonElement>('[aria-label="Hide run-1"]')!.click();
  await waitFor(() => button('Differences (0)'), 'zero differences with one column');
  check(
    button('Differences (0)').disabled &&
      button('All fields').getAttribute('aria-pressed') === 'true',
    'Single column shows All fields and disables unavailable difference mode',
  );
  check(
    rows().length > 20 && changed() === 0,
    'One visible execution retains all fields without false differences',
  );
  workspace.querySelector<HTMLButtonElement>('[aria-label="Hide run-2"]')!.click();
  await waitFor(() => region.textContent?.includes('Unhide an execution'), 'all hidden state');
  button('Show run-1').click();
  button('Show run-2').click();
  await waitFor(() => button('Differences (1)'), 'restored columns');

  const pickerTrigger = [...dialog.querySelectorAll<HTMLButtonElement>('button')].find((item) =>
    item.textContent?.includes('Edit executions'),
  )!;
  pickerTrigger.click();
  await waitFor(() => document.querySelector('[aria-label="Search execution candidates"]'));
  const picker = document.querySelector<HTMLElement>('[aria-label="Select executions"]')!;
  check(
    document.activeElement?.getAttribute('aria-label') === 'Search execution candidates',
    'Picker focuses search',
  );
  check(!picker.textContent?.includes('Hash:'), 'Single-hash picker omits hash context');
  const option = (id: string) =>
    picker.querySelector<HTMLButtonElement>(`[aria-label="Compare ${id}"]`)!;
  check(option('run-1').getAttribute('aria-checked') === 'true', 'Picker reflects table selection');
  option('run-3').click();
  await waitFor(() => region.textContent?.includes('run-3'));
  check(
    region.querySelector('thead th:nth-child(2)')?.textContent?.includes('run-2'),
    'Adding execution preserves reference',
  );
  option('run-2').click();
  await waitFor(() => !region.textContent?.includes('run-2'));
  check(
    region.querySelector('thead th:nth-child(2)')?.textContent?.includes('run-1'),
    'Removing reference chooses first remaining display column',
  );
  option('run-3').click();
  await waitFor(() => workspace.textContent?.includes('Select at least two executions'));
  option('run-1').click();
  await waitFor(() => pickerTrigger.textContent?.includes('(0/5)'));
  check(dialog.isConnected && picker.isConnected, 'Zero selections keeps dialog and picker open');
  option('run-1').click();
  await waitFor(() => pickerTrigger.textContent?.includes('(1/5)'), 'restore first selection');
  option('run-2').click();
  await waitFor(() => pickerTrigger.textContent?.includes('(2/5)'), 'restore second selection');
  picker.querySelector<HTMLInputElement>('input')!.focus();
  await new Promise((resolve) => setTimeout(resolve, 250));
  document.activeElement!.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
  );
  await waitFor(
    () => !document.querySelector('[aria-label="Select executions"][data-state="open"]'),
    'picker Escape',
  );
  check(dialog.isConnected, 'Escape closes picker before dialog');
  await waitFor(() => document.activeElement === pickerTrigger, 'Picker restores focus to trigger');

  dialog.querySelector<HTMLElement>('h2')!.focus();
  await new Promise((resolve) => setTimeout(resolve, 250));
  document.activeElement!.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
  );
  await waitFor(() => !document.querySelector('[role="dialog"]'), 'Escape dismissal');
  check(document.activeElement === compareButton, 'Escape restores focus to Compare button');
  check(!compareButton.disabled, 'Closing preserves execution selections');
  compareButton.click();
  await waitFor(() => document.querySelector('[role="dialog"]'));
  document.querySelector<HTMLButtonElement>('[role="dialog"] > button')!.click();
  await waitFor(() => !document.querySelector('[role="dialog"]'));
}

async function checkPickerSelectionLimits() {
  const extra = Array.from({ length: 123 }, (_, index) => index + 4).map((number) => ({
    ...executions[0],
    id: `execution-${number}`,
    executionId: number <= 6 ? `run-${number}` : `extra-${number}`,
  }));
  const expanded = { ...record, executions: [...executions, ...extra] };
  client.setQueryData(
    catalogQueryKeys.cases.readableDetail('chrysalis', 'test.user', 'test.case'),
    expanded,
  );
  client.setQueryData(catalogQueryKeys.cases.detail(record.id), expanded);
  for (const summary of extra) {
    const details = client.getQueryData<ExecutionOut>(
      catalogQueryKeys.executions.detail('execution-1'),
    )!;
    client.setQueryData(catalogQueryKeys.executions.detail(summary.id), {
      ...details,
      id: summary.id,
      executionId: summary.executionId,
    });
  }
  await waitFor(
    () =>
      document.querySelectorAll('table tbody [role="checkbox"]').length ===
      expanded.executions.length,
    'all case summaries',
  );
  const tableSearch = document.querySelector<HTMLInputElement>('[aria-label="Search executions"]')!;
  const setInput = (input: HTMLInputElement, value: string) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  };
  setInput(tableSearch, 'run-1');
  await waitFor(
    () => document.querySelectorAll('table tbody [role="checkbox"]').length === 1,
    'table filter',
  );
  const compare = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent === 'Compare (2)',
  )!;
  compare.click();
  await waitFor(() => document.querySelector('[data-case-comparison]'));
  const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
  const trigger = [...dialog.querySelectorAll<HTMLButtonElement>('button')].find((button) =>
    button.textContent?.includes('Edit executions'),
  )!;
  trigger.click();
  await waitFor(() => document.querySelector('[aria-label="Execution candidates"]'));
  const picker = document.querySelector<HTMLElement>('[aria-label="Select executions"]')!;
  const option = (id: number) =>
    picker.querySelector<HTMLButtonElement>(`[aria-label="Compare run-${id}"]`)!;
  check(
    picker.querySelectorAll('[role="checkbox"]').length === expanded.executions.length,
    'Picker includes filtered-out and unloaded-metadata executions',
  );
  const candidateList = picker.querySelector<HTMLElement>('[aria-label="Execution candidates"]')!;
  check(
    candidateList.scrollHeight > candidateList.clientHeight,
    'Large picker list scrolls inside bounded popover',
  );
  option(1).focus();
  option(1).dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
  check(
    document.activeElement?.getAttribute('role') === 'checkbox' &&
      document.activeElement !== option(1),
    'Arrow keys navigate picker candidates',
  );
  const pickerSearch = picker.querySelector<HTMLInputElement>('input')!;
  setInput(pickerSearch, 'run-6');
  await waitFor(() => picker.querySelectorAll('[role="checkbox"]').length === 1, 'picker search');
  check(option(6), 'Picker search indexes Execution ID');
  setInput(pickerSearch, '');
  await waitFor(
    () => picker.querySelectorAll('[role="checkbox"]').length === expanded.executions.length,
  );
  const detailsSix = client.getQueryData<ExecutionOut>(
    catalogQueryKeys.executions.detail('execution-6'),
  )!;
  client.removeQueries({
    queryKey: catalogQueryKeys.executions.detail('execution-6'),
    exact: true,
  });
  const originalAdapter = api.defaults.adapter;
  let rejectDetails: ((error: Error) => void) | undefined;
  let failOnce = true;
  api.defaults.adapter = async (config) => {
    if (!config.url?.endsWith('/execution-6')) throw new Error(`Unexpected request: ${config.url}`);
    if (failOnce) {
      failOnce = false;
      await new Promise((_resolve, reject) => {
        rejectDetails = reject;
      });
    }
    return { config, status: 200, statusText: 'OK', headers: {}, data: detailsSix };
  };
  for (const id of [4, 5, 6]) {
    option(id).click();
    await waitFor(() => option(id).getAttribute('aria-checked') === 'true');
  }
  await waitFor(
    () => dialog.textContent?.includes('Loading details for 1 selected execution'),
    'pending detail request has loading state',
  );
  check(
    !dialog.querySelector('[aria-label="Remove run-6"]'),
    'Pending details do not produce false comparison values',
  );
  rejectDetails!(new Error('Fixture detail request failed'));
  await waitFor(
    () => dialog.textContent?.includes('Could not load 1 selected execution'),
    'failed detail request has error state',
  );
  const retry = [...dialog.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent === 'Retry execution details',
  )!;
  retry.click();
  await waitFor(
    () => dialog.querySelector('[aria-label="Remove run-6"]'),
    'retry restores comparison column',
  );
  api.defaults.adapter = originalAdapter;
  check(trigger.textContent?.includes('(5/5)'), 'Picker reaches five selections');
  check(option(3).disabled && !option(1).disabled, 'Only unselected candidates disable at five');
  check(picker.textContent?.includes('Limit: 5 executions.'), 'Picker explains selection cap');
  option(4).click();
  await waitFor(() => !option(3).disabled);
  picker.querySelectorAll<HTMLButtonElement>('button').forEach((button) => {
    if (button.textContent === 'Done') button.click();
  });
  await waitFor(
    () => !document.querySelector('[aria-label="Select executions"][data-state="open"]'),
  );
  dialog.querySelector<HTMLButtonElement>(':scope > button')!.click();
  await waitFor(() => !document.querySelector('[data-case-comparison]'));
  setInput(tableSearch, '');
  await waitFor(
    () =>
      document.querySelectorAll('table tbody [role="checkbox"]').length ===
      expanded.executions.length,
  );
  check(
    document
      .querySelector('[aria-label="Select run-6 for compare"]')
      ?.getAttribute('aria-checked') === 'true',
    'Picker edits synchronize filtered table selections',
  );
  const clear = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent === 'Clear selection',
  )!;
  clear.click();
  await waitFor(
    () =>
      document
        .querySelector('[aria-label="Select run-1 for compare"]')
        ?.getAttribute('aria-checked') === 'false',
  );
  for (const id of [1, 2]) {
    document
      .querySelector<HTMLButtonElement>(`[aria-label="Select run-${id} for compare"]`)!
      .click();
    await waitFor(
      () =>
        document
          .querySelector(`[aria-label="Select run-${id} for compare"]`)
          ?.getAttribute('aria-checked') === 'true',
    );
  }
  client.setQueryData(
    catalogQueryKeys.cases.readableDetail('chrysalis', 'test.user', 'test.case'),
    record,
  );
  client.setQueryData(catalogQueryKeys.cases.detail(record.id), record);
  await waitFor(() => document.querySelectorAll('table tbody [role="checkbox"]').length === 3);
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
    git_commit_hash: field('model-hash', 'run-1'),
    source_code_path: field('/model/source', 'run-1'),
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
      grid_alias: { value: null, varies: true, incomplete: true, hasDifferences: true },
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
        simulatedDuration: duration({ days: 10950, months: 360, years: 30, calendarAssumed: true }),
      },
      {
        key: 'missing:run-3',
        caseHash: null,
        executionIds: ['run-3'],
        configuration: {
          ...firstConfiguration,
          grid_alias: field(null, 'run-3'),
          compset_long_name: field('OTHER_'.repeat(100), 'run-3'),
          grid_long_name: field('other-grid-long', 'run-3'),
        },
        coverage: { years: null, partial: true, excludedExecutionCount: 1 },
        simulatedDuration: duration({
          days: null,
          months: null,
          years: null,
          partial: true,
          excludedExecutionCount: 1,
        }),
      },
    ],
  };
  const identity = { machineName: 'chrysalis', hpcUsername: 'test.user', caseName: record.name };
  root.render(
    <MemoryRouter>
      <div className="min-w-0 p-6">
        <div className="h-screen" aria-hidden="true" />
        <CaseConfigurationSummary record={configured} identity={identity} />
        <CaseConfigurationDetails record={configured} identity={identity} />
        <div className="h-screen" aria-hidden="true" />
      </div>
    </MemoryRouter>,
  );
  await waitFor(() => document.querySelector('[data-case-configuration]'));
  const summary = document.querySelector('[aria-label="Case summary"]')!;
  check(summary.textContent?.includes('shared-alias'), 'Summary retains shared values');
  check(summary.textContent?.includes('Differs by case hash'), 'Summary flags differing values');
  check(!summary.textContent?.includes('Model tag'), 'Technical metadata stays out of summary');
  check(
    summary.textContent?.includes('Some executions unavailable'),
    'Summary distinguishes missing observations from disagreement',
  );
  check(
    summary.textContent?.includes('Changes within Case Hash'),
    'Summary flags within-hash differences',
  );
  const details = document.querySelector<HTMLDetailsElement>('[data-case-configuration]')!;
  const table = details.querySelector('table')!;
  check(
    !details.open && !table.checkVisibility(),
    'Comparison starts collapsed with no visible table',
  );
  details.querySelector('summary')!.click();
  check(details.open && table.checkVisibility(), 'Comparison disclosure opens table manually');
  details.querySelector('summary')!.click();
  check(!details.open, 'Comparison disclosure closes table manually');
  const hashes = [...table.querySelectorAll('thead th')].slice(1);
  check(hashes.length === 2, 'One comparison column per hash or missing-hash identity');
  check(
    hashes[0].textContent?.includes('Reference') && !hashes[1].textContent?.includes('Reference'),
    'First hash is clearly labeled as comparison reference',
  );
  check(!table.querySelector('tbody td:first-of-type mark'), 'Reference values stay unmarked');
  const changedToken = table.querySelector('tbody td:nth-of-type(2) mark')!;
  check(changedToken, 'Changed tokens receive inline highlighting');
  check(
    getComputedStyle(changedToken).backgroundColor !==
      getComputedStyle(changedToken.parentElement!).backgroundColor,
    'Token highlighting is visible without changing table layout',
  );
  check(!details.querySelector('[data-configuration-group]'), 'Per-hash metadata sections removed');
  check(!details.textContent?.includes('Expand metadata'), 'No expand metadata prompt');
  check(
    details
      .querySelector('p')
      ?.textContent?.includes(
        'Only configuration fields that differ between case hashes are shown.',
      ),
    'Concise comparison explanation',
  );
  check(
    details.querySelector('p')?.textContent?.includes('Case hashes identify CIME case instances.'),
    'Comparison briefly explains case hashes',
  );
  check(hashes[0].textContent?.includes('30 years'), 'Hash duration is cumulative, not coverage');
  check(
    !table.querySelector('thead')?.textContent?.includes('Gregorian calendar assumed'),
    'Hash columns omit calendar assumption labels',
  );
  check(
    !table.querySelector('thead')?.textContent?.includes('Simulated duration:'),
    'Hash columns show duration without repeating a label',
  );
  check(hashes[0].textContent?.includes('2 executions'), 'Execution count remains visible');
  check(!hashes[0].textContent?.includes('hash-'.repeat(40)), 'Hash is abbreviated');
  check(
    hashes[0].querySelector('[title]')?.getAttribute('title') === 'hash-'.repeat(40),
    'Full hash remains available',
  );
  check(
    hashes[1].textContent?.includes('Missing Case Hash: run-3'),
    'Hashless execution keeps identity',
  );
  check(
    hashes[1].textContent?.includes('Unavailable (partial)'),
    'Partial hash duration stays explicit',
  );
  const rowLabels = [...table.querySelectorAll('tbody th')].map((element) => element.textContent);
  check(
    rowLabels.join('|') === 'Compset Long Name|Grid Alias|Grid Long Name',
    'Only differing fields become rows, including both long names',
  );
  check(
    !table.querySelector('tbody')?.textContent?.includes('Duration'),
    'Duration stays outside configuration rows',
  );
  check(
    table.querySelector('tbody')?.textContent?.includes('Unavailable'),
    'Missing configuration value stays explicit',
  );
  const links = [...summary.querySelectorAll<HTMLAnchorElement>('a[href^="#case-configuration-"]')];
  check(links.length === 3, 'Every differing summary field has a comparison link');
  for (const link of links) {
    details.open = false;
    link.focus();
    check(document.activeElement === link, 'Difference link accepts keyboard focus');
    const previousHash = location.hash;
    link.click();
    check(details.open, 'Every Differs by link expands comparison before navigating');
    const target = document.getElementById(link.hash.slice(1))!;
    await new Promise((resolve) => setTimeout(resolve, 20));
    const rowLabel = document.getElementById(link.getAttribute('aria-controls')!)!;
    check(
      target === details && document.activeElement === rowLabel,
      'Difference link focuses matching row without scrolling to it',
    );
    const rowColor = getComputedStyle(rowLabel).backgroundColor;
    check(
      rowColor !== 'rgb(255, 255, 255)' && rowColor !== 'rgba(0, 0, 0, 0)',
      'Selected comparison row has visible highlight',
    );
    for (const cell of rowLabel.parentElement!.children) {
      check(
        getComputedStyle(cell).backgroundColor === rowColor,
        'Highlight spans field label and every hash value',
      );
    }
    check(
      [...table.querySelectorAll('tbody th')]
        .filter((label) => label !== rowLabel)
        .every((label) => getComputedStyle(label).backgroundColor !== rowColor),
      'Only selected row stays highlighted',
    );
    check(location.hash === previousHash, 'Difference link prevents native fragment jump');
    const bounds = target.getBoundingClientRect();
    if (bounds.height < window.innerHeight) {
      check(
        Math.abs((bounds.top + bounds.bottom) / 2 - window.innerHeight / 2) < 2,
        'Difference link centers comparison component',
      );
    }
    check(
      target.querySelector('h3')!.getBoundingClientRect().top >= 0 &&
        target.querySelector('h3')!.getBoundingClientRect().top < window.innerHeight,
      'Difference link keeps comparison heading in view',
    );
  }
  details.style.minHeight = '200vh';
  links[0].click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  const headingBounds = details.querySelector('h3')!.getBoundingClientRect();
  check(
    Math.abs((headingBounds.top + headingBounds.bottom) / 2 - window.innerHeight / 2) < 2,
    'Tall comparisons center their heading instead of jumping into table',
  );
  details.style.minHeight = '';
  check(
    table.querySelector('tbody a')?.getAttribute('href')?.endsWith('/run-1'),
    'Configuration links to execution source',
  );
  const changes = table.querySelector<HTMLDetailsElement>('tbody details')!;
  changes.querySelector('summary')!.click();
  check(changes.textContent?.includes('later-grid'), 'Later differences remain available');
  check(changes.textContent?.includes('Run date unavailable'), 'Undated provenance stays explicit');
  check(
    table.textContent?.includes('LONG_'.repeat(100)),
    'Long configuration values remain available',
  );
  check(
    document.documentElement.scrollWidth <= window.innerWidth,
    'Comparison has no page-wide overflow',
  );
  const first = configured.configurationGroups![0];
  const agreeing = {
    ...configured,
    configurationGroups: configured.configurationGroups!.slice(0, 1),
    sharedConfiguration: {
      ...configured.sharedConfiguration,
      grid_alias: { value: 'grid-one', varies: false, incomplete: false, hasDifferences: true },
    },
  };
  root.render(
    <MemoryRouter>
      <CaseConfigurationSummary record={agreeing} identity={identity} />
      <CaseConfigurationDetails record={agreeing} identity={identity} />
    </MemoryRouter>,
  );
  await waitFor(() => !document.querySelector('[data-case-configuration]'));
  check(
    !document.body.textContent?.includes('Configuration Differences'),
    'Single hash hides entire comparison section',
  );
  const agreeingSummary = document.querySelector('[aria-label="Case summary"]')!;
  check(
    agreeingSummary.textContent?.includes('Changes within Case Hash'),
    'Agreeing baselines still flag within-hash changes',
  );
  check(
    !agreeingSummary.textContent?.includes('Differs by case hash'),
    'Within-hash changes do not imply differing baselines',
  );
  check(
    agreeingSummary
      .querySelector('a[title="Source execution: run-1"]')
      ?.getAttribute('href')
      ?.endsWith('/run-1'),
    'Shared summary value retains execution source',
  );
  const withinHashChanges = agreeingSummary.querySelector<HTMLDetailsElement>('details')!;
  check(!withinHashChanges.open, 'Within-hash observations stay compact');
  withinHashChanges.querySelector('summary')!.click();
  check(
    withinHashChanges.open && withinHashChanges.textContent?.includes('later-grid'),
    'Within-hash observations remain accessible without a comparison row',
  );
  check(
    withinHashChanges.querySelector('a')?.getAttribute('href')?.endsWith('/run-2'),
    'Alternate observation retains execution source',
  );
  const identical: CaseDetailOut = {
    ...agreeing,
    configurationGroups: [
      first,
      { ...first, key: 'two', caseHash: 'second-hash', executionIds: ['run-3'] },
    ],
  };
  root.render(
    <MemoryRouter>
      <CaseConfigurationDetails record={identical} identity={identity} />
    </MemoryRouter>,
  );
  await waitFor(() => !document.querySelector('[aria-label="Case summary"]'));
  check(
    !document.querySelector('[data-case-configuration]'),
    'Identical hashes hide entire comparison section',
  );
  const many: CaseDetailOut = {
    ...configured,
    configurationGroups: Array.from({ length: 8 }, (_, index) => ({
      ...first,
      key: `hash-${index}`,
      caseHash: `hash-${index}`,
      configuration: {
        ...firstConfiguration,
        grid_long_name: field(`grid-${index}-${'LONG_'.repeat(100)}`, 'run-1'),
      },
    })),
  };
  root.render(
    <MemoryRouter>
      <div className="min-w-0 p-6">
        <CaseConfigurationDetails record={many} identity={identity} />
      </div>
    </MemoryRouter>,
  );
  await waitFor(() => document.querySelectorAll('[data-case-configuration] thead th').length === 9);
  const manyDetails = document.querySelector<HTMLDetailsElement>('[data-case-configuration]')!;
  check(!manyDetails.open, 'Many-hash comparison also starts collapsed');
  manyDetails.querySelector('summary')!.click();
  const manyTable = document.querySelector('[data-case-configuration] table')!;
  const scrollContainer = manyTable.parentElement!;
  check(
    scrollContainer.scrollWidth > scrollContainer.clientWidth,
    'Many hashes scroll within comparison',
  );
  scrollContainer.scrollLeft = scrollContainer.scrollWidth;
  check(scrollContainer.scrollLeft > 0, 'Comparison allows horizontal scrolling');
  check(
    manyTable.querySelector('tbody th')!.getBoundingClientRect().left >= 0,
    'Field labels stay visible while scrolling',
  );
  check(
    document.documentElement.scrollWidth <= window.innerWidth,
    'Many hashes do not cause page overflow',
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
  const disclosure = table.closest('details')!;
  check(disclosure && !disclosure.open, 'Populated artifacts start collapsed');
  check(
    disclosure.querySelector('summary')?.textContent?.includes('30 records · 30 unique values'),
    'Collapsed artifacts retain counts',
  );
  check(!table.checkVisibility(), 'Collapsed artifacts hide table and controls');
  disclosure.querySelector('summary')!.click();
  check(disclosure.open && table.checkVisibility(), 'Artifacts expand on demand');
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
  disclosure.querySelector('summary')!.click();
  check(
    !disclosure.open && !search.checkVisibility(),
    'Collapsing artifacts hides search controls',
  );
  disclosure.querySelector('summary')!.click();
  check(
    search.value === 'Artifact 00' && table.tBodies[0].rows.length === 1,
    'Reopening artifacts preserves filters',
  );

  root.render(
    <CaseArtifactsTable
      key="empty-artifacts"
      artifacts={[]}
      totalArtifactCount={0}
      onFilterExecutionIds={() => {}}
    />,
  );
  await waitFor(() => document.body.textContent?.includes('No execution artifacts available.'));
  const emptyDisclosure = document.getElementById('artifacts-heading')!.closest('details')!;
  check(!emptyDisclosure.open, 'Empty artifacts start collapsed');
  check(
    emptyDisclosure.querySelector('summary')?.textContent?.includes('0 records · 0 unique values'),
    'Empty artifacts retain counts',
  );
  emptyDisclosure.querySelector('summary')!.click();
  check(emptyDisclosure.open, 'Empty artifacts can expand to show explanation');
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
