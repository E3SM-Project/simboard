/**
 * Comparison state kept in the page URL, so the address bar is always a link
 * to exactly what is on screen. Plot matching happens in the backend.
 */

import type { DiagnosticsRunOut, DiagnosticsTool, PanelView } from '@/features/diagnostics/types';

export interface CompareRun {
  url: string;
  label: string;
}

export interface CompareState {
  runs: CompareRun[];
  selected?: CompareRun[];
  filter?: string;
  set: string | null;
  plot: string | null;
  view: PanelView;
}

export const COMPARE_PATH = '/diagnostics/compare';

/** The most runs one comparison accepts (the API's limit). */
export const MAX_COMPARED_RUNS = 12;

const SEPARATOR = '|';

export const parseCompareState = (params: URLSearchParams): CompareState => {
  const readRuns = (key: string) =>
    params
      .getAll(key)
      .map((value) => {
        const at = value.lastIndexOf(SEPARATOR);
        const url = (at >= 0 ? value.slice(0, at) : value).trim();
        return { url, label: (at >= 0 ? value.slice(at + 1) : '').trim() };
      })
      .filter((run) => run.url);
  const view = params.get('view');
  return {
    runs: readRuns('run'),
    ...(params.has('selected') ? { selected: readRuns('selected') } : {}),
    ...(params.has('filter') ? { filter: params.get('filter') ?? '' } : {}),
    set: params.get('set'),
    plot: params.get('plot'),
    view: view === 'ref' || view === 'diff' ? view : 'test',
  };
};

export const compareSearch = (state: CompareState): string => {
  const params = new URLSearchParams();
  for (const run of state.runs) {
    params.append('run', `${run.url}${SEPARATOR}${run.label.replaceAll(SEPARATOR, ' ')}`);
  }
  for (const run of state.selected ?? []) {
    params.append('selected', `${run.url}${SEPARATOR}${run.label.replaceAll(SEPARATOR, ' ')}`);
  }
  if (state.filter !== undefined) params.set('filter', state.filter);
  if (state.set) params.set('set', state.set);
  if (state.plot) params.set('plot', state.plot);
  if (state.view !== 'test') params.set('view', state.view);
  return params.toString();
};

export const comparePath = (runs: CompareRun[], selected?: CompareRun[]): string =>
  `${COMPARE_PATH}?${compareSearch({ runs, selected, set: null, plot: null, view: 'test' })}`;

/**
 * A run label as people see it. A leading ``!`` marks an MPAS case-name
 * override (an IICE convention) and is not shown.
 */
export const displayLabel = (run: CompareRun): string => {
  const label = run.label.replace(/^!/, '');
  if (label) return label;
  try {
    const url = new URL(run.url);
    const parts = url.pathname.split('/').filter(Boolean);
    const tool = parts.findIndex((part) => part === 'e3sm_diags' || part === 'mpas_analysis');
    const name =
      tool > 0
        ? parts[tool - 1]
        : parts.filter((part) => !['viewer', 'index.html', 'html'].includes(part)).at(-1) ||
          url.hostname;
    const period = url.pathname.match(/(?:model_vs_(?:obs|model)_|climo_|yrs)(\d+-\d+)/)?.[1];
    const compact = name.length > 54 ? `${name.slice(0, 30)}…${name.slice(-20)}` : name;
    return [compact, period && !compact.includes(period) ? period : ''].filter(Boolean).join(' ');
  } catch {
    return 'Diagnostic run';
  }
};

const pad = (year: number) => String(year).padStart(4, '0');

/** ``1985-2014`` for a run's climatology years, or ``''``. */
export const runPeriod = (run: Pick<DiagnosticsRunOut, 'startYear' | 'endYear'>): string =>
  run.startYear != null && run.endYear != null ? `${pad(run.startYear)}-${pad(run.endYear)}` : '';

/** Whether a URL looks like a run the backend can read. */
export const isRunUrl = (url: string): boolean =>
  /^https:\/\/\S+$/.test(url.trim()) &&
  (/\/viewer\/?(index\.html)?$/.test(url.trim()) ||
    /\/mpas_analysis\//.test(url) ||
    /\/(html|yrs\d+-\d+)\/?$/.test(url.trim()));

