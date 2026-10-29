import { api } from '@/api/api';
import type { CaseDiagnosticsOut, CompareOut } from '@/features/diagnostics/types';

// Both calls read the public archives on a cache miss, which can take a few
// seconds per run; allow longer than the default timeout.
const ARCHIVE_TIMEOUT_MS = 60_000;

export const getCaseDiagnosticsRuns = async (caseId: string): Promise<CaseDiagnosticsOut> =>
  (
    await api.get<CaseDiagnosticsOut>(`/cases/${caseId}/diagnostics/runs`, {
      timeout: ARCHIVE_TIMEOUT_MS,
    })
  ).data;

export const compareRuns = async (
  runs: { url: string; label: string }[],
  set: string | null,
): Promise<CompareOut> =>
  (
    await api.post<CompareOut>(
      '/diagnostics/compare',
      { runs, set },
      { timeout: ARCHIVE_TIMEOUT_MS },
    )
  ).data;
