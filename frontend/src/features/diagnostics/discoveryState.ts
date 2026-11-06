import type { DiagnosticsRunOut, DiagnosticsSourceOut } from './types';

export const RUN_GROUPS = [
  { key: 'e3sm_diags:model_vs_obs', title: 'E3SM Diags · model vs observations' },
  { key: 'e3sm_diags:model_vs_model', title: 'E3SM Diags · model vs model' },
  { key: 'mpas_analysis', title: 'MPAS-Analysis' },
];

export const runGroup = (run: DiagnosticsRunOut): string =>
  run.tool === 'mpas_analysis' ? run.tool : `${run.tool}:${run.comparison ?? 'model_vs_obs'}`;

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
