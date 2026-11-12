import type { QueryClient } from '@tanstack/react-query';

import { compareRuns } from '@/features/diagnostics/api';
import { type CompareRun, displayLabel } from '@/features/diagnostics/compareState';

/** Use the viewer's plot intersection before opening any comparison entry point. */
export const validateComparison = async (
  client: QueryClient,
  runs: CompareRun[],
  set: string | null = null,
): Promise<{ problem: string; retryable: boolean } | null> => {
  const result = await client.fetchQuery({
    queryKey: ['diagnostics', 'compare', runs, set],
    queryFn: () => compareRuns(runs, set),
    staleTime: 0,
    retry: false,
  });
  const failed = result.runs.filter((run) => run.error);
  if (failed.length || (!result.sets.length && result.runs.some((run) => run.partial))) {
    return {
      problem: failed.length
        ? `Could not read diagnostics for ${failed.map(displayLabel).join(', ')}. Retry the compatibility check.`
        : 'Some plots could not be read, so compatibility could not be confirmed. Try again.',
      retryable: true,
    };
  }
  if (!result.sets.length) {
    return {
      problem: 'Selected runs have no plots in common. Choose compatible runs.',
      retryable: false,
    };
  }
  // Reuse this response when the viewer resolves its category in the URL.
  if (result.set) client.setQueryData(['diagnostics', 'compare', runs, result.set.name], result);

  return null;
};
