import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createRoot } from 'react-dom/client';
import { Link, MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router-dom';

import { api } from '../../src/api/api';
import { ComparePage } from '../../src/features/diagnostics/ComparePage';
import { comparePath, parseCompareState } from '../../src/features/diagnostics/compareState';
import { ComparisonBar } from '../../src/features/diagnostics/components/ComparisonBar';
import {
  DiagnosticsResourceLink,
  DiagnosticsRunsCard,
} from '../../src/features/diagnostics/components/DiagnosticsRunsCard';
import '../../src/index.css';

const base = 'https://web.lcrc.anl.gov/public/e3sm/diagnostic_output';
const url = (id: string, period = '0001-0050') =>
  `${base}/${id}/e3sm_diags/a/model_vs_obs_${period}/viewer/`;
const run = (id: string, start = 1, end = 50) => ({
  url: url(id, `${String(start).padStart(4, '0')}-${String(end).padStart(4, '0')}`),
  tool: 'e3sm_diags',
  comparison: 'model_vs_obs',
  startYear: start,
  endYear: end,
  tsStartYear: null,
  tsEndYear: null,
  subsection: 'atm_monthly',
});
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
// Keep headless checks deterministic; CSS animation completion uses wall-clock frames.
const style = document.createElement('style');
style.textContent =
  '*, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }';
document.head.append(style);
let latest = '';
let compares = 0;
api.defaults.adapter = async (config) => {
  const endpoint = config.url ?? '';
  let data: unknown;
  if (endpoint === '/cases') {
    const search = String(config.params.get('search') ?? '');
    const records = ['alpha', 'beta', 'raw-only'].filter((id) => id.includes(search));
    data = {
      items: records.map((id) => ({
        id,
        name: `case.${id}`,
        latestExecution: { executionId: 'execution-1' },
      })),
      page: 1,
      pageSize: 6,
      total: records.length,
    };
  } else if (endpoint.includes('/diagnostics/runs')) {
    const id = endpoint.split('/')[2];
    data = {
      caseId: id,
      caseName: `case.${id}`,
      sources: [
        {
          rootUrl: `${base}/${id}/`,
          label: null,
          runs: id === 'raw-only' ? [] : [run(id), run(id, 51, 100)],
          partial: false,
          error: null,
        },
      ],
    };
  } else if (endpoint === '/diagnostics/compare') {
    compares++;
    const body = JSON.parse(config.data);
    const sets = ['lat_lon', 'polar'].map((name) => ({
      name,
      title: name === 'lat_lon' ? 'Latitude / longitude' : 'Polar',
      plotCount: 1,
      missing: 0,
    }));
    data = {
      runs: body.runs.map((item: { url: string; label: string }) => ({
        ...item,
        tool: 'e3sm_diags',
        imageBaseUrl: '/missing-images/',
        error: null,
        partial: false,
      })),
      sets,
      set: {
        ...(sets.find((set) => set.name === body.set) ?? sets[0]),
        imageWidth: null,
        panels: {},
        groups: [
          {
            id: 'temperature',
            title: 'Temperature',
            reference: 'Observations',
            plots: [
              {
                key: 'temperature/ANN',
                season: 'ANN',
                region: 'global',
                singlePanel: true,
                paths: body.runs.map(() => 'plot.png'),
                references: body.runs.map(() => 'Observations'),
              },
            ],
          },
        ],
      },
    };
  } else throw new Error(`Unexpected request ${endpoint}`);
  return { config, data, status: 200, statusText: 'OK', headers: {} };
};

const Case = () => {
  const { id = 'alpha' } = useParams();
  return (
    <>
      <h1>Case {id}</h1>
      <a href={`${base}/${id}/`} data-original-resource>
        Original diagnostics
      </a>
      <DiagnosticsResourceLink caseId={id} url={`${base}/${id}/`} />
      <DiagnosticsResourceLink caseId={id} url={`${base}/${id}/raw/`} />
      <DiagnosticsRunsCard
        key={id}
        caseId={id}
        caseName={`case.${id}`}
        directories={[{ url: `${base}/${id}/`, label: null }]}
      />
    </>
  );
};
const Probe = () => {
  const location = useLocation();
  latest = `${location.pathname}${location.search}${location.hash}`;
  return null;
};
const root = createRoot(document.getElementById('root')!);
let mount = 0;
const render = (path: string) =>
  root.render(
    <QueryClientProvider client={client}>
      <MemoryRouter key={++mount} initialEntries={[path]}>
        <nav>
          <Link to="/case/alpha">Alpha case</Link>
          <Link to="/case/beta">Beta case</Link>
          <Link to="/diagnostics">Diagnostics workspace</Link>
        </nav>
        <Probe />
        <Routes>
          <Route path="/case/:id" element={<Case />} />
          <Route path="/diagnostics" element={<ComparePage />} />
          <Route path="/diagnostics/compare" element={<ComparePage />} />
        </Routes>
        <ComparisonBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );

const check = (condition: unknown, message: string) => {
  if (!condition) throw new Error(message);
};
const waitFor = async (predicate: () => unknown, label: string) => {
  for (let i = 0; i < 400; i++) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error(`Timed out: ${label}`);
};
const button = (text: string) =>
  [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (item) => item.textContent?.trim() === text,
  );
const link = (text: string) =>
  [...document.querySelectorAll<HTMLAnchorElement>('a')].find(
    (item) => item.textContent?.trim() === text,
  );
const click = (element: HTMLElement | undefined | null, label: string) => {
  check(element, `Missing ${label}`);
  element!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }));
  element!.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, button: 0 }));
  element!.click();
};
const input = (element: HTMLInputElement, value: string) => {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(element, value);
  element.dispatchEvent(new Event('input', { bubbles: true }));
};

