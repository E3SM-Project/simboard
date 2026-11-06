import type { SelectedRun } from '@/features/diagnostics/compareState';
import type {
  DiagnosticAnalysis,
  DiagnosticToolFilter,
} from '@/features/diagnostics/discoveryState';

interface WorkspaceState {
  runs: SelectedRun[];
  search: string;
  caseId: string | null;
  page: number;
  analysis: DiagnosticAnalysis;
  tool: DiagnosticToolFilter;
  tab: string;
  filter: string;
}

const STORAGE_KEY = 'simboard.diagnostics-workspace';
const DEFAULTS: WorkspaceState = {
  runs: [],
  search: '',
  caseId: null,
  page: 1,
  analysis: 'all',
  tool: 'all',
  tab: 'browse',
  filter: '',
};
let fallback = DEFAULTS;
let storageUnavailable = false;

export const readWorkspace = (): WorkspaceState => {
  if (storageUnavailable) return fallback;
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null');
    if (!value || typeof value !== 'object') return DEFAULTS;

    return {
      runs: Array.isArray(value.runs)
        ? value.runs.filter(
            (run: SelectedRun | null) =>
              run &&
              typeof run.url === 'string' &&
              typeof run.label === 'string' &&
              (!run.entry ||
                (typeof run.entry.caseId === 'string' &&
                  typeof run.entry.caseName === 'string' &&
                  (run.entry.tool === 'e3sm_diags' || run.entry.tool === 'mpas_analysis'))),
          )
        : [],
      search: typeof value.search === 'string' ? value.search : '',
      caseId: typeof value.caseId === 'string' ? value.caseId : null,
      page: Number.isInteger(value.page) && value.page > 0 ? value.page : 1,
      analysis:
        value.analysis === 'climatology' || value.analysis === 'time_series'
          ? value.analysis
          : 'all',
      tool: value.tool === 'e3sm_diags' || value.tool === 'mpas_analysis' ? value.tool : 'all',
      tab: value.tab === 'url' ? 'url' : 'browse',
      filter: typeof value.filter === 'string' ? value.filter : '',
    };
  } catch {
    return fallback;
  }
};

export const saveWorkspace = (patch: Partial<WorkspaceState>) => {
  fallback = { ...readWorkspace(), ...patch };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(fallback));
  } catch {
    // Storage full or disabled: retain this session's workspace in memory.
    storageUnavailable = true;
  }
};