export const imageUrl = (base: string, path: string): string =>
  base + path.split('/').map(encodeURIComponent).join('/');

// ----------------------------------------------------------------------------
// Runs picked on case pages (see comparisonBasket.ts for the store)
// ----------------------------------------------------------------------------

/** Keep tray and workspace selection limits consistent with the comparison API. */
export const MAX_RUNS_PER_GROUP = MAX_COMPARED_RUNS;

export interface BasketEntry {
  url: string;
  caseId: string;
  caseName: string;
  tool: DiagnosticsTool;
  comparison: DiagnosticsRunOut['comparison'];
  period: string;
  subsection: string | null;
  casePath?: string;
}

export interface SelectedRun extends CompareRun {
  entry?: BasketEntry;
}

/** Scope setup selections; the viewer still verifies actual plot compatibility. */
export const selectedRunGroup = (run: SelectedRun): string => {
  if (run.entry) return groupKey(run.entry);
  if (/\/(mpas_analysis|yrs\d+-\d+|html)\//.test(`${run.url}/`)) return 'mpas_analysis';
  if (run.url.includes('model_vs_model')) return 'e3sm_diags:model_vs_model';
  if (run.url.includes('model_vs_obs')) return 'e3sm_diags:model_vs_obs';

  return 'manual';
};

/** Restore one staged kind automatically, without merging unrelated comparisons. */
export const syncSelectedRuns = (
  runs: SelectedRun[],
  entries: BasketEntry[],
  selectedGroup?: string,
): SelectedRun[] => {
  const retained = runs
    .filter((run) => !run.entry || entries.some((entry) => entry.url === run.url))
    .map((run) => ({ ...run, entry: entries.find((entry) => entry.url === run.url) ?? run.entry }));
  const kinds = new Set(retained.flatMap((run) => (run.entry ? [groupKey(run.entry)] : [])));
  const kind =
    kinds.size > 1
      ? null
      : (selectedGroup ??
        (kinds.size === 1
          ? [...kinds][0]
          : !retained.length && entries[0]
            ? groupKey(entries[0])
            : null));
  if (kind) {
    for (const entry of entries.filter((entry) => groupKey(entry) === kind)) {
      if (retained.length >= MAX_COMPARED_RUNS) break;
      if (!retained.some((run) => run.url === entry.url))
        retained.push({ url: entry.url, label: entryLabel(entry), entry });
    }
  }

  return retained;
};

/**
 * Runs of different tools or kinds share no plots, so each kind is its own
 * comparison: E3SM Diags against observations, against a model, and MPAS.
 */
export const groupKey = (entry: Pick<BasketEntry, 'tool' | 'comparison'>): string =>
  entry.tool === 'mpas_analysis' ? entry.tool : `${entry.tool}:${entry.comparison}`;

export const toEntry = (
  run: DiagnosticsRunOut,
  caseId: string,
  caseName: string,
  casePath?: string,
): BasketEntry => ({
  url: run.url,
  caseId,
  caseName,
  tool: run.tool,
  comparison: run.comparison,
  period: runPeriod(run),
  subsection: run.subsection,
  ...(casePath ? { casePath } : {}),
});

export const entryLabel = (entry: BasketEntry): string =>
  [entry.caseName, entry.period].filter(Boolean).join(' ');

/** Apply explicit workspace edits without replacing unrelated staged runs. */
export const reconcileBasket = (
  entries: BasketEntry[],
  previousUrls: string[],
  nextUrls: string[],
  additions: BasketEntry[],
): BasketEntry[] | null => {
  const next = entries.filter(
    (entry) => !previousUrls.includes(entry.url) || nextUrls.includes(entry.url),
  );
  for (const entry of additions) {
    if (nextUrls.includes(entry.url) && !next.some((item) => item.url === entry.url))
      next.push(entry);
  }
  if (
    next.some(
      (entry) =>
        next.filter((item) => groupKey(item) === groupKey(entry)).length > MAX_RUNS_PER_GROUP,
    )
  )
    return null;
  return next;
};
