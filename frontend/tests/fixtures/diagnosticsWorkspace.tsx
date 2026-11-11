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
  subsection: 'atm_monthly_180x360_aave',
});
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
// Keep headless checks deterministic; CSS animation completion uses wall-clock frames.
const style = document.createElement('style');
style.textContent =
  '*, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }';
document.head.append(style);
let latest = '';
let compares = 0;
let validations = 0;
let comparisonDelay = 0;
let comparisonFailures = 0;
const discoveryLogs: unknown[][] = [];
const originalDebug = console.debug;
console.debug = (...args) => {
  discoveryLogs.push(args);
  originalDebug(...args);
};
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
    if (search === 'search-failed') throw new Error('Case search unavailable');
    const records = ['alpha', 'beta', 'raw-only'].filter((id) => id.includes(search));
    data = {
      items: records.map((id) => ({
        id,
        name: `case.${id}`,
        machineName: 'chrysalis',
        hpcUsername: 'scientist',
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
    if (['partial', 'rejected', 'request-failed', 'mixed', 'ranges'].includes(search))
      data = { items: [{ id: search, name: `case.${search}` }], page: 1, pageSize: 6, total: 1 };
    if (search === 'analysis')
      data = {
        items: ['metadata', 'beta'].map((id) => ({
          id,
          name: `case.${id}`,
          machineName: 'chrysalis',
          hpcUsername: 'scientist',
        })),
        page: 1,
        pageSize: 6,
        total: 2,
      };
    if (search === 'dense') {
      const page = Number(config.params.get('page') ?? 1);
      data = {
        items: Array.from({ length: 6 }, (_, index) => ({
          id: `dense-${(page - 1) * 6 + index}`,
          name: `case.dense-${(page - 1) * 6 + index}.${'long_identifier_'.repeat(4)}`,
        })),
        page,
        pageSize: 6,
        total: 18,
      };
    }
  } else if (endpoint.includes('/diagnostics/runs')) {
    const id = endpoint.split('/')[2];
    if (id === 'request-failed') throw new Error('Case diagnostics unavailable');
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
    if (id === 'partial' || id === 'rejected')
      data = {
        caseId: id,
        caseName: `case.${id}`,
        sources: [
          {
            rootUrl: `${base}/${id}/`,
            runs: id === 'partial' ? [run(id)] : [],
            partial: id === 'partial',
            error: id === 'rejected' ? 'url_not_allowed' : null,
          },
        ],
      };
    if (id === 'mixed')
      data = {
        caseId: id,
        caseName: `case.${id}`,
        sources: [
          {
            rootUrl: `${base}/${id}/`,
            label: 'Public output',
            runs: [run(id)],
            partial: false,
            error: null,
          },
          {
            rootUrl: 'https://unsupported.test/diagnostics/',
            label: 'Unsupported output',
            runs: [],
            partial: false,
            error: 'url_not_allowed',
          },
        ],
      };
    if (id === 'ranges') {
      const combined = {
        ...run(id, 51, 100),
        tool: 'mpas_analysis',
        comparison: null,
        subsection: null,
        tsStartYear: 1,
        tsEndYear: 100,
        url: `${base}/${id}/mpas_analysis/ts_0001-0100_climo_0051-0100/`,
      };
      data = {
        caseId: id,
        caseName: `case.${id}`,
        sources: [
          {
            rootUrl: `${base}/${id}/`,
            runs: [
              combined,
              run(id, 51, 100),
              {
                ...combined,
                startYear: null,
                endYear: null,
                tsStartYear: 101,
                tsEndYear: 200,
                url: `${base}/${id}/mpas_analysis/ts_0101-0200/`,
              },
              {
                ...combined,
                startYear: null,
                endYear: null,
                tsStartYear: null,
                tsEndYear: null,
                url: `${base}/${id}/mpas_analysis/unknown_9000-9999/`,
              },
            ],
            partial: false,
            error: null,
          },
          { rootUrl: `${base}/${id}/duplicate/`, runs: [combined], partial: false, error: null },
        ],
      };
    }
    if (id === 'metadata') {
      const model = {
        ...run(id),
        url: `${base}/${id}/e3sm_diags/atm_monthly_180x360_aave_mvm_PI100/model_vs_model_0001-0050/viewer/`,
        comparison: 'model_vs_model',
        subsection: 'atm_monthly_180x360_aave_mvm_PI100',
      };
      data = {
        caseId: id,
        caseName: `case.${id}`,
        sources: [
          {
            rootUrl: `${base}/${id}/`,
            label: 'zppy diagnostics',
            runs: [run(id), model],
          },
          {
            rootUrl: `${base}/${id}/second/`,
            label: 'Other diagnostics',
            runs: [
              run(id),
              {
                ...model,
                url: `${base}/${id}/second/e3sm_diags/lnd_monthly_mvm_lnd/model_vs_model_0001-0050/viewer/`,
                subsection: 'lnd_monthly_mvm_lnd',
              },
              {
                ...run(id),
                tool: 'mpas_analysis',
                comparison: null,
                subsection: null,
                url: `${base}/${id}/mpas_analysis/ts_0001-0500_climo_0001-0050/`,
                tsStartYear: 1,
                tsEndYear: 500,
              },
            ],
          },
        ],
      };
    }
    if (id.startsWith('dense-'))
      data = {
        caseId: id,
        caseName: `case.${id}`,
        sources: [
          {
            rootUrl: `${base}/${id}/`,
            runs: Array.from({ length: 30 }, (_, index) =>
              run(id, index * 50 + 1, (index + 1) * 50),
            ),
          },
        ],
      };
  } else if (endpoint === '/diagnostics/compare') {
    compares++;
    const body = JSON.parse(config.data);
    if (body.runs.length > 1) validations++;
    const family = body.runs[0]?.url.includes('/group-ocean') ? 'ocean' : 'atmosphere';
    const grouped = body.runs.every((item: { url: string }) => item.url.includes('/group-'));
    if (comparisonDelay) await new Promise((resolve) => setTimeout(resolve, comparisonDelay));
    if (comparisonFailures > 0) {
      comparisonFailures--;
      throw new Error('Compatibility service unavailable');
    }
    const composite = body.runs.some((item: { url: string }) => item.url.includes('/composite-'));
    const incompatible = body.runs.some((item: { url: string }) =>
      item.url.includes('/incompatible/'),
    );
    const sets = (
      body.runs.some((item: { url: string }) => item.url.includes('/group-missing'))
        ? ['lat_lon']
        : ['lat_lon', 'polar']
    ).map((name) => ({
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
            key: grouped
              ? `${body.set === 'polar' ? family : body.runs[0].url}/${variable}/${season}`
              : `${variable}/${season}`,
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
  } else if (endpoint.startsWith('/cases/')) {
    const id = endpoint.split('/')[2];
    data = { id, name: `case.${id}`, machineNames: ['chrysalis'], hpcUsernames: ['scientist'] };
  } else throw new Error(`Unexpected request ${endpoint}`);
  return { config, data, status: 200, statusText: 'OK', headers: {} };
};

const Case = () => {
  const { id: routeId = 'alpha' } = useParams();
  const id = routeId.replace(/^case\./, '');
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
          <Route path="/cases/:machine/:user/:id" element={<Case />} />
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
/** The primary Compare action, whose label carries the selected run count. */
const compareAction = () =>
  [...document.querySelectorAll<HTMLButtonElement>('button')].find((item) =>
    /^Compare \(\d+\)$/.test(item.textContent?.trim() ?? ''),
  );
const analysisTab = (text: string) =>
  [
    ...document.querySelectorAll<HTMLButtonElement>(
      '[aria-label="Filter diagnostics by analysis"] [role="tab"]',
    ),
  ].find((item) => item.textContent?.startsWith(`${text} (`));
const selectedSummary = () =>
  [...document.querySelectorAll<HTMLHeadingElement>('h2')].find((item) =>
    item.textContent?.startsWith('Selected runs ('),
  );
const toolButton = (text: string) =>
  [
    ...document.querySelectorAll<HTMLButtonElement>(
      '[aria-label="Filter diagnostics by tool"] button',
    ),
  ].find((item) => item.textContent?.startsWith(`${text} (`));
const expandSelections = async () => {
  await waitFor(
    () => document.querySelector('[aria-label="Selected runs"]'),
    'selected details visible',
  );
};
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
  render('/case/metadata');
  await waitFor(() => button('Diagnostics (4)4 supported runs'), 'metadata case loaded');
  check(
    button('Diagnostics (4)4 supported runs')?.getAttribute('aria-expanded') === 'true',
    'Supported diagnostics expand by default',
  );
  click(button('Diagnostics (4)4 supported runs'), 'collapse diagnostics');
  await waitFor(
    () => button('Diagnostics (4)4 supported runs')?.getAttribute('aria-expanded') === 'false',
    'Manual collapse remains available',
  );
  click(button('Diagnostics (4)4 supported runs'), 'reopen diagnostics');
  await waitFor(() => document.querySelectorAll('h4').length === 1, 'single shared period');
  check(document.querySelector('h4')?.textContent?.startsWith('0001–0050'), 'Period-first header');
  for (const identifier of [
    'atm_monthly_180x360_aave',
    'atm_monthly_180x360_aave_mvm_PI100',
    'lnd_monthly_mvm_lnd',
    'ts_0001-0500_climo_0001-0050',
  ])
    check(
      [...document.querySelectorAll('li span')].some((item) => item.textContent === identifier),
      `Exact identifier ${identifier}`,
    );
  const mpasRow = document.querySelector('a[aria-label^="Open MPAS"]')?.closest('li');
  check(mpasRow?.textContent?.includes('Climatology · Time Series'), 'MPAS analyses retained');
  check(
    mpasRow?.textContent?.includes('Climatology: 0001–0050 · Time Series: 0001–0500'),
    'Both MPAS periods explicitly labeled',
  );
  check(!mpasRow?.textContent?.includes('Model vs.'), 'No inferred MPAS comparison');
  check(
    document.querySelectorAll('a[aria-label^="Open "]').length === 4,
    'All unique runs accessible',
  );
  check(
    document.querySelectorAll('button[aria-expanded]').length === 1,
    'No nested run accordions',
  );
  check(
    document.documentElement.scrollWidth <= window.innerWidth + 1,
    'Precise identifiers do not cause horizontal overflow',
  );
  check(
    analysisTab('All')?.getAttribute('aria-selected') === 'true',
    'All analyses shown by default',
  );
  click(analysisTab('Climatology'), 'filter case diagnostics');
  await waitFor(
    () => analysisTab('Climatology')?.getAttribute('aria-selected') === 'true',
    'climatology filter selected',
  );
  analysisTab('Climatology')!.focus();
  analysisTab('Climatology')!.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }),
  );
  await waitFor(
    () => analysisTab('Time Series')?.getAttribute('aria-selected') === 'true',
    'analysis keyboard navigation',
  );
  check(document.activeElement === analysisTab('Time Series'), 'Analysis arrow key moves focus');
  await waitFor(
    () => document.querySelector('h4')?.textContent?.startsWith('0001–0050'),
    'time-series filter preserves climatology-first grouping',
  );
  check(
    document.querySelectorAll('a[aria-label^="Open "]').length === 1,
    'Time-series filter hides climatology-only runs',
  );
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label^="Add MPAS"]'),
    'select combined MPAS run',
  );
  await waitFor(() => document.querySelector('button[aria-label^="Remove MPAS"]'), 'MPAS added');
  click(analysisTab('Climatology'), 'return to climatology grouping');
  await waitFor(
    () => document.querySelector('h4')?.textContent?.startsWith('0001–0050'),
    'climatology period grouping',
  );
  check(
    document.querySelector('button[aria-label^="Remove MPAS"]')?.getAttribute('aria-pressed') ===
      'true',
    'Same run stays Added across analysis filters',
  );
  check(
    JSON.parse(localStorage.getItem('simboard.diagnostics-comparison')!).length === 1,
    'Filters do not duplicate tray selections',
  );
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label^="Remove MPAS"]'),
    'remove combined run',
  );
  await waitFor(
    () => !document.querySelector('[aria-label="Diagnostics comparison"]'),
    'tray cleared',
  );
  click(
    [...document.querySelectorAll<HTMLAnchorElement>('a')].find((item) =>
      item.textContent?.startsWith('View in Diagnostics'),
    ),
    'resource shortcut after filtering',
  );
  await waitFor(
    () => analysisTab('All')?.getAttribute('aria-selected') === 'true',
    'resource navigation restores all analyses',
  );
  check(
    document.querySelectorAll('a[aria-label^="Open "]').length === 4,
    'Resource shortcut does not leave runs hidden by a filter',
  );
  localStorage.setItem(
    'simboard.diagnostics-comparison',
    JSON.stringify(
      Array.from({ length: 12 }, (_, index) => ({
        url: url(`full-${index}`),
        caseId: `full-${index}`,
        caseName: `Full ${index}`,
        tool: 'e3sm_diags',
        comparison: 'model_vs_obs',
        period: '0001-0050',
      })),
    ),
  );
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/case/alpha');
  await waitFor(
    () =>
      document.querySelector('button[aria-label^="Add E3SM"]') &&
      compareAction()?.textContent?.trim() === 'Compare (12)',
    'runs with a full comparison group',
  );
  check(
    document.querySelector<HTMLButtonElement>('button[aria-label^="Add E3SM"]')?.disabled &&
      document
        .querySelector('button[aria-label^="Add E3SM"]')
        ?.parentElement?.closest('[tabindex="0"]')
        ?.getAttribute('aria-label')
        ?.startsWith('Compare up to 12 runs'),
    'Add is disabled with a reason when the group is full',
  );
  localStorage.removeItem('simboard.diagnostics-comparison');
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
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
    document.activeElement?.getAttribute('aria-label'),
    'Legacy group target has an accessible name',
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
  click(compareAction(), 'compare from tray');
  await waitFor(() => document.querySelectorAll('figure').length === 2, 'populated comparison');
  check(
    !document.querySelector('[aria-label="Diagnostics comparison"]'),
    'No duplicate tray in workspace',
  );
  const original = latest;
  click(button('Edit runs'), 'run editor');
  await waitFor(() => document.querySelector('[role="dialog"]'), 'editor dialog');
  check(
    document.querySelector('button[aria-label="Remove run 1"]'),
    'Selected-run details are open by default',
  );
  await expandSelections();
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label="Remove run 1"]'),
    'draft remove',
  );
  click(button('Cancel'), 'cancel edits');
  await waitFor(() => !document.querySelector('[role="dialog"]'), 'editor close');
  check(document.activeElement === button('Edit runs'), 'Cancel restores editor trigger focus');
  check(latest === original, 'Cancel preserves comparison URL');
  click(button('Edit runs'), 'reopen editor');
  await waitFor(() => document.querySelector('[role="dialog"]'), 'editor reopened');
  await expandSelections();
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
  await new Promise((resolve) => setTimeout(resolve, 50));
  await waitFor(() => document.querySelectorAll('figure').length === 1, 'reload without basket');
  check(latest.includes(encodeURIComponent(url('beta'))), 'Full underlying run URL retained');
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(
    () =>
      document.querySelector('[role="tab"][data-state="active"]')?.textContent ===
      'Browse SimBoard',
    'default browser',
  );
  await waitFor(() => button('case.beta · 2 runs'), 'supported-only results');
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
  check(
    document.querySelectorAll('#available-case-diagnostics li button[aria-pressed="true"]')
      .length === 2,
    'Added states reflect both selected periods',
  );
  const betaCase = button('case.beta · 2 runs')!;
  betaCase.focus();
  click(betaCase, 'switch active case');
  await waitFor(
    () =>
      document.querySelector('#available-case-diagnostics')?.getAttribute('aria-label') ===
      'Diagnostics for case.beta',
    'beta diagnostics selected',
  );
  check(document.activeElement === betaCase, 'Case switch keeps keyboard focus in case list');
  await new Promise((resolve) => setTimeout(resolve, 350));
  check(betaCase.getAttribute('aria-pressed') === 'true', 'Selected-case state');
  check(button('case.alpha · 2 runs'), 'Case list remains visible');
  await expandSelections();
  check(
    document.querySelector('[aria-label="Selected runs"]')?.textContent?.includes('case.alpha'),
    'Inactive-case selections remain visible',
  );
  click(
    document.querySelector<HTMLButtonElement>(
      '#available-case-diagnostics button[aria-label^="Add E3SM"]',
    ),
    'cross-case workspace selection',
  );
  await waitFor(() => document.body.textContent?.includes('Selected runs (3/'), 'cross-case count');
  click(button('case.alpha · 2 runs'), 'return to first case');
  await waitFor(
    () =>
      document.querySelectorAll('#available-case-diagnostics li button[aria-pressed="true"]')
        .length === 2,
    'Added states survive case changes',
  );
  click(compareAction(), 'same case comparison');
  await waitFor(
    () => document.querySelectorAll('figure').length === 3,
    'multi-case and multi-period plots',
  );
  render('/diagnostics');
  await waitFor(() => button('Add by URL'), 'manual entry tab');
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (3/'),
    'Workspace selections restore after navigation',
  );
  await expandSelections();
  for (let remaining = 3; remaining > 0; remaining--) {
    click(
      document.querySelector<HTMLButtonElement>('button[aria-label="Remove run 1"]'),
      'clear previous selection',
    );
    await waitFor(
      () => document.body.textContent?.includes(`Selected runs (${remaining - 1}/`),
      'selection removed immediately',
    );
  }
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
  click(compareAction(), 'manual comparison');
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
  await waitFor(
    () =>
      [...document.querySelectorAll('summary')].find((item) =>
        item.textContent?.includes('IICE example comparisons'),
      ),
    'examples disclosure',
  );
  const examples = [...document.querySelectorAll('summary')]
    .find((item) => item.textContent?.includes('IICE example comparisons'))!
    .closest('details')!;
  click(examples.querySelector('summary'), 'open examples');
  check(examples.querySelectorAll('li').length === 4, 'All IICE examples retained');
  click(examples.querySelector('li button') as HTMLButtonElement, 'open IICE example');
  await waitFor(
    () => document.querySelectorAll('figure').length === 4,
    'example opens directly into plots',
  );
}

