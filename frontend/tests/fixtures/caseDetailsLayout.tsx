import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
  executions: [],
};
client.setQueryData(['cases', 'readable-detail', 'chrysalis', 'test.user', 'test.case'], record);
client.setQueryDefaults(['executions', 'case'], {
  initialData: { pages: [{ items: [], total: 0, page: 1, pageSize: 100 }], pageParams: [1] },
});
const root = createRoot(document.getElementById('root')!);

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
              <Route
                path="/cases/:machine/:hpcUsername/:caseName"
                element={
                  <CaseDetailsPage
                    selectedCaseExecutionIdsByCase={{}}
                    setSelectedCaseExecutionIdsForCase={() => {}}
                  />
                }
              />
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
      notes?.nextElementSibling!.getBoundingClientRect().height! < 50,
      'Empty notes stay compact',
    );
    const resources = document.querySelector('a[href="https://example.test/docs"]');
    check(
      resources && resources.getBoundingClientRect().width < 400,
      'Single resource stays compact',
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

  const history = [...document.querySelectorAll('button')].find((element) =>
    element.textContent?.includes('Change History'),
  )!;
  history.click();
  await waitFor(() => requests.length === 1);
  check(requests[0].includes('/history'), 'Opening history fetches history only');
}

run()
  .then(() => {
    const output = document.createElement('output');
    output.id = 'test-result';
    output.textContent = 'passed';
    document.body.append(output);
  })
  .catch((error) => {
    const output = document.createElement('output');
    output.id = 'test-result';
    output.textContent = error.stack;
    document.body.append(output);
  });
