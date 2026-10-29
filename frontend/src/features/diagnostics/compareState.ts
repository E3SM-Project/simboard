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
  set: string | null;
  plot: string | null;
  view: PanelView;
}

export const COMPARE_PATH = '/diagnostics/compare';

const SEPARATOR = '|';

export const parseCompareState = (params: URLSearchParams): CompareState => {
  const runs = params
    .getAll('run')
    .map((value) => {
      const at = value.lastIndexOf(SEPARATOR);
      const url = (at >= 0 ? value.slice(0, at) : value).trim();
      return { url, label: (at >= 0 ? value.slice(at + 1) : '').trim() };
    })
    .filter((run) => run.url);
  const view = params.get('view');
  return {
    runs,
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
  if (state.set) params.set('set', state.set);
  if (state.plot) params.set('plot', state.plot);
  if (state.view !== 'test') params.set('view', state.view);
  return params.toString();
};

export const comparePath = (runs: CompareRun[]): string =>
  `${COMPARE_PATH}?${compareSearch({ runs, set: null, plot: null, view: 'test' })}`;

/**
 * A run label as people see it. A leading ``!`` marks an MPAS case-name
 * override (as in IICE) and is not shown.
 */
export const displayLabel = (run: CompareRun): string => run.label.replace(/^!/, '') || run.url;

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

/** The most runs that stay legible side by side. */
export const MAX_RUNS_PER_GROUP = 6;

export interface BasketEntry {
  url: string;
  caseId: string;
  caseName: string;
  tool: DiagnosticsTool;
  comparison: DiagnosticsRunOut['comparison'];
  period: string;
  subsection: string | null;
}

/**
 * Runs of different tools or kinds share no plots, so each kind is its own
 * comparison: E3SM Diags against observations, against a model, and MPAS.
 */
export const groupKey = (entry: Pick<BasketEntry, 'tool' | 'comparison'>): string =>
  entry.tool === 'mpas_analysis' ? entry.tool : `${entry.tool}:${entry.comparison}`;

export const toEntry = (run: DiagnosticsRunOut, caseId: string, caseName: string): BasketEntry => ({
  url: run.url,
  caseId,
  caseName,
  tool: run.tool,
  comparison: run.comparison,
  period: runPeriod(run),
  subsection: run.subsection,
});

export const entryLabel = (entry: BasketEntry): string =>
  [entry.caseName, entry.period].filter(Boolean).join(' ');