async function testAnalysisFilters() {
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(
    () => document.getElementById('diagnostic-case-search'),
    'analysis workspace setup',
  );
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'analysis');
  await waitFor(() => button('case.metadata · 4 runs'), 'mixed-analysis case found');
  check(analysisTab('All')?.getAttribute('aria-selected') === 'true', 'Workspace defaults to All');
  check(analysisTab('All')?.textContent === 'All (4)', 'All count deduplicates supported runs');
  check(
    analysisTab('Climatology')?.textContent === 'Climatology (4)',
    'Climatology count for active case',
  );
  check(
    analysisTab('Time Series')?.textContent === 'Time Series (1)',
    'Time-series count for active case',
  );
  click(analysisTab('Time Series'), 'workspace time-series filter');
  await waitFor(
    () => document.querySelector('h4')?.textContent?.startsWith('0001–0050'),
    'workspace time-series filter preserves climatology-first grouping',
  );
  click(
    document.querySelector<HTMLButtonElement>(
      '#available-case-diagnostics button[aria-label^="Add MPAS"]',
    ),
    'workspace MPAS selection',
  );
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'one whole-run selection',
  );
  click(analysisTab('Climatology'), 'workspace climatology filter');
  await waitFor(
    () => document.querySelector('h4')?.textContent?.startsWith('0001–0050'),
    'workspace climatology grouping',
  );
  check(
    document.querySelector('#available-case-diagnostics button[aria-label^="Remove MPAS"]'),
    'Workspace Added state survives filter',
  );
  check(
    document.querySelectorAll('#available-case-diagnostics a[aria-label^="Open "]').length === 4,
    'Climatology filter keeps combined runs',
  );
  click(button('case.beta · 2 runs'), 'switch case with analysis filter');
  await waitFor(
    () =>
      document.querySelector('#available-case-diagnostics')?.getAttribute('aria-label') ===
      'Diagnostics for case.beta',
    'beta selected with filter',
  );
  check(
    analysisTab('Climatology')?.getAttribute('aria-selected') === 'true' &&
      toolButton('MPAS-Analysis')?.disabled,
    'Single-tool case retains available analysis and disables missing tool',
  );
  click(
    document.querySelector<HTMLButtonElement>(
      '#available-case-diagnostics button[aria-label^="Add E3SM"]',
    ),
    'select beta climatology',
  );
  await waitFor(
    () => JSON.parse(localStorage.getItem('simboard.diagnostics-workspace')!).runs.length === 2,
    'mixed selections retained',
  );
  check(
    document.body.textContent?.includes('Run added to E3SM Diags'),
    'Other-category addition names its group',
  );
  check(
    !document.querySelector('[aria-label="Selected runs"]')?.textContent?.includes('case.beta'),
    'Other category stays hidden in selections',
  );
  check(
    analysisTab('Time Series')?.disabled &&
      analysisTab('Time Series')?.textContent === 'Time Series (0)',
    'Unavailable analysis stays visible with zero count',
  );
  click(button('case.metadata · 4 runs'), 'return to mixed analyses');
  await waitFor(
    () => analysisTab('Time Series') && !analysisTab('Time Series')!.disabled,
    'Time Series returns for a mixed-analysis case',
  );
  click(analysisTab('Time Series'), 'activate available time-series filter');
  await waitFor(
    () => analysisTab('Time Series')?.getAttribute('aria-selected') === 'true',
    'Time Series selected',
  );
  click(button('case.beta · 2 runs'), 'switch to unavailable active filter');
  await waitFor(
    () =>
      analysisTab('All')?.getAttribute('aria-selected') === 'true' &&
      JSON.parse(localStorage.getItem('simboard.diagnostics-workspace')!).analysis === 'all',
    'Unavailable active filter falls back to All',
  );
  check(analysisTab('Time Series')?.disabled, 'Fallback disables unavailable analysis');
  check(
    document.body.textContent?.includes('Selected runs (1/'),
    'Automatic fallback never removes selections',
  );
  click(button('case.metadata · 4 runs'), 'return to combined run');
  await waitFor(
    () => document.querySelector('#available-case-diagnostics button[aria-label^="Remove MPAS"]'),
    'MPAS remains selected after automatic fallback',
  );
  click(analysisTab('All'), 'restore all analyses');
  await waitFor(
    () =>
      document.querySelectorAll('#available-case-diagnostics a[aria-label^="Open "]').length === 4,
    'All rows restored',
  );
  check(
    document.documentElement.scrollWidth <= window.innerWidth + 1,
    'Analysis filters have no horizontal overflow',
  );
  click(compareAction(), 'compare whole runs after filtering');
  await waitFor(
    () => document.querySelectorAll('figure').length === 1,
    'one comparison panel per selected run',
  );
  const sharedRuns = parseCompareState(new URLSearchParams(latest.split('?')[1])).runs;
  check(sharedRuns.length === 1, 'Default comparison uses current category only');
  check(
    parseCompareState(new URLSearchParams(latest.split('?')[1])).selected?.length === 2,
    'Other categories remain selected in shared URL',
  );
  check(
    sharedRuns[0].url === `${base}/metadata/mpas_analysis/ts_0001-0500_climo_0001-0050/`,
    'Full MPAS run URL unchanged',
  );
  check(sharedRuns[0].label === 'case.metadata 0001-0050', 'Existing comparison label unchanged');
  render('/case/raw-only');
  await waitFor(() => button('Diagnostics (0)0 supported runs'), 'case without supported runs');
  check(
    button('Diagnostics (0)0 supported runs')?.getAttribute('aria-expanded') === 'false',
    'Empty diagnostics stay collapsed',
  );
  click(button('Diagnostics (0)0 supported runs'), 'expand empty diagnostics');
  await waitFor(
    () => button('Diagnostics (0)0 supported runs')?.getAttribute('aria-expanded') === 'true',
    'empty diagnostics expanded',
  );
  check(
    analysisTab('All')?.textContent === 'All (0)' &&
      toolButton('All')?.textContent === 'All (0)' &&
      analysisTab('Time Series')?.disabled &&
      toolButton('MPAS-Analysis')?.disabled,
    'Empty case keeps both labeled rows with disabled zero-count options',
  );
  check(
    !document.body.textContent?.includes('Check All for other runs.'),
    'Empty sources do not suggest hidden runs',
  );
  render('/case/metadata');
  await waitFor(
    () => analysisTab('Time Series') && !analysisTab('Time Series')!.disabled,
    'case data update setup',
  );
  click(analysisTab('Time Series'), 'select case time series before update');
  await waitFor(
    () => analysisTab('Time Series')?.getAttribute('aria-selected') === 'true',
    'case time series active',
  );
  const original = client.getQueryData(['diagnostics', 'case-runs', 'metadata']);
  client.setQueryData(['diagnostics', 'case-runs', 'metadata'], {
    caseId: 'metadata',
    caseName: 'case.metadata',
    sources: [
      { rootUrl: `${base}/metadata/`, runs: [run('metadata')], error: null, partial: false },
    ],
  });
  await waitFor(
    () =>
      analysisTab('All')?.getAttribute('aria-selected') === 'true' &&
      toolButton('All')?.getAttribute('aria-pressed') === 'true' &&
      document.querySelectorAll('a[aria-label^="Open "]').length === 1,
    'Case Details falls back when data changes',
  );
  client.setQueryData(['diagnostics', 'case-runs', 'metadata'], original);
  await waitFor(
    () => analysisTab('All')?.getAttribute('aria-selected') === 'true',
    'Restored data keeps reset All analysis',
  );
}

