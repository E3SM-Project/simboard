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
  const varying = discovery.varyingFields;

  return (
    <details className="max-w-64 whitespace-normal text-xs text-slate-500">
      <summary className="cursor-pointer rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        Details{summary.metadata ? ' · Varies' : ''}
      </summary>
      <p className="mt-2">Simulation: {summary.simulationPeriod}</p>
      <dl className="mt-1 space-y-1">
        {discovery.showCaseHash ? (
          <div>
            <dt className="inline font-medium">Case Hash: </dt>
            <dd className="inline break-all">
              {candidate.summary.caseHash ?? MISSING_CASE_HASH_LABEL}
            </dd>
          </div>
        ) : null}
        {EXECUTION_METADATA_FIELDS.map(([key, label]) => (
          <div key={key}>
            <dt className="inline font-medium">
              {label}
              {varying.includes(key) && knownExecutionValue(candidate.details?.[key])
                ? ' (varies)'
                : ''}
              :{' '}
            </dt>
            <dd className="inline break-words">
              {knownExecutionValue(candidate.details?.[key]) ?? '—'}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
};
