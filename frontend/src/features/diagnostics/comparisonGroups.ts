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

/**
 * Partition selections by a shared plot intersection, not tool metadata.
 *
 * Sends one compare request per run (every set in detail), not one per run
 * per set.
 */
export const loadComparisonGroups = async (
  client: QueryClient,
  runs: CompareRun[],
): Promise<ComparisonGroup[]> => {
  const catalogs = await Promise.all(
    runs.map(async (run) => {
      const read = (set: string | null, allSets = false) =>
        client.fetchQuery({
          queryKey: ['diagnostics', 'compare', [run], allSets ? 'all-sets' : set],
          queryFn: () => compareRuns([run], set, allSets),
          // A run that was partly read or unreadable may recover; ask again
          // after the backend's short partial cache instead of ten minutes.
          staleTime: (query) =>
            query.state.data?.runs.some((item) => item.error || item.partial)
              ? 30_000
              : 10 * 60_000,
          retry: false,
        });
      const summary = await read(null, true);
      const summaryAt = client.getQueryState([
        'diagnostics',
        'compare',
        [run],
        'all-sets',
      ])?.dataUpdatedAt;
      // Seed a per-set entry the compare view reads, unless a newer response
      // is already there, so opening a set after grouping does not ask again.
      const seed = (set: string | null, detail: SetDetailOut) => {
        const key = ['diagnostics', 'compare', [run], set];
        const existing = client.getQueryState(key)?.dataUpdatedAt ?? 0;
        if (existing >= (summaryAt ?? 0) && client.getQueryData(key)) return;
        client.setQueryData(
          key,
          { ...summary, set: detail, details: undefined },
          {
            updatedAt: summaryAt,
          },
        );
      };
      let details: SetDetailOut[];
      if (summary.details) {
        details = summary.details;
        details.forEach((detail) => seed(detail.name, detail));
        // The view asks for the default set as `null` on a link without one.
        if (summary.set) seed(null, summary.set);
      } else {
        // A backend that predates allSets omits details; read each set, and
        // keep those separately fetched responses as they are.
        details = (
          await Promise.all(
            summary.sets.map((set) => (set.name === summary.set?.name ? summary : read(set.name))),
          )
        ).flatMap((detail) => (detail.set ? [detail.set] : []));
      }
      const plots = new Set(
        summary.runs.some((item) => item.error)
          ? []
          : details.flatMap((detail) =>
              detail.groups.flatMap((group) =>
                group.plots.map((plot) => JSON.stringify([detail.name, plot.key])),
              ),
            ),
      );
      const tool = summary.runs[0]?.tool;
      const title =
        tool === 'mpas_analysis'
          ? 'MPAS-Analysis'
          : tool === 'e3sm_diags'
            ? `E3SM Diags${run.url.includes('model_vs_model') ? ' · Model vs. Model' : run.url.includes('model_vs_obs') ? ' · Model vs. Observations' : ''}`
            : 'Diagnostic sets';

      return {
        run,
        plots,
        title,
        details,
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
      if (group.title !== catalog.title) group.title = 'Compatible diagnostic sets';
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