async function testToolFilters() {
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/case/ranges');
  await waitFor(
    () =>
      document.querySelector('h1')?.textContent === 'Case ranges' &&
      toolButton('All')?.textContent === 'All (4)',
    'unique case tool counts',
  );
  check(toolButton('E3SM Diags')?.textContent === 'E3SM Diags (1)', 'Case E3SM count');
  check(
    toolButton('MPAS-Analysis')?.textContent === 'MPAS-Analysis (3)',
    'Case MPAS count deduplicates sources',
  );
  check(
    document.querySelector('[id$="-tool-label"]')?.textContent === 'Tool' &&
      document.querySelector('[id$="-analysis-label"]')?.textContent === 'Analysis',
    'Both filter rows have subtle hierarchy labels',
  );
  for (const kind of ['tool', 'analysis']) {
    const controls = document.querySelector(`[aria-label="Filter diagnostics by ${kind}"]`)!;
    check(
      document.getElementById(controls.getAttribute('aria-labelledby')!)?.textContent ===
        (kind === 'tool' ? 'Tool' : 'Analysis'),
      'Visible labels name their filter controls',
    );
  }
  const combinedUrl = `${base}/ranges/mpas_analysis/ts_0001-0100_climo_0051-0100/`;
  const combined = document
    .querySelector<HTMLAnchorElement>(`a[href="${combinedUrl}"]`)!
    .closest('li')!;
  check(
    combined.closest('section')?.querySelector('h4')?.textContent?.startsWith('0051–0100'),
    'MPAS groups by climatology range',
  );
  check(
    combined.textContent?.includes('Climatology: 0051–0100 · Time Series: 0001–0100'),
    'MPAS row keeps both time ranges',
  );
  check(combined.textContent?.includes('ts_0001-0100_climo_0051-0100'), 'MPAS identifier complete');
  check(
    document.querySelectorAll(`a[href="${combinedUrl}"]`).length === 1,
    'MPAS appears once across duplicate sources',
  );
  check(
    [...document.querySelectorAll('h4')].some((item) => item.textContent?.startsWith('0101–0200')),
    'Time-series-only run uses its time range',
  );
  check(
    [...document.querySelectorAll('h4')].some((item) =>
      item.textContent?.startsWith('Unknown time range'),
    ),
    'Missing metadata stays unknown despite identifier years',
  );
  click(toolButton('E3SM Diags'), 'filter single-analysis tool');
  await waitFor(
    () => document.querySelectorAll('a[aria-label^="Open "]').length === 1,
    'E3SM-only subset',
  );
  check(
    toolButton('All') &&
      analysisTab('Time Series')?.disabled &&
      analysisTab('All')?.textContent === 'All (1)',
    'Selected tool updates analysis counts and disables missing analysis',
  );
  check(
    getComputedStyle(toolButton('E3SM Diags')!).backgroundColor !==
      getComputedStyle(toolButton('All')!).backgroundColor &&
      getComputedStyle(toolButton('E3SM Diags')!).boxShadow !== 'none',
    'Active Tool filter has distinct background and shadow',
  );
  check(
    document.querySelector('[id$="-tool-label"]')?.textContent === 'Tool' &&
      document.querySelector('[id$="-analysis-label"]')?.textContent === 'Analysis',
    'Both filter labels remain visible',
  );
  click(toolButton('MPAS-Analysis'), 'filter case MPAS runs');
  await waitFor(
    () => document.querySelectorAll('a[aria-label^="Open "]').length === 3,
    'case MPAS filter',
  );
  click(analysisTab('Time Series'), 'filter MPAS time series');
  await waitFor(
    () => document.querySelectorAll('a[aria-label^="Open "]').length === 2,
    'MPAS time-series subset',
  );
  check(
    document.querySelector('h4')?.textContent?.startsWith('0051–0100'),
    'Analysis filter does not regroup combined MPAS run by time series',
  );
  click(
    document
      .querySelector<HTMLAnchorElement>(`a[href="${combinedUrl}"]`)!
      .closest('li')!
      .querySelector<HTMLButtonElement>('button[aria-label^="Add MPAS"]'),
    'select combined run after filtering',
  );
  await waitFor(
    () => document.querySelector('button[aria-label^="Remove MPAS"]'),
    'filtered MPAS selected',
  );
  check(
    toolButton('E3SM Diags')?.disabled &&
      toolButton('E3SM Diags')?.textContent === 'E3SM Diags (0)',
    'Time Series disables tools with no matching runs',
  );
  check(
    toolButton('All')?.textContent === 'All (2)' &&
      toolButton('MPAS-Analysis')?.textContent === 'MPAS-Analysis (2)',
    'Tool counts follow selected analysis without duplicates',
  );
  click(analysisTab('All'), 'clear analysis before switching tool');
  await waitFor(() => !toolButton('E3SM Diags')?.disabled, 'All analysis enables E3SM tool');
  click(toolButton('E3SM Diags'), 'switch to available tool');
  await waitFor(
    () =>
      analysisTab('All')?.textContent === 'All (1)' &&
      document.querySelectorAll('a[aria-label^="Open "]').length === 1,
    'Tool change updates analysis counts',
  );
  click(toolButton('MPAS-Analysis'), 'restore MPAS after analysis reset');
  await waitFor(
    () =>
      analysisTab('All')?.getAttribute('aria-selected') === 'true' &&
      document.querySelectorAll('a[aria-label^="Open "]').length === 3,
    'Tool switch keeps All analysis and includes unknown ranges',
  );
  click(analysisTab('All'), 'show all MPAS analyses');
  click(toolButton('All'), 'show all tools');
  await waitFor(
    () => document.querySelectorAll('a[aria-label^="Open "]').length === 4,
    'all case tools restored',
  );
  check(
    JSON.parse(localStorage.getItem('simboard.diagnostics-comparison')!).length === 1,
    'Tool filters preserve one selected URL',
  );
  click(toolButton('MPAS-Analysis'), 'active MPAS before data change');
  const original = client.getQueryData(['diagnostics', 'case-runs', 'ranges']);
  client.setQueryData(['diagnostics', 'case-runs', 'ranges'], {
    caseId: 'ranges',
    caseName: 'case.ranges',
    sources: [
      { rootUrl: `${base}/ranges/`, runs: [run('ranges', 51, 100)], error: null, partial: false },
    ],
  });
  await waitFor(
    () =>
      toolButton('All')?.getAttribute('aria-pressed') === 'true' &&
      toolButton('MPAS-Analysis')?.disabled &&
      document.querySelectorAll('a[aria-label^="Open "]').length === 1,
    'Missing active tool falls back to All on case data update',
  );
  const combinedRun = {
    ...run('ranges', 51, 100),
    tool: 'mpas_analysis',
    comparison: null,
    subsection: null,
    tsStartYear: 1,
    tsEndYear: 100,
    url: combinedUrl,
  };
  client.setQueryData(['diagnostics', 'case-runs', 'ranges'], {
    caseId: 'ranges',
    caseName: 'case.ranges',
    sources: [
      { rootUrl: `${base}/ranges/`, runs: [combinedRun, combinedRun], error: null, partial: false },
    ],
  });
  await waitFor(
    () =>
      toolButton('All')?.textContent === 'All (1)' &&
      analysisTab('All')?.textContent === 'All (1)' &&
      analysisTab('Time Series')?.textContent === 'Time Series (1)',
    'One combined MPAS run keeps unique counts in both filter rows',
  );
  check(
    analysisTab('Climatology')?.textContent === 'Climatology (1)' &&
      analysisTab('Time Series')?.textContent === 'Time Series (1)',
    'Combined analyses count one unique run each',
  );
  check(
    toolButton('E3SM Diags')?.disabled &&
      document.querySelector('[id$="-tool-label"]')?.textContent === 'Tool',
    'Single-tool case keeps Tool label and disables unavailable tool',
  );
  click(analysisTab('Time Series'), 'filter single combined MPAS run');
  await waitFor(
    () => analysisTab('Time Series')?.getAttribute('aria-selected') === 'true',
    'single MPAS time-series filter active',
  );
  check(
    document.querySelectorAll(`a[href="${combinedUrl}"]`).length === 1 &&
      document.querySelector('h4')?.textContent?.startsWith('0051–0100'),
    'Single combined MPAS run keeps unique climatology-first grouping',
  );
  client.setQueryData(['diagnostics', 'case-runs', 'ranges'], original);
  click(link('Diagnostics workspace'), 'workspace tool filters');
  await waitFor(
    () => document.getElementById('diagnostic-case-search'),
    'workspace browser for ranges',
  );
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'ranges');
  await waitFor(() => toolButton('All')?.textContent === 'All (4)', 'workspace unique tool counts');
  check(
    document.querySelector('[id$="-tool-label"]')?.textContent === 'Tool' &&
      document.querySelector('[id$="-analysis-label"]')?.textContent === 'Analysis',
    'Workspace uses same labeled filter hierarchy',
  );
  click(toolButton('MPAS-Analysis'), 'workspace MPAS filter');
  click(analysisTab('Time Series'), 'workspace MPAS time-series filter');
  await waitFor(
    () =>
      document.querySelectorAll('#available-case-diagnostics a[aria-label^="Open "]').length === 2,
    'workspace MPAS subset',
  );
  check(
    document.querySelector('h4')?.textContent?.startsWith('0051–0100'),
    'Workspace uses same climatology-first grouping',
  );
  check(
    document.querySelectorAll(`#available-case-diagnostics a[href="${combinedUrl}"]`).length === 1,
    'Workspace combined MPAS run stays unique in discovery',
  );
  check(
    document.querySelector('#available-case-diagnostics button[aria-label^="Remove MPAS"]'),
    'Cross-page Added state survives tool filtering',
  );
  render('/case/alpha');
  await waitFor(
    () => document.querySelector('h1')?.textContent === 'Case alpha',
    'leave workspace tool filter',
  );
  render('/diagnostics');
  await waitFor(
    () => toolButton('MPAS-Analysis')?.getAttribute('aria-pressed') === 'true',
    'Workspace tool filter persists across navigation',
  );
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'beta');
  await waitFor(
    () =>
      document.querySelector('#available-case-diagnostics')?.getAttribute('aria-label') ===
        'Diagnostics for case.beta' &&
      toolButton('All')?.getAttribute('aria-pressed') === 'true' &&
      analysisTab('All')?.getAttribute('aria-selected') === 'true' &&
      JSON.parse(localStorage.getItem('simboard.diagnostics-workspace')!).tool === 'all',
    'Workspace switches unavailable tool to All for next case',
  );
  check(
    JSON.parse(localStorage.getItem('simboard.diagnostics-workspace')!).analysis === 'all',
    'Unavailable analysis also resets with case switch',
  );
}