async function testWorkspace() {
  localStorage.clear();
  render('/case/alpha');
  await waitFor(
    () =>
      document.querySelector('a[href="#diagnostics-alpha-source-0-e3sm_diags:model_vs_obs"]') ||
      document.querySelector('a[href$="#diagnostics-alpha-source-0-e3sm_diags:model_vs_obs"]'),
    'resource shortcut',
  );
  check(document.querySelectorAll('a').length > 0, 'Original resource retained');
  check(
    document.querySelectorAll('a').length &&
      document.querySelector('[data-original-resource]')?.getAttribute('href') === `${base}/alpha/`,
    'Original resource destination unchanged',
  );
  check(
    [...document.querySelectorAll('a')].filter((item) =>
      item.textContent?.startsWith('View in Diagnostics'),
    ).length === 1,
    'Unmatched resource has no shortcut',
  );
  click(
    [...document.querySelectorAll<HTMLAnchorElement>('a')].find((item) =>
      item.textContent?.startsWith('View in Diagnostics'),
    ),
    'resource shortcut',
  );
  await waitFor(
    () => document.activeElement?.id === 'diagnostics-alpha-source-0-e3sm_diags:model_vs_obs',
    'expanded group focus',
  );
  check(
    [...document.querySelectorAll('a')].some((item) =>
      item.textContent?.includes('Browse diagnostics directory'),
    ),
    'Compact directory link',
  );
  click(document.querySelector<HTMLButtonElement>('button[aria-label^="Add E3SM"]'), 'first run');
  await waitFor(() => button('Expand'), 'collapsed tray');
  check(!document.getElementById('comparison-tray-selections'), 'Tray starts collapsed');
  click(link('Beta case'), 'second case');
  await waitFor(() => document.querySelector('h1')?.textContent === 'Case beta', 'second case');
  click(
    [...document.querySelectorAll<HTMLButtonElement>('button')].find((item) =>
      item.textContent?.includes('Diagnostics ('),
    ),
    'expand beta diagnostics',
  );
  await waitFor(() => document.querySelector('button[aria-label^="Add E3SM"]'), 'beta runs');
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label^="Add E3SM"]'),
    'beta selection',
  );
  await waitFor(() => document.body.textContent?.includes('2 selected'), 'persistent count');
  click(button('Expand'), 'expand tray');
  await waitFor(() => document.getElementById('comparison-tray-selections'), 'expanded tray');
  check(
    document.getElementById('comparison-tray-selections')?.textContent?.includes('case.alpha'),
    'Cross-case selection retained',
  );
  click(link('Compare'), 'compare directly');
  await waitFor(() => document.querySelectorAll('figure').length === 2, 'populated comparison');
  check(
    !document.querySelector('[aria-label="Diagnostics comparison"]'),
    'No duplicate tray in workspace',
  );
  const original = latest;
  click(button('Edit runs'), 'run editor');
  await waitFor(() => document.querySelector('[role="dialog"]'), 'editor dialog');
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label="Remove run 1"]'),
    'draft remove',
  );
  click(button('Cancel'), 'cancel edits');
  await waitFor(() => !document.querySelector('[role="dialog"]'), 'editor close');
  check(latest === original, 'Cancel preserves comparison URL');
  click(button('Edit runs'), 'reopen editor');
  await waitFor(() => document.querySelector('button[aria-label="Remove run 1"]'), 'draft reset');
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label="Remove run 1"]'),
    'remove active run',
  );
  await waitFor(
    () => document.querySelector('[role="dialog"]')?.textContent?.includes('Selected runs (1/'),
    'draft removal',
  );
  click(button('Apply changes'), 'apply edit');
  await waitFor(
    () => parseCompareState(new URLSearchParams(latest.split('?')[1])).runs.length === 1,
    'updated URL',
  );
  check(
    JSON.parse(localStorage.getItem('simboard.diagnostics-comparison')!).length === 1,
    'Explicit removal updates known basket',
  );
  const shared = latest;
  localStorage.clear();
  render(shared);
  await waitFor(() => document.querySelectorAll('figure').length === 1, 'reload without basket');
  check(latest.includes(encodeURIComponent(url('beta'))), 'Full underlying run URL retained');
  render('/diagnostics');
  await waitFor(
    () =>
      document.querySelector('[role="tab"][data-state="active"]')?.textContent ===
      'Browse SimBoard',
    'default browser',
  );
  await waitFor(
    () => document.body.textContent?.includes('2 supported cases found'),
    'supported-only results',
  );
  check(!button('case.raw-only · 0 runs'), 'Raw resources are not supported cases');
  click(button('case.alpha · 2 runs'), 'browse indexed case');
  await waitFor(() => document.querySelector('button[aria-label^="Add E3SM"]'), 'browser runs');
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label^="Add E3SM"]'),
    'first period',
  );
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'first period added',
  );
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label^="Add E3SM"]'),
    'second period',
  );
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (2/'),
    'same-case periods',
  );
  click(button('Compare'), 'same case comparison');
  await waitFor(() => document.querySelectorAll('figure').length === 2, 'same case plots');
  render('/diagnostics');
  await waitFor(() => button('Add by URL'), 'manual entry tab');
  click(button('Add by URL'), 'manual tab');
  await waitFor(() => document.getElementById('manual-run-url'), 'manual form');
  input(document.getElementById('manual-run-url') as HTMLInputElement, `${base}/raw/`);
  await waitFor(
    () => (document.getElementById('manual-run-url') as HTMLInputElement).value === `${base}/raw/`,
    'directory input',
  );
  click(button('Add run'), 'reject directory');
  await waitFor(() => document.querySelector('[role="alert"]'), 'invalid resource feedback');
  input(document.getElementById('manual-run-url') as HTMLInputElement, url('external'));
  await new Promise((resolve) => setTimeout(resolve, 10));
  input(document.getElementById('manual-run-label') as HTMLInputElement, 'External run');
  await new Promise((resolve) => setTimeout(resolve, 10));
  click(button('Add run'), 'manual run');
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'manual run selected',
  );
  click(button('Compare'), 'manual comparison');
  await waitFor(() => document.querySelector('figure'), 'manual plots');
  check(
    document.querySelector('figure')?.textContent?.includes('External run'),
    'Manual label retained',
  );
  render(comparePath([{ url: url('alpha'), label: '!Case override' }]));
  await waitFor(
    () => document.querySelector('figure')?.textContent?.includes('Case override'),
    'MPAS label presentation',
  );
  check(compares > 0, 'Backend comparison interface used');
  check(
    document.documentElement.scrollWidth <= window.innerWidth + 1,
    'No horizontal page overflow',
  );
}

testWorkspace()
  .then(() => {
    const output = document.createElement('output');
    output.id = 'test-result';
    output.textContent = 'passed';
    window.frameElement?.insertAdjacentElement('afterend', output);
  })
  .catch((error) => {
    const output = document.createElement('output');
    output.id = 'test-result';
    output.textContent = error instanceof Error ? error.message : String(error);
    window.frameElement?.insertAdjacentElement('afterend', output);
  });
