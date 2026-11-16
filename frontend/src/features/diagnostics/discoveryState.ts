import type { DiagnosticsRunOut, DiagnosticsSourceOut, DiagnosticsTool } from './types';

export const RUN_GROUPS = [
  { key: 'e3sm_diags:model_vs_obs', title: 'E3SM Diags · model vs observations' },
  { key: 'e3sm_diags:model_vs_model', title: 'E3SM Diags · model vs model' },
  { key: 'mpas_analysis', title: 'MPAS-Analysis' },
];

export const runGroup = (run: DiagnosticsRunOut): string =>
  run.tool === 'mpas_analysis' ? run.tool : `${run.tool}:${run.comparison ?? 'model_vs_obs'}`;

export type DiagnosticAnalysis = 'all' | 'climatology' | 'time_series';
export type DiagnosticToolFilter = 'all' | DiagnosticsTool;

/** Discovery years are authoritative; never guess periods from identifiers. */
export const diagnosticPeriod = (
  run: DiagnosticsRunOut,
  analysis: DiagnosticAnalysis = 'all',
): string => {
  if (analysis === 'climatology') return diagnosticClimatologyPeriod(run) || 'Unknown time range';
  if (analysis === 'time_series') return diagnosticTimeSeriesPeriod(run) || 'Unknown time range';

  return (
    diagnosticClimatologyPeriod(run) || diagnosticTimeSeriesPeriod(run) || 'Unknown time range'
  );
};

export const diagnosticClimatologyPeriod = (run: DiagnosticsRunOut): string =>
  _period(run.startYear, run.endYear);

export const diagnosticTimeSeriesPeriod = (run: DiagnosticsRunOut): string =>
  _period(run.tsStartYear, run.tsEndYear);

/** Group across source directories while retaining every unique run URL. */
export const periodGroups = (
  sources: DiagnosticsSourceOut[],
  analysis: DiagnosticAnalysis = 'all',
  tool: DiagnosticToolFilter = 'all',
) => {
  const groups = new Map<string, DiagnosticsRunOut[]>();
  const seen = new Set<string>();
  for (const run of sources.flatMap((source) => source.runs)) {
    if (tool !== 'all' && run.tool !== tool) continue;
    if (analysis === 'climatology' && !diagnosticClimatologyPeriod(run)) continue;
    if (analysis === 'time_series' && !diagnosticTimeSeriesPeriod(run)) continue;
    if (seen.has(run.url)) continue;
    seen.add(run.url);
    const period = diagnosticPeriod(run);
    groups.set(period, [...(groups.get(period) ?? []), run]);
  }

  return [...groups]
    .sort(([left], [right]) => {
      if (left === 'Unknown time range') return 1;
      if (right === 'Unknown time range') return -1;
      return left.localeCompare(right, undefined, { numeric: true });
    })
    .map(([period, runs]): [string, DiagnosticsRunOut[]] => [
      period,
      runs.sort(
        (left, right) =>
          RUN_GROUPS.findIndex((group) => group.key === runGroup(left)) -
          RUN_GROUPS.findIndex((group) => group.key === runGroup(right)),
      ),
    ]);
};

export const diagnosticTitle = (run: DiagnosticsRunOut): string => {
  const analyses = [
    diagnosticClimatologyPeriod(run) ? 'Climatology' : '',
    diagnosticTimeSeriesPeriod(run) ? 'Time Series' : '',
  ].filter(Boolean);
  const comparison =
    run.tool === 'e3sm_diags' && run.comparison
      ? {
          model_vs_obs: 'Model vs. Observations',
          model_vs_model: 'Model vs. Model',
        }[run.comparison]
      : '';

  return [...(analyses.length ? analyses : ['Diagnostic run']), comparison]
    .filter(Boolean)
    .join(' · ');
};

/** Keep scientific identifiers verbatim, including when only the URL supplies one. */
export const diagnosticIdentifier = (
  run: Pick<DiagnosticsRunOut, 'subsection' | 'url' | 'tool'>,
): string => {
  if (run.subsection) return run.subsection;
  try {
    const parts = new URL(run.url).pathname.split('/').filter(Boolean).map(decodeURIComponent);
    const tool = parts.indexOf(run.tool);
    const excluded = ['viewer', 'index.html', 'html'];
    const identifier =
      tool >= 0 ? parts[tool + 1] : parts.filter((part) => !excluded.includes(part)).at(-1);

    return identifier && !excluded.includes(identifier) ? identifier : 'Identifier unavailable';
  } catch {
    return 'Identifier unavailable';
  }
};

const _period = (start: number | null, end: number | null): string =>
  start != null && end != null
    ? `${String(start).padStart(4, '0')}–${String(end).padStart(4, '0')}`
    : '';

export const diagnosticsId = (caseId: string): string => `diagnostics-${caseId}`;

export const sourceId = (caseId: string, index: number): string =>
  `${diagnosticsId(caseId)}-source-${index}`;

/** Match directory ancestry on the same origin, never a partial path segment. */
export const relatedDirectories = (left: string, right: string): boolean => {
  return containsDirectory(left, right) || containsDirectory(right, left);
};

const containsDirectory = (left: string, right: string): boolean => {
  try {
    const a = new URL(left);
    const b = new URL(right);
    if (!['https:', 'http:'].includes(a.protocol) || a.origin !== b.origin) return false;
    if (a.search !== b.search || a.username || b.username || a.password || b.password) return false;
    const aPath = `${a.pathname.replace(/\/+$/, '')}/`;
    const bPath = `${b.pathname.replace(/\/+$/, '')}/`;
    return bPath.startsWith(aPath);
  } catch {
    return false;
  }
};

/** The nearest section containing every structured group matched by a resource. */
export const resourceTarget = (
  caseId: string,
  url: string,
  sources: DiagnosticsSourceOut[],
): string | null => {
  const matches = sources.flatMap((source, index) => {
    const runs = source.runs.filter(
      (run) => relatedDirectories(url, run.url) || containsDirectory(url, source.rootUrl),
    );
    const groups = [...new Set(runs.map(runGroup))];
    return groups.length ? [{ index, groups }] : [];
  });
  if (!matches.length) return null;
  if (matches.length > 1) return diagnosticsId(caseId);
  const { index, groups } = matches[0];
  const parent = sourceId(caseId, index);
  return groups.length === 1 ? `${parent}-${groups[0]}` : parent;
};