async function testViewer() {
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(() => document.getElementById('diagnostic-case-search'), 'search browser');
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'paged');
  await waitFor(
    () => document.body.textContent?.includes('No supported cases found on this page'),
    'bounded discovery empty page',
  );
  click(button('Load more cases'), 'load more supported cases');
  await waitFor(() => button('case.alpha · 2 runs'), 'supported case on next page');
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'unavailable');
  await waitFor(() => button('Retry discovery'), 'archive failure feedback');
  check(
    document.body.textContent?.includes(
      'Could not load diagnostics for case.unavailable. Results are incomplete.',
    ),
    'Archive failure names affected case and incompleteness',
  );
  click(button('Retry discovery'), 'retry failed archive');
  await waitFor(() => button('case.unavailable · 2 runs'), 'retry bypasses failed discovery cache');
  check(!button('Retry discovery'), 'Successful retry clears discovery warning');
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
  await expandSelections();
  click(
    document.querySelector('[role="dialog"] details summary'),
    'expand address and label editor',
  );
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
  click(button('Clear filter'), 'clear variable filter');
  await waitFor(
    () =>
      document.querySelector<HTMLInputElement>('input[aria-label="Filter variables"]')?.value ===
        '' && !button('Clear filter'),
    'filter cleared from empty state',
  );
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
  localStorage.removeItem('simboard.diagnostics-workspace');
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(() => selectedSummary(), 'synchronized selection summary');
  await expandSelections();
  await waitFor(
    () => document.querySelector('[aria-label="Comparison group"]'),
    'automatic tray group',
  );
  check(
    document.querySelector('[aria-label="Comparison group"]')?.textContent?.includes('(1/12)'),
    'Selected group dropdown displays selected count and limit',
  );
  check(
    Boolean(
      selectedSummary()!.compareDocumentPosition(
        document.querySelector('[aria-label="Comparison group"]')!,
      ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ),
    'Selected heading precedes group dropdown',
  );
  check(!button('Import tray selections'), 'No manual import step');
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'automatic grouped selection',
  );
  check(
    !document.querySelector('[aria-label="Selected runs"]')?.textContent?.includes('Staged MPAS'),
    'Import does not silently mix diagnostic kinds',
  );
}

