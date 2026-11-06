import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createRoot } from 'react-dom/client';
import { Link, MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router-dom';

import { api } from '../../src/api/api';
import { ComparePage } from '../../src/features/diagnostics/ComparePage';
import {
  comparePath,
  compareSearch,
  parseCompareState,
} from '../../src/features/diagnostics/compareState';
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
let unavailableChecks = 0;
let copiedLink = '';
Object.defineProperty(navigator, 'clipboard', {
  configurable: true,
  value: {
    writeText: async (text: string) => {
      copiedLink = text;
    },
  },
});
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
    if (search === 'paged') {
      const page = Number(config.params.get('page') ?? 1);
      data = {
        items: [
          { id: page === 1 ? 'raw-only' : 'alpha', name: page === 1 ? 'raw-only' : 'case.alpha' },
        ],
        page,
        pageSize: 1,
        total: 2,
      };
    }
    if (search === 'unavailable')
      data = {
        items: [{ id: 'unavailable', name: 'case.unavailable' }],
        page: 1,
        pageSize: 6,
        total: 1,
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
    if (id === 'unavailable' && unavailableChecks++ === 0)
      data = {
        caseId: id,
        caseName: `case.${id}`,
        sources: [
          { rootUrl: `${base}/${id}/`, runs: [], partial: false, error: 'archive_unavailable' },
        ],
      };
  } else if (endpoint === '/diagnostics/compare') {
    compares++;
    const body = JSON.parse(config.data);
    const composite = body.runs.some((item: { url: string }) => item.url.includes('/composite-'));
    const incompatible = body.runs.some((item: { url: string }) =>
      item.url.includes('/incompatible/'),
    );
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
        imageBaseUrl: composite
          ? `/__diagnostics/image/${encodeURIComponent(item.url)}/`
          : '/missing-images/',
        error: item.url.includes('/unreadable/') ? 'archive_unavailable' : null,
        partial: false,
      })),
      sets: incompatible ? [] : sets,
      set: {
        ...(sets.find((set) => set.name === body.set) ?? sets[0]),
        imageWidth: composite ? 1000 : null,
        panels: composite
          ? {
              test: { width: 1000, height: 200, top: 0, left: 0 },
              ref: { width: 1000, height: 200, top: 200, left: 0 },
              diff: { width: 1000, height: 200, top: 400, left: 0 },
            }
          : {},
        groups: ['temperature', 'precipitation'].map((variable) => ({
          id: variable,
          title: variable === 'temperature' ? 'Temperature' : 'Precipitation',
          reference: 'Observations',
          plots: ['ANN', 'DJF'].map((season) => ({
            key: `${variable}/${season}`,
            season,
            region: 'global',
            singlePanel: !composite,
            paths: body.runs.map((run: { url: string }) =>
              run.url.includes('/unreadable/') ? null : 'plot.png',
            ),
            references: body.runs.map((item: { url: string }, index: number) =>
              composite && index && !item.url.includes('/composite-same-')
                ? 'Reference model'
                : 'Observations',
            ),
          })),
        })),
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
  check(document.activeElement === button('Edit runs'), 'Cancel restores editor trigger focus');
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
  await waitFor(() => button('Retry image'), 'unavailable image recovery');
  check(link('Open original image'), 'Full image remains accessible after failure');
  click(button('Retry image'), 'retry failed image');
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
  render('/diagnostics');
  await waitFor(() => button('Add by URL'), 'example setup');
  click(button('Add by URL'), 'example tab');
  await waitFor(() => document.querySelector('summary'), 'examples disclosure');
  click(document.querySelector('summary'), 'open examples');
  check(
    document.querySelector('details')?.querySelectorAll('li').length === 4,
    'All IICE examples retained',
  );
  click(document.querySelector('details li button') as HTMLButtonElement, 'open IICE example');
  await waitFor(
    () => document.querySelectorAll('figure').length === 4,
    'example opens directly into plots',
  );
}

