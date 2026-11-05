import { Info } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  EXECUTION_METADATA_FIELDS,
  type ExecutionCandidate,
  getExecutionDiscoveryContext,
  getExecutionSummary,
  knownExecutionValue,
  MISSING_CASE_HASH_LABEL,
} from '@/lib/catalog/executionDiscovery';

export const ExecutionMetadataDetails = ({
  candidate,
  discovery,
}: {
  candidate: ExecutionCandidate;
  discovery: ReturnType<typeof getExecutionDiscoveryContext>;
}) => {
  const summary = getExecutionSummary(candidate, discovery);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0 text-muted-foreground"
          aria-label={`Execution details for ${summary.executionId}`}
          title="Execution details"
        >
          <Info className="h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="max-h-80 w-80 max-w-[calc(100vw-2rem)] overflow-y-auto text-xs data-[state=closed]:!animate-none"
        aria-label={`Details for ${summary.executionId}`}
      >
        <p className="break-all font-mono font-medium">{summary.executionId}</p>
        <p className="mt-2">Simulation: {summary.simulationPeriod}</p>
        <dl className="mt-1 space-y-1">
          {candidate.summary.caseHash || discovery.showCaseHash ? (
            <div>
              <dt className="inline font-medium">Case Hash: </dt>
              <dd className="inline break-all">
                {candidate.summary.caseHash ?? MISSING_CASE_HASH_LABEL}
              </dd>
            </div>
          ) : null}
          {EXECUTION_METADATA_FIELDS.map(([key, label]) => (
            <div key={key}>
              <dt className="inline font-medium">{label}: </dt>
              <dd className="inline break-words">
                {knownExecutionValue(candidate.details?.[key]) ?? '—'}
              </dd>
            </div>
          ))}
          <div>
            <dt className="inline font-medium">Compset Long Name: </dt>
            <dd className="inline break-words">
              {knownExecutionValue(candidate.details?.compsetLongName) ?? '—'}
            </dd>
          </div>
          <div>
            <dt className="inline font-medium">Grid Long Name: </dt>
            <dd className="inline break-words">
              {knownExecutionValue(candidate.details?.gridLongName) ?? '—'}
            </dd>
          </div>
        </dl>
      </PopoverContent>
    </Popover>
  );
};