async function testUnifiedSelections() {
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/case/alpha');
  await waitFor(
    () => document.querySelector('button[aria-label^="Add E3SM"]'),
    'case selection setup',
  );
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label^="Add E3SM"]'),
    'stage case diagnostic',
  );
  await waitFor(() => button('Expand'), 'case selection staged');
  click(link('Diagnostics workspace'), 'open synchronized workspace');
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'Case selection automatically available',
  );
  check(!button('Import tray selections'), 'No import action required');
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'analysis');
  await waitFor(() => button('case.metadata · 4 runs'), 'persistent search setup');
  click(button('case.beta · 2 runs'), 'choose beta');
  await waitFor(
    () => document.querySelector('#available-case-diagnostics button[aria-label^="Add E3SM"]'),
    'beta diagnostics',
  );
  click(
    document.querySelector<HTMLButtonElement>(
      '#available-case-diagnostics button[aria-label^="Add E3SM"]',
    ),
    'select beta',
  );
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (2/'),
    'workspace selected beta',
  );
  check(
    JSON.parse(localStorage.getItem('simboard.diagnostics-comparison')!).length === 2,
    'Workspace Add updates tray immediately',
  );
  await expandSelections();
  const backlink = document.querySelector<HTMLAnchorElement>('[aria-label="View Case case.beta"]');
  check(
    backlink?.getAttribute('href') === '/cases/chrysalis/scientist/case.beta#diagnostics-beta',
    'Backlink uses readable case route',
  );
  click(backlink, 'View Case backlink');
  await waitFor(
    () => document.querySelector('h1')?.textContent === 'Case beta',
    'backlink destination',
  );
  await waitFor(
    () => document.querySelector('button[aria-label^="Remove E3SM"]'),
    'Case Details reflects workspace selection',
  );
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label^="Remove E3SM"]'),
    'remove from case',
  );
  await waitFor(
    () => document.body.textContent?.includes('1 selected'),
    'case removal updates tray',
  );
  click(link('Diagnostics workspace'), 'return to workspace');
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'Case removal updates workspace',
  );
  check(
    (document.getElementById('diagnostic-case-search') as HTMLInputElement).value === 'analysis',
    'Search survives backlink navigation',
  );
  await waitFor(
    () => button('case.beta · 2 runs')?.getAttribute('aria-pressed') === 'true',
    'Selected case survives navigation',
  );
  check(
    analysisTab('All')?.getAttribute('aria-selected') === 'true' &&
      JSON.parse(localStorage.getItem('simboard.diagnostics-workspace')!).analysis === 'all',
    'Single-analysis case keeps All filter across navigation',
  );
  click(
    document.querySelector<HTMLButtonElement>(
      '#available-case-diagnostics button[aria-label^="Add E3SM"]',
    ),
    'reselect beta',
  );
  await waitFor(() => document.body.textContent?.includes('Selected runs (2/'), 'beta reselected');
  render('/case/raw-only');
  await waitFor(
    () => document.querySelector('h1')?.textContent === 'Case raw-only',
    'unmount workspace for refresh',
  );
  client.clear();
  render('/diagnostics');
  await waitFor(
    () => button('case.beta · 2 runs')?.getAttribute('aria-pressed') === 'true',
    'Selected case restored without query cache',
  );
  check(document.body.textContent?.includes('Selected runs (2/'), 'Selections survive refresh');
  check(
    analysisTab('All')?.getAttribute('aria-selected') === 'true' &&
      JSON.parse(localStorage.getItem('simboard.diagnostics-workspace')!).analysis === 'all',
    'Single-analysis case keeps All filter across refresh',
  );
  check(
    !document.body.textContent?.includes('supported cases found in checked results'),
    'No routine discovery status clutter',
  );
  check(
    document.querySelector('button[aria-label="Remove run 1"]'),
    'Selected details stay open after refresh',
  );
  await expandSelections();
  const selections = document.querySelector('[aria-label="Selected runs"]')!;
  check(
    Boolean(
      document.getElementById('available-case-diagnostics')!.compareDocumentPosition(selections) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ),
    'Selected entries follow discovery panels',
  );
  check(
    getComputedStyle(compareAction()!.closest('footer')!).position === 'sticky',
    'Compare remains in sticky footer',
  );
  check(
    !selections.querySelector('button[aria-expanded]') &&
      selectedSummary()?.parentElement === selections,
    'Selected heading sits above permanently visible selection controls',
  );
  check(
    Boolean(
      selectedSummary()!.compareDocumentPosition(selections.querySelector('a')!) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ),
    'Selected heading precedes selected rows',
  );
  render(comparePath([{ url: url('alpha'), label: 'Explicit shared selection' }]));
  await waitFor(
    () => document.querySelectorAll('figure').length === 1,
    'Shared URL overrides local selections',
  );
  check(
    !document.body.textContent?.includes('case.beta'),
    'No unrelated local run in shared comparison',
  );
  click(button('Edit runs'), 'edit explicit selection');
  await waitFor(() => document.querySelector('[role="dialog"]'), 'shared editor');
  check(
    document.querySelector('[role="dialog"]')?.textContent?.includes('Selected runs (1/'),
    'Shared editor does not merge local runs',
  );
  click(button('Cancel'), 'cancel shared edits');
}

async function testDiscoveryWarnings() {
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(() => document.getElementById('diagnostic-case-search'), 'warning test setup');
  for (const [search, message] of [
    ['partial', 'Run discovery is incomplete for case.partial. Some runs may be missing.'],
    [
      'request-failed',
      'Could not load diagnostics for case.request-failed. Results are incomplete.',
    ],
    ['search-failed', 'Case search failed. Results may be incomplete.'],
  ]) {
    input(document.getElementById('diagnostic-case-search') as HTMLInputElement, search);
    await waitFor(() => document.body.textContent?.includes(message), `${search} specific warning`);
    check(
      !document.body.textContent?.includes('Some results could not be read'),
      'No vague warning',
    );
    check(button('Retry discovery'), 'Transient failure can be retried');
    if (search === 'partial')
      check(button('case.partial · 1 runs'), 'Partial discovery keeps available runs');
  }
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'raw-only');
  await waitFor(
    () => document.body.textContent?.includes('No supported cases found.'),
    'benign empty directory',
  );
  check(!button('Retry discovery'), 'Empty unsupported directory does not trigger a warning');
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'rejected');
  await waitFor(
    () =>
      latest === '/diagnostics' &&
      client.getQueryState(['diagnostics', 'supported-cases', 'rejected'])?.status === 'success' &&
      JSON.parse(localStorage.getItem('simboard.diagnostics-workspace')!).search === 'rejected' &&
      !document.querySelector('[aria-label="Browse cases"] li') &&
      document.body.textContent?.includes('No supported cases found.'),
    'unsupported-only case excluded',
  );
  check(!button('Retry discovery'), 'Unsupported directories are silently excluded');
  check(
    !document.body.textContent?.includes('not on a supported public server'),
    'No unsupported-directory warning',
  );
  check(
    discoveryLogs.some(
      (args) => args[0] === 'Diagnostics discovery excluded unsupported directories',
    ),
    'Excluded sources retain troubleshooting logs',
  );
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'mixed');
  await waitFor(
    () => button('case.mixed · 1 runs'),
    'Case with both supported and unsupported directories',
  );
  check(
    !document.body.textContent?.includes('Unsupported output'),
    'Unsupported source omitted from available diagnostics',
  );
  check(
    !document.body.textContent?.includes('not on a supported public diagnostics server'),
    'No unsupported warning in available diagnostics',
  );
  const info = document.querySelector<HTMLButtonElement>(
    '[aria-label="About supported diagnostics"]',
  )!;
  info.focus();
  await waitFor(
    () =>
      document.querySelector('[role="tooltip"]')?.textContent ===
      'Only publicly accessible E3SM Diags and MPAS-Analysis runs supported by the comparison viewer are listed.',
    'Supported diagnostic info tooltip available by keyboard',
  );
  (document.getElementById('diagnostic-case-search') as HTMLInputElement).focus();
}

