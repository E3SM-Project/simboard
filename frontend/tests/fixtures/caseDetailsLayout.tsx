import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

import { api } from '../../src/api/api';
import { AuthContext } from '../../src/auth/context';
import { CaseDetailsPage } from '../../src/features/catalog/CaseDetailsPage';
import { CasesPage } from '../../src/features/catalog/CasesPage';
import '../../src/index.css';

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

    const developer = document.querySelector('details');
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
    for (const text of ['Executions', 'Case hash groups', 'Machines', 'HPC users']) {
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
  await checkCasesFilters();
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
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: {
      writeText: async (value: string) => {
        copied = value;
      },
    },
  });
  document.querySelector<HTMLButtonElement>('[aria-label="Copy search link"]')!.click();
  await waitFor(() => copied.includes('caseGroup=v3.HR'));
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
