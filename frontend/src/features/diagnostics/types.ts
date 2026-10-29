/** Wire types for the diagnostics API (``app/features/diagnostics``). */

export type DiagnosticsTool = 'e3sm_diags' | 'mpas_analysis';

export interface DiagnosticsRunOut {
  tool: DiagnosticsTool;
  /** E3SM Diags ``viewer/`` page or MPAS-Analysis run directory. */
  url: string;
  subsection: string | null;
  comparison: 'model_vs_obs' | 'model_vs_model' | null;
  startYear: number | null;
  endYear: number | null;
  tsStartYear: number | null;
  tsEndYear: number | null;
}

export interface DiagnosticsSourceOut {
  rootUrl: string;
  label: string | null;
  runs: DiagnosticsRunOut[];
  partial: boolean;
  error: string | null;
}

export interface CaseDiagnosticsOut {
  caseId: string;
  caseName: string;
  sources: DiagnosticsSourceOut[];
}

export interface CompareRunOut {
  url: string;
  label: string;
  tool: DiagnosticsTool | null;
  imageBaseUrl: string;
  /** Some of the run's pages could not be read, so plots may be missing. */
  partial: boolean;
  error: string | null;
}

/** A window onto one panel of a composite image, in image pixels. */
export interface PanelOut {
  width: number;
  height: number;
  top: number;
  left: number;
}

export interface ComparedPlotOut {
  key: string;
  season: string | null;
  region: string | null;
  singlePanel: boolean;
  /** Per requested run, relative to its ``imageBaseUrl``; null if unreadable. */
  paths: (string | null)[];
  references: (string | null)[];
}

export interface GroupOut {
  id: string;
  title: string;
  reference: string;
  plots: ComparedPlotOut[];
}

export interface SetSummaryOut {
  name: string;
  title: string;
  plotCount: number;
  missing: number;
}

export interface SetDetailOut extends SetSummaryOut {
  imageWidth: number | null;
  panels: Partial<Record<PanelView, PanelOut>>;
  groups: GroupOut[];
}

export interface CompareOut {
  runs: CompareRunOut[];
  sets: SetSummaryOut[];
  set: SetDetailOut | null;
}

export type PanelView = 'test' | 'ref' | 'diff';