async function testCompatibilityValidation() {
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(() => button('case.alpha · 2 runs'), 'compatibility setup');
  check(compareAction()?.disabled, 'Compare disabled without a run');
  const before = validations;
  click(
    document.querySelector<HTMLButtonElement>(
      '#available-case-diagnostics button[aria-label^="Add E3SM"]',
    ),
    'select first supported run',
  );
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'minimum selection',
  );
  check(!compareAction()?.disabled, 'Compare enabled at API minimum of one run');
  click(button('case.beta · 2 runs'), 'select second case for validation');
  await waitFor(
    () =>
      document.getElementById('available-case-diagnostics')?.getAttribute('aria-label') ===
      'Diagnostics for case.beta',
    'second validation case',
  );
  click(
    document.querySelector<HTMLButtonElement>(
      '#available-case-diagnostics button[aria-label^="Add E3SM"]',
    ),
    'select second supported run',
  );
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (2/'),
    'two supported selections',
  );
  check(validations === before, 'Selection does not validate compatibility');
  comparisonDelay = 100;
  const compare = compareAction()!;
  click(compare, 'validate on Compare');
  compare.click();
  await waitFor(
    () => document.querySelector('button[aria-busy="true"]'),
    'Compatibility loading state',
  );
  check(
    document.querySelector<HTMLButtonElement>('button[aria-busy="true"]')?.disabled,
    'Pending Compare disabled',
  );
  check(
    document.querySelector<HTMLFieldSetElement>('fieldset')?.disabled,
    'Selections cannot change during validation',
  );
  await waitFor(
    () => document.querySelectorAll('figure').length === 2,
    'Compatible runs navigate to viewer',
  );
  await new Promise((resolve) => setTimeout(resolve, 20));
  check(
    validations === before + 1,
    'Duplicate clicks and viewer reuse do not duplicate validation',
  );
  comparisonDelay = 0;

  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(() => button('Add by URL'), 'incompatible setup');
  click(button('Add by URL'), 'manual compatibility tab');
  await waitFor(() => document.getElementById('manual-run-url'), 'manual compatibility input');
  input(document.getElementById('manual-run-url') as HTMLInputElement, url('incompatible'));
  await new Promise((resolve) => setTimeout(resolve, 10));
  click(button('Add run'), 'select incompatible run');
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'incompatible selection accepted',
  );
  const beforeIncompatible = compares;
  check(!compareAction()?.disabled, 'Supported selection remains comparable until checked');
  check(!document.querySelector('[role="alert"]'), 'No compatibility warning during selection');
  click(compareAction(), 'check incompatible plots');
  await waitFor(
    () =>
      document.querySelector('[role="alert"]')?.textContent ===
      'Selected runs have no plots in common. Choose compatible runs.',
    'Specific no-common-plots message',
  );
  check(
    latest === '/diagnostics' && !document.querySelector('figure'),
    'Incompatible selection stays on setup page',
  );
  check(
    JSON.parse(localStorage.getItem('simboard.diagnostics-workspace')!).runs[0].url ===
      url('incompatible'),
    'Failed compatibility preserves selection',
  );
  check(compares === beforeIncompatible + 1, 'One compatibility request for no shared plots');
  await expandSelections();
  click(
    document.querySelector<HTMLButtonElement>('button[aria-label="Remove run 1"]'),
    'replace incompatible run',
  );
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (0/'),
    'removed incompatible run',
  );
  input(document.getElementById('manual-run-url') as HTMLInputElement, url('network-fail'));
  await new Promise((resolve) => setTimeout(resolve, 10));
  click(button('Add run'), 'select run before network error');
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'network run selected',
  );
  comparisonFailures = 1;
  click(compareAction(), 'trigger network validation failure');
  await waitFor(() => button('Retry comparison'), 'Actionable validation retry');
  check(
    document
      .querySelector('[role="alert"]')
      ?.textContent?.includes('Check your connection and try again.'),
    'Network failure has actionable message',
  );
  check(latest === '/diagnostics', 'Network error does not navigate');
  check(
    document.body.textContent?.includes('Selected runs (1/'),
    'Network error preserves selections',
  );
  click(button('Retry comparison'), 'retry compatibility');
  await waitFor(
    () => document.querySelectorAll('figure').length === 1,
    'Retry opens compatible viewer',
  );

  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(() => button('Add by URL'), 'abandoned validation setup');
  click(button('Add by URL'), 'abandoned manual tab');
  await waitFor(() => document.getElementById('manual-run-url'), 'abandoned manual input');
  input(document.getElementById('manual-run-url') as HTMLInputElement, url('abandoned'));
  await new Promise((resolve) => setTimeout(resolve, 10));
  click(button('Add run'), 'select run before navigation');
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (1/'),
    'abandoned run selected',
  );
  comparisonDelay = 100;
  click(compareAction(), 'start abandoned validation');
  await waitFor(
    () => document.querySelector('button[aria-busy="true"]'),
    'abandoned request pending',
  );
  click(link('Alpha case'), 'leave setup while validating');
  await waitFor(
    () => document.querySelector('h1')?.textContent === 'Case alpha',
    'case after abandoning validation',
  );
  await new Promise((resolve) => setTimeout(resolve, 150));
  check(latest === '/case/alpha', 'Completed request does not navigate after leaving setup');
  comparisonDelay = 0;
}

async function testTrayCompatibility() {
  const stage = (ids: string[]) => {
    localStorage.clear();
    localStorage.setItem(
      'simboard.diagnostics-comparison',
      JSON.stringify(
        ids.map((id) => ({
          url: url(id),
          caseId: id,
          caseName: `case.${id}`,
          tool: 'e3sm_diags',
          comparison: 'model_vs_obs',
          period: '0001-0050',
          subsection: 'atm_monthly_180x360_aave',
        })),
      ),
    );
    window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
    render('/case/alpha');
  };
  stage(['tray-one', 'tray-two']);
  await waitFor(
    () => compareAction() && document.querySelector('h1')?.textContent === 'Case alpha',
    'tray compatible setup',
  );
  const before = validations;
  comparisonDelay = 100;
  const compareButton = compareAction()!;
  click(compareButton, 'tray compatibility check');
  compareButton.click();
  await waitFor(
    () => document.querySelector('[aria-label="Diagnostics comparison"] button[aria-busy="true"]'),
    'tray loading state',
  );
  check(latest === '/case/alpha', 'Tray waits for validation before navigation');
  await waitFor(
    () => document.querySelectorAll('figure').length === 2,
    'Tray opens every selected compatible run',
  );
  check(
    validations === before + 1,
    'Tray duplicate clicks and viewer reuse make one validation request',
  );
  comparisonDelay = 0;

  stage(['tray-one', 'unreadable']);
  await waitFor(
    () => compareAction() && document.querySelector('h1')?.textContent === 'Case alpha',
    'tray unreadable setup',
  );
  click(compareAction(), 'tray unreadable validation');
  await waitFor(() => button('Retry comparison'), 'tray archive failure retry');
  check(
    latest === '/case/alpha' && !document.querySelector('figure'),
    'Unreadable selected run blocks incomplete viewer',
  );
  check(
    document.querySelector('[role="alert"]')?.textContent?.includes('case.unreadable'),
    'Tray identifies unreadable selected run',
  );
  check(
    JSON.parse(localStorage.getItem('simboard.diagnostics-comparison')!).length === 2,
    'Tray preserves selections on failure',
  );

  stage(['tray-one', 'incompatible']);
  await waitFor(() => compareAction(), 'tray incompatible setup');
  click(compareAction(), 'tray no-common-plots validation');
  await waitFor(
    () =>
      document.querySelector('[role="alert"]')?.textContent ===
      'Selected runs have no plots in common. Choose compatible runs.',
    'tray specific incompatibility message',
  );
  check(latest === '/case/alpha', 'Incompatible tray stays on case page');
  check(!button('Retry comparison'), 'Incompatibility does not offer network retry');

  stage(['tray-network-one', 'tray-network-two']);
  await waitFor(() => compareAction(), 'tray network setup');
  comparisonFailures = 1;
  click(compareAction(), 'tray network error');
  await waitFor(() => button('Retry comparison'), 'tray network retry available');
  click(button('Retry comparison'), 'tray retry network');
  await waitFor(
    () => document.querySelectorAll('figure').length === 2,
    'Tray retry opens both runs',
  );

  stage(['tray-abandon-one', 'tray-abandon-two']);
  await waitFor(
    () => compareAction() && document.querySelector('h1')?.textContent === 'Case alpha',
    'tray abandoned setup',
  );
  comparisonDelay = 100;
  click(compareAction(), 'start tray validation before leaving');
  await waitFor(() => document.querySelector('button[aria-busy="true"]'), 'tray request pending');
  click(link('Beta case'), 'leave case during tray validation');
  await waitFor(
    () => document.querySelector('h1')?.textContent === 'Case beta',
    'new case after leaving',
  );
  await new Promise((resolve) => setTimeout(resolve, 150));
  check(latest === '/case/beta', 'Tray result does not override navigation');
  comparisonDelay = 0;
}

