/**
 * Build links into IICE, the Interface for Inter-Comparison of E3SM diagnostics.
 *
 * IICE (https://portal.nersc.gov/project/e3sm/iice/) renders the same
 * e3sm_diags or mpas-analysis plot from several cases side by side. It is a
 * CGI form, not a static viewer: the shareable link is the form action plus a
 * query string of `urlN`/`labelN` pairs, which is exactly what its own
 * "Copy Link" button produces (see `viewer/js/form_ctrl.js` `copycmplink()`).
 *
 * Nothing here talks to the network. Given the viewer URLs SimBoard already
 * knows about, this module produces the IICE link a user would otherwise have
 * to assemble by hand.
 *
 * Contract observed 2026-10-19 against the live tool:
 *
 *   e3sm_diags:     /project/m2136/bin/iice/iice.cgi
 *                   dconfig=vsObs | vsModel
 *   mpas-analysis:  /project/m2136/bin/iice/mpas-a.cgi
 *                   dconfig=wcycl | cryo
 *
 *   url1..urlN      viewer directory per case
 *   label1..labelN  display label; `!refCase label` tags a model_vs_model
 *                   reference case name so IICE can resolve image filenames
 *   category        '' (index) | a set name | 'display' (one plot)
 *   plot            relative image path under the viewer root
 *   diff            0 total fields | 1 difference plots
 *
 * IICE itself only escapes spaces (`copycmplink()` does `replace(/ /g,'%20')`)
 * and its CGI reads the raw query, so this builder deliberately mirrors that
 * rather than fully URL-encoding, which the CGI does not decode.
 */

export const IICE_ORIGIN = 'https://portal.nersc.gov';

export const IICE_ENTRANCE_URL = `${IICE_ORIGIN}/project/e3sm/iice/`;

const IICE_E3SM_DIAGS_CGI = `${IICE_ORIGIN}/project/m2136/bin/iice/iice.cgi`;
const IICE_MPAS_ANALYSIS_CGI = `${IICE_ORIGIN}/project/m2136/bin/iice/mpas-a.cgi`;

export type IiceTool = 'e3sm_diags' | 'mpas_analysis';

export type IiceComparison = 'model_vs_obs' | 'model_vs_model';

/** One case's contribution to a comparison. */
export interface IiceEntry {
  /** e3sm_diags `viewer/` directory or mpas-analysis run directory. */
  url: string;
  /** Shown over the plot; usually the case name plus period. */
  label: string;
  /**
   * For model_vs_model e3sm_diags runs only: the reference case name. IICE
   * cannot resolve those image filenames without it and encodes it as a
   * `!refCase ` prefix on the label.
   */
  referenceCase?: string;
}

export interface IiceLinkOptions {
  tool: IiceTool;
  entries: IiceEntry[];
  /**
   * e3sm_diags: which viewer template to drive the comparison with. Defaults
   * to `vsModel` when any entry carries a reference case, else `vsObs`.
   * mpas-analysis: `wcycl` (coupled) or `cryo`; defaults to `wcycl`.
   */
  dconfig?: 'vsObs' | 'vsModel' | 'wcycl' | 'cryo';
  /** Deep-link straight to one plot set or image. */
  category?: string;
  plot?: string;
  diff?: 0 | 1;
}

export interface IiceLinkProblem {
  code: 'too_few_entries' | 'mixed_comparison_modes';
  message: string;
}

/**
 * Normalise a viewer URL to what IICE expects: no trailing slash.
 *
 * IICE joins `urlN + '/../' + plot`, so a trailing slash yields a double slash
 * that some servers reject. Its own entrance page examples omit it.
 */
export const normalizeIiceViewerUrl = (url: string): string => url.trim().replace(/\/+$/, '');

/** Sanitise a label the way IICE tolerates it: one line, no `&`, single spaces. */
const cleanLabel = (label: string): string =>
  label
    .replace(/[\r\n&]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const encodeIiceValue = (value: string): string => value.replace(/ /g, '%20');

/**
 * Render the label IICE should see, including the `!refCase ` prefix when a
 * reference case is supplied.
 */
export const formatIiceLabel = (entry: IiceEntry): string => {
  const base = cleanLabel(entry.label);
  // The reference case is free text and is prefixed into the same query
  // parameter, so it needs the same cleaning as the label: an unescaped `&`
  // would otherwise let it append parameters to a link meant for sharing.
  const reference = cleanLabel(entry.referenceCase ?? '');

  return reference ? `!${reference} ${base}`.trim() : base;
};

/**
 * Check whether `options` can produce a comparison IICE will render.
 *
 * Returns an empty array when everything is fine. Problems are advisory for
 * the UI; `buildIiceLink` will still produce a link when it can.
 */
export const validateIiceLink = (options: IiceLinkOptions): IiceLinkProblem[] => {
  const problems: IiceLinkProblem[] = [];

  if (options.entries.length < 2) {
    problems.push({
      code: 'too_few_entries',
      message: 'IICE compares two or more diagnostics sets; add at least one more case.',
    });
  }

  // One comparison is driven by one IICE template, so a model-vs-observations
  // run and a model-vs-model run cannot be rendered together.
  const modes = new Set(
    options.entries.map((entry) => (entry.referenceCase?.trim() ? 'model' : 'obs')),
  );
  if (modes.size > 1) {
    problems.push({
      code: 'mixed_comparison_modes',
      message:
        'IICE cannot render model-vs-observations and model-vs-model runs together; compare them separately.',
    });
  }

  return problems;
};

/**
 * Build a shareable IICE comparison link.
 *
 * Returns `null` when there is nothing to compare (no entries). With a single
 * entry it still returns a link, which opens IICE pre-filled so the user can
 * add more cases there.
 */
export const buildIiceLink = (options: IiceLinkOptions): string | null => {
  const entries = options.entries.filter((entry) => entry.url.trim().length > 0);
  if (entries.length === 0) {
    return null;
  }

  const cgi = options.tool === 'mpas_analysis' ? IICE_MPAS_ANALYSIS_CGI : IICE_E3SM_DIAGS_CGI;
  const params: string[] = [];

  entries.forEach((entry, index) => {
    const n = index + 1;
    params.push(`url${n}=${encodeIiceValue(normalizeIiceViewerUrl(entry.url))}`);
    params.push(`label${n}=${encodeIiceValue(formatIiceLabel(entry))}`);
  });

  if (options.category !== undefined) {
    params.push(`category=${encodeIiceValue(options.category)}`);
  }
  if (options.plot !== undefined) {
    params.push(`plot=${encodeIiceValue(options.plot)}`);
  }
  if (options.diff !== undefined) {
    params.push(`diff=${options.diff}`);
  }

  params.push(`dconfig=${resolveDconfig(options, entries)}`);

  return `${cgi}?${params.join('&')}`;
};

const resolveDconfig = (options: IiceLinkOptions, entries: IiceEntry[]): string => {
  if (options.dconfig) {
    return options.dconfig;
  }
  if (options.tool === 'mpas_analysis') {
    return 'wcycl';
  }

  return entries.some((entry) => entry.referenceCase?.trim()) ? 'vsModel' : 'vsObs';
};

/**
 * Suggest a default label for a discovered viewer: case name plus period, so
 * that two periods of the same case stay distinguishable in IICE.
 */
export const suggestIiceLabel = (
  caseName: string,
  period?: { startYear: number | null; endYear: number | null },
): string => {
  if (!period || period.startYear == null || period.endYear == null) {
    return caseName;
  }
  const pad = (year: number) => String(year).padStart(4, '0');
  return `${caseName} ${pad(period.startYear)}-${pad(period.endYear)}`;
};
