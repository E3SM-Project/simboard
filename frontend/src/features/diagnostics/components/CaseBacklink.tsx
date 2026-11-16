import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';

import { getCaseById } from '@/api/catalog';
import { Button } from '@/components/ui/button';
import type { BasketEntry } from '@/features/diagnostics/compareState';
import { diagnosticsId } from '@/features/diagnostics/discoveryState';
import { caseDetailsPath } from '@/lib/catalog/urls';

/** Older persisted selections have an ID but no readable case address. */
export const CaseBacklink = ({ entry }: { entry: BasketEntry }) => {
  const query = useQuery({
    queryKey: ['case', entry.caseId],
    queryFn: () => getCaseById(entry.caseId),
    enabled: !entry.casePath,
    staleTime: 10 * 60_000,
  });
  const record = query.data;
  const path =
    entry.casePath ??
    (record?.machineNames.length === 1 && record.hpcUsernames.length === 1
      ? caseDetailsPath({
          machineName: record.machineNames[0],
          hpcUsername: record.hpcUsernames[0],
          caseName: record.name,
        })
      : null);
  if (!path) return null;

  return (
    <Button asChild size="sm" variant="ghost" className="h-7 shrink-0 px-2 text-xs">
      <Link
        to={`${path}#${diagnosticsId(entry.caseId)}`}
        aria-label={`View Case ${entry.caseName}`}
      >
        View Case
      </Link>
    </Button>
  );
};