async function testExampleRetryAndGroupSwitch() {
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(() => button('Add by URL'), 'example retry setup');
  click(button('Add by URL'), 'example retry tab');
  await waitFor(() => document.getElementById('manual-run-url'), 'example retry form');
  const examples = [...document.querySelectorAll('summary')]
    .find((item) => item.textContent?.includes('IICE example comparisons'))!
    .closest('details')!;
  click(examples.querySelector('summary'), 'show examples for failed check');
  comparisonFailures = 1;
  click(
    examples.querySelector<HTMLButtonElement>('li button'),
    'open example with transient failure',
  );
  await waitFor(() => button('Retry comparison'), 'example validation retry offered');
  check(
    document.body.textContent?.includes('Selected runs (0/'),
    'Failed example does not replace current selections',
  );
  click(button('Retry comparison'), 'retry original example');
  await waitFor(
    () => document.querySelectorAll('figure').length === 4,
    'Retry opens all original example runs',
  );
  check(
    parseCompareState(new URLSearchParams(latest.split('?')[1])).runs[0].label ===
      'E3SMv2 historical',
    'Retry uses example runs, not empty draft',
  );

  const staged = [
    {
      url: url('staged-obs'),
      caseId: 'obs',
      caseName: 'Staged observations',
      tool: 'e3sm_diags',
      comparison: 'model_vs_obs',
      period: '0001-0050',
      subsection: 'atm_monthly_180x360_aave',
    },
    {
      url: `${base}/staged-mpas/mpas_analysis/ts_0001-0050_climo_0001-0050/`,
      caseId: 'mpas',
      caseName: 'Staged MPAS',
      tool: 'mpas_analysis',
      comparison: null,
      period: '0001-0050',
      subsection: null,
    },
  ];
  localStorage.clear();
  localStorage.setItem('simboard.diagnostics-comparison', JSON.stringify(staged));
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await waitFor(
    () => selectedSummary()?.textContent?.includes('Selected runs (1/'),
    'staged group switch setup',
  );
  click(button('Add by URL'), 'manual run before group switch');
  await waitFor(() => document.getElementById('manual-run-url'), 'manual group-switch input');
  input(document.getElementById('manual-run-url') as HTMLInputElement, url('manual-group-switch'));
  await new Promise((resolve) => setTimeout(resolve, 10));
  click(button('Add run'), 'add manual run to staged group');
  await waitFor(
    () => document.body.textContent?.includes('Selected runs (2/'),
    'manual and staged runs selected',
  );
  comparisonFailures = 1;
  click(compareAction(), 'fail check before changing group');
  await waitFor(() => button('Retry comparison'), 'group switch starts with retry error');
  await expandSelections();
  const beforeSwitch = compares;
  const group = document.querySelector<HTMLButtonElement>('[aria-label="Comparison group"]')!;
  group.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
  await waitFor(() => document.querySelector('[role="option"]'), 'comparison groups opened');
  const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find(
    (item) => item.textContent === 'MPAS-Analysis (1/12)',
  )!;
  option.focus();
  option.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  await waitFor(
    () =>
      document.querySelector('[aria-label="Selected runs"]')?.textContent?.includes('Staged MPAS'),
    'new staged group selected',
  );
  check(
    !document.querySelector(`[aria-label="Selected runs"] a[href="${url('manual-group-switch')}"]`),
    'Group switch hides other-category manual URL',
  );
  check(
    document.body.textContent?.includes('Selected runs (1/'),
    'Group switch shows only current-category selections',
  );
  check(
    !document.querySelector('[role="alert"]') && !button('Retry comparison'),
    'Changing groups clears stale validation error and retry',
  );
  check(compares === beforeSwitch, 'Changing groups does not validate compatibility');
  check(
    JSON.parse(localStorage.getItem('simboard.diagnostics-comparison')!).length === 2,
    'Switching groups preserves unrelated staged selections',
  );
}

async function testSelectionScrollStability() {
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  const container = document.getElementById('root')!;
  container.style.paddingTop = '900px';
  container.style.paddingBottom = '900px';
  const settle = () => new Promise((resolve) => setTimeout(resolve, 50));
  const toggleWithoutJump = async (row: HTMLButtonElement, panel: HTMLElement, label: string) => {
    row.scrollIntoView({ block: 'center' });
    row.focus();
    await settle();
    const pageTop = window.scrollY;
    const panelTop = panel.scrollTop;
    const rowTop = row.getBoundingClientRect().top;
    const wasAdded = row.getAttribute('aria-pressed');
    click(row, label);
    await waitFor(() => row.getAttribute('aria-pressed') !== wasAdded, label);
    await settle();
    check(document.activeElement === row, `${label} retains row focus`);
    check(
      Math.abs(window.scrollY - pageTop) <= 1,
      `${label} keeps page scroll: ${pageTop} to ${window.scrollY}`,
    );
    check(
      Math.abs(panel.scrollTop - panelTop) <= 1,
      `${label} keeps diagnostic scroll: ${panelTop} to ${panel.scrollTop}`,
    );
    check(
      Math.abs(row.getBoundingClientRect().top - rowTop) <= 1,
      `${label} keeps row position: ${rowTop} to ${row.getBoundingClientRect().top}`,
    );
  };
  try {
    render('/case/dense-0');
    await waitFor(() => button('Diagnostics (30)30 supported runs'), 'scrolling case setup');
    const card = document.getElementById('diagnostics-dense-0')!;
    const panel = card.querySelector<HTMLElement>('.overflow-y-auto')!;
    const row = card.querySelectorAll<HTMLButtonElement>('li button[aria-pressed]')[12];
    await toggleWithoutJump(row, panel, 'Case Add');
    const paddingChanges: MutationRecord[] = [];
    const observer = new MutationObserver((records) => paddingChanges.push(...records));
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ['style'],
      attributeOldValue: true,
    });
    try {
      const secondRow = card.querySelectorAll<HTMLButtonElement>('li button[aria-pressed]')[13];
      await toggleWithoutJump(secondRow, panel, 'Case Add with existing tray');
      await toggleWithoutJump(secondRow, panel, 'Case Added with existing tray');
      check(
        paddingChanges.every((record) => record.oldValue?.includes('padding-bottom')),
        'Changing selection count never clears existing tray padding',
      );
    } finally {
      observer.disconnect();
    }
    await toggleWithoutJump(row, panel, 'Case Added');
    click(link('Diagnostics workspace'), 'scrolling workspace setup');
    await waitFor(
      () => document.getElementById('diagnostic-case-search'),
      'scrolling case browser',
    );
    input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'dense');
    await waitFor(
      () =>
        document.querySelectorAll('#available-case-diagnostics li button[aria-pressed]').length ===
        30,
      'dense workspace runs',
    );
    const available = document.getElementById('available-case-diagnostics')!;
    const workspacePanel = available.lastElementChild as HTMLElement;
    const workspaceRow =
      available.querySelectorAll<HTMLButtonElement>('li button[aria-pressed]')[12];
    await toggleWithoutJump(workspaceRow, workspacePanel, 'Workspace Add');
    await expandSelections();
    await toggleWithoutJump(
      workspaceRow,
      workspacePanel,
      'Workspace Added with expanded selections',
    );
  } finally {
    container.style.paddingTop = '';
    container.style.paddingBottom = '';
    window.scrollTo(0, 0);
  }
}

async function testDenseBrowser() {
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  render('/diagnostics');
  await new Promise((resolve) => setTimeout(resolve, 10));
  await waitFor(() => document.getElementById('diagnostic-case-search'), 'dense browser setup');
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'dense');
  await waitFor(
    () => document.querySelector('[aria-label="Browse cases"] ul')?.children.length === 6,
    'first dense page',
  );
  click(button('Load more cases'), 'second dense page');
  await waitFor(
    () => document.querySelector('[aria-label="Browse cases"] ul')?.children.length === 12,
    'second dense page loaded',
  );
  click(button('Load more cases'), 'third dense page');
  await waitFor(
    () => document.querySelector('[aria-label="Browse cases"] ul')?.children.length === 18,
    'third dense page loaded',
  );
  const cases = document.querySelector<HTMLElement>('[aria-label="Browse cases"]')!;
  const diagnostics = document.getElementById('available-case-diagnostics')!;
  const caseScroll = cases.querySelector('ul')!.parentElement!;
  const runScroll = diagnostics.lastElementChild as HTMLElement;
  check(
    Math.abs(cases.getBoundingClientRect().height - diagnostics.getBoundingClientRect().height) < 2,
    'Discovery panels have matching heights',
  );
  const scrollBounds = caseScroll.getBoundingClientRect();
  const visibleCases = [...cases.querySelectorAll('li')].filter(
    (item) =>
      item.getBoundingClientRect().top >= scrollBounds.top &&
      item.getBoundingClientRect().bottom <= scrollBounds.bottom,
  ).length;
  check(
    visibleCases >= 8 && visibleCases <= 10,
    `Discovery shows 8–10 cases before scrolling, saw ${visibleCases}`,
  );
  check(caseScroll.scrollHeight > caseScroll.clientHeight, 'Cases scroll independently');
  check(runScroll.scrollHeight > runScroll.clientHeight, 'Diagnostics scroll independently');
  if (window.innerWidth >= 768) {
    check(
      cases.getBoundingClientRect().right <= diagnostics.getBoundingClientRect().left,
      'Desktop two-column layout',
    );
    check(
      Math.abs(cases.getBoundingClientRect().top - diagnostics.getBoundingClientRect().top) < 2,
      'Desktop panels align',
    );
  } else {
    check(
      cases.getBoundingClientRect().bottom <= diagnostics.getBoundingClientRect().top,
      'Mobile stacked panels',
    );
  }
  for (let index = 1; index <= 12; index++) {
    click(
      diagnostics.querySelector<HTMLButtonElement>('button[aria-label^="Add E3SM"]'),
      'select dense run',
    );
    await waitFor(
      () => document.body.textContent?.includes(`Selected runs (${index}/`),
      'dense selected count',
    );
  }
  caseScroll.scrollTop = caseScroll.scrollHeight;
  runScroll.scrollTop = runScroll.scrollHeight;
  const compare = compareAction()!;
  check(
    compare.getBoundingClientRect().top >= 0 &&
      compare.getBoundingClientRect().bottom <= window.innerHeight,
    'Compare stays visible while panels scroll',
  );
  check(
    document.documentElement.scrollWidth <= window.innerWidth + 1,
    'Dense browser has no horizontal overflow',
  );
  render(
    comparePath(
      Array.from({ length: 12 }, (_, index) => ({
        url: url(`external-${index}`),
        label: `External ${index}`,
      })),
    ),
  );
  await waitFor(() => document.querySelectorAll('figure').length === 12, 'large comparison');
  click(button('Edit runs'), 'large comparison editor');
  await waitFor(() => document.querySelector('[role="dialog"]'), 'large editor dialog');
  const apply = button('Apply changes')!;
  check(
    apply.getBoundingClientRect().top >= 0 &&
      apply.getBoundingClientRect().bottom <= window.innerHeight,
    'Apply stays visible with twelve selections',
  );
  check(
    apply.parentElement!.parentElement!.getBoundingClientRect().height < 110,
    'Only compact comparison controls stay sticky',
  );
  click(button('Cancel'), 'close large editor');
}