async function testViewer() {
  render('/diagnostics');
  await waitFor(() => document.getElementById('diagnostic-case-search'), 'search browser');
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'paged');
  await waitFor(
    () => document.body.textContent?.includes('No supported cases in checked results'),
    'bounded discovery empty page',
  );
  click(button('Load more cases'), 'load more supported cases');
  await waitFor(() => button('case.alpha · 2 runs'), 'supported case on next page');
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'unavailable');
  await waitFor(() => button('Retry discovery'), 'archive failure feedback');
  click(button('Retry discovery'), 'retry failed archive');
  await waitFor(() => button('case.unavailable · 2 runs'), 'retry bypasses failed discovery cache');
  render(comparePath([{ url: url('incompatible'), label: 'Incompatible' }]));
  await waitFor(
    () => document.body.textContent?.includes('These runs have no plots in common'),
    'incompatible selection feedback',
  );
  check(button('Edit runs'), 'Incompatible selections remain editable');
  render(
    comparePath([
      { url: url('alpha'), label: 'Available' },
      { url: url('unreadable'), label: 'Unavailable' },
    ]),
  );
  await waitFor(
    () => document.body.textContent?.includes('Plot unavailable for this run'),
    'missing run placeholder',
  );
  check(document.querySelectorAll('figure').length === 2, 'Failed run retains aligned cell');
  check(
    document.querySelectorAll('figure')[1].textContent?.includes('Unavailable'),
    'Missing run keeps its label',
  );
  check(button('Retry diagnostics'), 'Failed catalog can be retried');

  const sharedState = {
    runs: [
      { url: url('composite-one'), label: 'First simulation' },
      { url: url('composite-two'), label: 'Second simulation' },
    ],
    set: 'polar',
    plot: 'temperature/DJF',
    view: 'diff' as const,
  };
  render(`/diagnostics/compare?${compareSearch(sharedState)}`);
  await waitFor(
    () => document.querySelector('[role="radiogroup"][aria-label="Panel"]'),
    'composite panel controls',
  );
  await waitFor(
    () => document.querySelector<HTMLImageElement>('figure img')?.complete,
    'published image',
  );
  check(document.querySelectorAll('figure').length === 2, 'Difference has one cell per simulation');
  check(
    document.body.textContent?.includes('not the difference between selected simulations'),
    'Scientific difference explained',
  );
  check(
    document.querySelector<HTMLImageElement>('figure img')?.style.top === '-200%',
    'Difference crop uses published window',
  );
  check(
    document.querySelector('[aria-label="Season"] [aria-checked="true"]')?.textContent === 'DJF',
    'Season restored from URL',
  );
  check(
    document.querySelector('[aria-labelledby="plot-set-label"]')?.textContent === 'Polar',
    'Category restored from URL',
  );
  click(button('Copy link'), 'copy comparison link');
  await waitFor(() => copiedLink === window.location.href, 'copy uses full address');
  const original = latest;
  click(button('Edit runs'), 'edit without resetting plot settings');
  await waitFor(() => document.querySelector('[role="dialog"]'), 'editor open');
  document
    .querySelector<HTMLInputElement>('input[aria-label="Run 1 label"]')!
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'j', bubbles: true }));
  check(latest === original, 'Plot shortcuts do not intercept editor input');
  click(button('Apply changes'), 'apply unchanged selection');
  await waitFor(() => !document.querySelector('[role="dialog"]'), 'editor applied');
  check(
    parseCompareState(new URLSearchParams(latest.split('?')[1])).view === 'diff',
    'Apply preserves panel mode',
  );
  check(
    parseCompareState(new URLSearchParams(latest.split('?')[1])).plot === 'temperature/DJF',
    'Apply preserves selected plot',
  );

  const season = document.querySelector<HTMLButtonElement>(
    '[aria-label="Season"] [aria-checked="true"]',
  )!;
  season.focus();
  season.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  await waitFor(
    () =>
      document.querySelector('[aria-label="Season"] [aria-checked="true"]')?.textContent === 'ANN',
    'radio arrow navigation',
  );
  check(document.activeElement?.textContent === 'ANN', 'Radio arrow moves focus');
  click(
    [...document.querySelectorAll<HTMLButtonElement>('[aria-label="Panel"] button')].find(
      (item) => item.textContent === 'Run',
    ),
    'run panel',
  );
  await waitFor(
    () => document.querySelectorAll('figure').length === 4,
    'distinct references retained',
  );
  check(
    [...document.querySelectorAll('figcaption')].some((item) =>
      item.textContent?.includes('Reference · Reference model'),
    ),
    'Model reference distinct from observations',
  );
  const category = document.querySelector<HTMLButtonElement>('[aria-labelledby="plot-set-label"]')!;
  category.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
  await waitFor(() => document.querySelector('[role="option"]'), 'category keyboard open');
  const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find(
    (item) => item.textContent === 'Latitude / longitude',
  )!;
  option.focus();
  option.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  await waitFor(() => latest.includes('set=lat_lon'), 'category keyboard selection');
  const filter = document.querySelector<HTMLInputElement>('input[aria-label="Filter variables"]')!;
  input(filter, 'nothing-matches');
  await waitFor(
    () => document.body.textContent?.includes('No variables match this filter'),
    'empty filter feedback',
  );
  input(filter, '');
  await new Promise((resolve) => setTimeout(resolve, 10));
  const variableButton = document.querySelector<HTMLButtonElement>('aside button')!;
  click(variableButton, 'select variable before keyboard stepping');
  variableButton.focus();
  variableButton.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
  await waitFor(() => latest.includes('precipitation'), 'variable keyboard stepping');
  const restored = latest;
  localStorage.setItem(
    'simboard.diagnostics-comparison',
    JSON.stringify([
      {
        url: url('unrelated'),
        caseId: 'unrelated',
        caseName: 'Unrelated staged case',
        tool: 'e3sm_diags',
        comparison: 'model_vs_obs',
      },
    ]),
  );
  render(restored);
  await waitFor(
    () => document.querySelector('h2')?.textContent?.includes('Precipitation'),
    'reload restores active plot independently of basket',
  );
  check(
    !document.body.textContent?.includes('Unrelated staged case'),
    'Shared link does not import conflicting basket',
  );
  check(
    document.documentElement.scrollWidth <= window.innerWidth + 1,
    'Viewer has no mobile overflow',
  );
  render(
    comparePath([
      { url: url('composite-same-one'), label: 'First period' },
      { url: url('composite-same-two'), label: 'Second period' },
    ]),
  );
  await waitFor(
    () =>
      document.querySelectorAll('figure').length === 4 &&
      document.querySelector('figure')?.textContent?.includes('First period'),
    'same-name references retain distinct published images',
  );
  check(
    [...document.querySelectorAll('figcaption')].filter((caption) =>
      caption.textContent?.startsWith('Reference · Observations'),
    ).length === 2,
    'No reference equivalence inferred from names',
  );
  const overrides = [
    { url: `${base}/shared/mpas_analysis/ts_1-10/`, label: '!Case A' },
    { url: `${base}/shared/mpas_analysis/ts_1-10/`, label: '!Case B' },
  ];
  render(comparePath(overrides));
  await waitFor(
    () =>
      document.querySelectorAll('figure').length === 2 &&
      document.querySelector('figure')?.textContent?.includes('Case A'),
    'same directory with IICE overrides',
  );
  click(button('Edit runs'), 'edit IICE overrides');
  await waitFor(() => document.querySelector('[role="dialog"]'), 'override editor');
  click(button('Apply changes'), 'apply distinct same-directory overrides');
  await waitFor(() => !document.querySelector('[role="dialog"]'), 'override edits accepted');
  check(
    parseCompareState(new URLSearchParams(latest.split('?')[1])).runs[1].label === '!Case B',
    'IICE override remains in shared URL',
  );

  const staged = [
    {
      url: url('staged-one'),
      label: 'unused',
      caseId: 'one',
      caseName: 'Staged one',
      period: '0001-0050',
      tool: 'e3sm_diags',
      comparison: 'model_vs_obs',
    },
    {
      url: `${base}/mpas/mpas_analysis/ts_1-10/`,
      caseId: 'mpas',
      caseName: 'Staged MPAS',
      period: '0001-0010',
      tool: 'mpas_analysis',
      comparison: null,
    },
  ];
  localStorage.setItem('simboard.diagnostics-comparison', JSON.stringify(staged));
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(
    () => document.querySelector('[aria-label="Tray group to import"]'),
    'explicit tray group',
  );
  click(button('Import tray selections'), 'import one kind');
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'grouped import selection',
  );
  check(
    !document.querySelector('[aria-label="Selected runs"]')?.textContent?.includes('Staged MPAS'),
    'Import does not silently mix diagnostic kinds',
  );
}

testWorkspace()
  .then(testViewer)
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
