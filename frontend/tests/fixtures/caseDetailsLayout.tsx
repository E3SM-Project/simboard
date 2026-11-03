import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { api } from '../../src/api/api';
import { AuthContext } from '../../src/auth/context';
import { CaseDetailsPage } from '../../src/features/catalog/CaseDetailsPage';
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
const executions = [1, 2].map((number) => ({
  id: `execution-${number}`,
  executionId: `run-${number}`,
  caseHash: 'test-hash',
  status: 'completed',
  simulationStartDate: `000${number}-01-01`,
  simulationEndDate: `000${number + 1}-01-01`,
  initializationType: number === 1 ? 'hybrid' : 'startup',
  runStartDate: `2026-10-0${number}T12:00:00Z`,
  runEndDate: `2026-10-0${number}T13:00:00Z`,
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
    pages: [{ items: executions, total: 2, page: 1, pageSize: 100 }],
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
      'Select|Initialization|Run dates (latest first)|Execution ID|Simulation dates|Case Hash',
    'Flat execution column order',
  );
  const row = table.tBodies[0].rows[0];
  check(row.cells[1].textContent === 'startup', 'Initialization value stays unchanged');
  check(row.cells[2].textContent === '2026-10-02 → 2026-10-02', 'Run dates match column');
  check(row.cells[3].textContent === 'run-2', 'Latest execution stays first');
  check(row.cells[4].textContent === '0002-01-01 → 0003-01-01', 'Simulation dates match column');
  check(row.cells[5].textContent === 'test-hash', 'Hash matches column');
  check(
    row.cells[3].querySelector('a')?.getAttribute('href')?.endsWith('/run-2'),
    'Execution link retained',
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
      'Select|Initialization|Run dates|Execution ID|Simulation dates',
    'Grouped execution column order',
  );
  check(
    groupTable.querySelector('[role="checkbox"]')?.getAttribute('aria-checked') === 'true',
    'Grouping retains selection',
  );

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