async function testComparisonGroups() {
  localStorage.clear();
  window.dispatchEvent(new StorageEvent('storage', { key: 'simboard.diagnostics-comparison' }));
  localStorage.setItem(
    'simboard.diagnostics-workspace',
    JSON.stringify({
      search: 'analysis',
      caseId: 'metadata',
      analysis: 'climatology',
      tool: 'e3sm_diags',
    }),
  );
  const selected = [
    { url: url('group-atmosphere-one'), label: 'Atmosphere one' },
    { url: url('group-atmosphere-two'), label: 'Atmosphere two' },
    { url: url('group-ocean-one'), label: 'Ocean one' },
  ];
  render(
    `/diagnostics/compare?${compareSearch({
      runs: selected.slice(0, 2),
      selected,
      set: 'polar',
      plot: 'atmosphere/temperature/DJF',
      view: 'diff',
      filter: 'Temperature',
    })}`,
  );
  await waitFor(
    () => document.querySelector('[aria-labelledby="comparison-group-label"]'),
    'actual plot groups',
  );
  check(
    document.body.textContent?.includes('2 active runs · 3 selected runs'),
    'Active and selected counts differ',
  );
  const chooseGroup = async (text: string) => {
    const trigger = document.querySelector<HTMLElement>(
      '[aria-labelledby="comparison-group-label"]',
    )!;
    trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    await waitFor(() => document.querySelector('[role="option"]'), 'group options');
    const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find((item) =>
      item.textContent?.includes(text),
    )!;
    option.focus();
    option.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  };
  await chooseGroup('(1 runs)');
  await waitFor(
    () => document.querySelector('figure')?.textContent?.includes('Ocean one'),
    'ocean plots',
  );
  let state = parseCompareState(new URLSearchParams(latest.split('?')[1]));
  check(state.selected?.length === 3 && state.runs.length === 1, 'Switch preserves selected URLs');
  check(
    state.set === 'polar' && state.view === 'diff' && state.filter === 'Temperature',
    'Switch preserves unrelated viewer settings',
  );
  const shared = latest;
  localStorage.clear();
  render(shared);
  await waitFor(
    () => document.querySelector('figure')?.textContent?.includes('Ocean one'),
    'direct shared group restored',
  );
  await waitFor(
    () => document.querySelector('[aria-labelledby="comparison-group-label"]'),
    'shared selections restore selector',
  );
  await new Promise((resolve) => setTimeout(resolve, 50));
  click(button('Edit runs'), 'compact group editor');
  await waitFor(() => document.querySelector('[role="dialog"]'), 'compact editor open');
  check(
    !document.querySelector('[role="dialog"] [aria-label="Browse cases"]'),
    'Editor omits case browser',
  );
  check(!document.querySelector('[role="dialog"] [role="tablist"]'), 'Editor omits setup tabs');
  click(button('Cancel'), 'cancel compact editor');
  await waitFor(() => !document.querySelector('[role="dialog"]'), 'compact editor closed');
  check(latest === shared, 'Cancel preserves shared group URL');
  await chooseGroup('(2 runs)');
  await waitFor(
    () => document.querySelectorAll('figure').length === 2,
    'shared nondefault category groups',
  );
  state = parseCompareState(new URLSearchParams(latest.split('?')[1]));
  check(state.runs.length === 2, 'Runs sharing only nondefault category remain together');
  check(state.plot === 'atmosphere/temperature/DJF', 'Group switch keeps variable and season');
  click(button('Edit runs'), 'edit active group with inactive selections');
  await waitFor(() => document.querySelector('[role="dialog"]'), 'active group editor');
  click(document.querySelector('[role="dialog"] details summary'), 'edit active label');
  input(
    document.querySelector<HTMLInputElement>('input[aria-label="Run 1 label"]')!,
    'Renamed atmosphere',
  );
  await new Promise((resolve) => setTimeout(resolve, 10));
  click(button('Apply changes'), 'apply active group label');
  await waitFor(() => !document.querySelector('[role="dialog"]'), 'active group label applied');
  state = parseCompareState(new URLSearchParams(latest.split('?')[1]));
  check(
    state.selected?.length === 3 && state.selected.some((item) => item.label === 'Ocean one'),
    'Apply retains inactive group',
  );
  check(state.runs[0].label === 'Renamed atmosphere', 'Apply updates active label');
  click(link('Back to Diagnostics'), 'return from direct share');
  await waitFor(
    () => selectedSummary()?.textContent?.includes('Selected runs (3/'),
    'shared selections return to setup',
  );
  check(latest === '/diagnostics', 'Back targets setup, not browser history');
  check(
    JSON.parse(localStorage.getItem('simboard.diagnostics-workspace')!).runs.length === 3,
    'Setup keeps all shared selections',
  );
  input(document.getElementById('diagnostic-case-search') as HTMLInputElement, 'analysis');
  await waitFor(() => button('case.metadata · 4 runs'), 'setup search for return-state test');
  click(button('case.metadata · 4 runs'), 'set active setup case');
  click(toolButton('E3SM Diags'), 'set setup tool filter');
  click(analysisTab('Climatology'), 'set setup analysis filter');
  await new Promise((resolve) => setTimeout(resolve, 10));
  render(shared);
  await new Promise((resolve) => setTimeout(resolve, 50));
  await waitFor(() => link('Back to Diagnostics'), 'viewer before setup-state return');
  click(link('Back to Diagnostics'), 'restore setup state');
  await waitFor(() => document.getElementById('diagnostic-case-search'), 'setup state restored');
  check(
    (document.getElementById('diagnostic-case-search') as HTMLInputElement).value === 'analysis',
    'Back preserves search',
  );
  await waitFor(
    () => toolButton('E3SM Diags')?.getAttribute('aria-pressed') === 'true',
    'Back preserves tool filter',
  );
  check(
    analysisTab('Climatology')?.getAttribute('aria-selected') === 'true',
    'Back preserves analysis filter',
  );
  check(
    document.querySelector('#available-case-diagnostics')?.getAttribute('aria-label') ===
      'Diagnostics for case.metadata',
    'Back preserves active case',
  );
  render(
    `/diagnostics/compare?${compareSearch({ runs: selected, set: 'polar', plot: null, view: 'test' })}`,
  );
  await new Promise((resolve) => setTimeout(resolve, 50));
  await waitFor(
    () => parseCompareState(new URLSearchParams(latest.split('?')[1])).runs.length === 2,
    'Mixed URL defaults to first compatible group',
  );
  const missing = { url: url('group-missing'), label: 'Missing category' };
  render(
    `/diagnostics/compare?${compareSearch({ runs: selected.slice(0, 2), selected: [...selected.slice(0, 2), missing], set: 'polar', plot: null, view: 'test' })}`,
  );
  await new Promise((resolve) => setTimeout(resolve, 50));
  await waitFor(
    () => document.querySelector('[aria-labelledby="comparison-group-label"]'),
    'missing-category selector',
  );
  await chooseGroup('(1 runs)');
  await waitFor(
    () => parseCompareState(new URLSearchParams(latest.split('?')[1])).set === 'lat_lon',
    'Switch resolves missing category in URL',
  );
}

testWorkspace()
  .then(testAnalysisFilters)
  .then(testToolFilters)
  .then(testViewer)
  .then(testUnifiedSelections)
  .then(testDiscoveryWarnings)
  .then(testCompatibilityValidation)
  .then(testTrayCompatibility)
  .then(testExampleRetryAndGroupSwitch)
  .then(testSelectionScrollStability)
  .then(testDenseBrowser)
  .then(testComparisonGroups)
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
