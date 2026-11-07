import type { QueryClient } from '@tanstack/react-query';

import { compareRuns } from '@/features/diagnostics/api';
import { type CompareRun, MAX_COMPARED_RUNS } from '@/features/diagnostics/compareState';
import type { SetDetailOut } from '@/features/diagnostics/types';

export interface ComparisonGroup {
  id: string;
  title: string;
  runs: CompareRun[];
  plots: Set<string>;
  details: SetDetailOut[];
}

export const comparisonGroupId = (runs: CompareRun[]) =>
  JSON.stringify(runs.map((run) => [run.url, run.label]).sort());

/** Partition selections by a shared plot intersection, not tool metadata. */
export const loadComparisonGroups = async (
  client: QueryClient,
  runs: CompareRun[],
): Promise<ComparisonGroup[]> => {
  const catalogs = await Promise.all(
    runs.map(async (run) => {
      const read = (set: string | null) =>
        client.fetchQuery({
          queryKey: ['diagnostics', 'compare', [run], set],
          queryFn: () => compareRuns([run], set),
          staleTime: 10 * 60_000,
          retry: false,
        });
      const summary = await read(null);
      const details = await Promise.all(
        summary.sets.map((set) => (set.name === summary.set?.name ? summary : read(set.name))),
      );
      const plots = new Set(
        summary.runs.some((item) => item.error)
          ? []
          : details.flatMap(
              (detail) =>
                detail.set?.groups.flatMap((group) =>
                  group.plots.map((plot) => JSON.stringify([detail.set?.name, plot.key])),
                ) ?? [],
            ),
      );
      const tool = summary.runs[0]?.tool;
      const title =
        tool === 'mpas_analysis'
          ? 'MPAS-Analysis'
          : tool === 'e3sm_diags'
            ? `E3SM Diags${run.url.includes('model_vs_model') ? ' · Model vs. Model' : run.url.includes('model_vs_obs') ? ' · Model vs. Observations' : ''}`
            : 'Diagnostic runs';

      return {
        run,
        plots,
        title,
        details: details.flatMap((detail) => (detail.set ? [detail.set] : [])),
      };
    }),
  );
  const groups: ComparisonGroup[] = [];
  for (const catalog of catalogs) {
    const group = groups.find(
      (item) =>
        item.runs.length < MAX_COMPARED_RUNS &&
        [...item.plots].some((key) => catalog.plots.has(key)),
    );
    if (group) {
      group.runs.push(catalog.run);
      group.plots = new Set([...group.plots].filter((key) => catalog.plots.has(key)));
      group.id = comparisonGroupId(group.runs);
      if (group.title !== catalog.title) group.title = 'Compatible diagnostic runs';
    } else {
      groups.push({
        id: comparisonGroupId([catalog.run]),
        title: catalog.title,
        runs: [catalog.run],
        plots: catalog.plots,
        details: catalog.details,
      });
    }
  }

  return groups;
};
