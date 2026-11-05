import { Link } from 'react-router-dom';

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
  describeSimulatedDuration,
  formatCaseDate,
  formatCaseHashLabel,
  formatSimulatedDuration,
  getConfigurationBaseline,
} from '@/features/catalog/caseUtils';
import { executionDetailsPath, type ReadableCaseIdentity } from '@/lib/catalog/urls';
import type {
  CaseDetailOut,
  CaseHashConfigurationOut,
  ConfigurationFieldOut,
  ConfigurationObservationOut,
  SimulationDurationOut,
} from '@/types';

// Keep technical metadata in expandable details; extraction belongs to #443.
const CONFIGURATION_FIELDS = [
  ['compset_alias', 'Compset Alias'],
  ['grid_alias', 'Grid Alias'],
  ['compset_long_name', 'Compset long name'],
  ['grid_long_name', 'Resolution'],
  ['source_code_path', 'Source code path'],
  ['git_commit_hash', 'Model hash'],
  ['git_tag', 'Model tag'],
] as const;

export const CaseConfigurationSummary = ({
  record,
  identity,
}: {
  record: CaseDetailOut;
  identity?: ReadableCaseIdentity;
}) => (
  <dl
    className="grid auto-rows-fr grid-cols-1 gap-x-6 gap-y-4 text-sm sm:grid-cols-2 lg:grid-cols-3"
    aria-label="Case summary"
  >
    <SummaryField label="Total Simulated Duration">
      <SimulatedDurationValue duration={record.simulatedDuration} />
    </SummaryField>
    <SummaryField label="Latest Execution">
      {record.latestExecution ? (
        <>
          <div title="Latest completed execution by run end, with run start fallback.">
            {record.latestExecution.runEndDate || record.latestExecution.runStartDate
              ? formatCaseDate(
                  record.latestExecution.runEndDate ?? record.latestExecution.runStartDate,
                )
              : 'Run date unavailable'}
          </div>
          {identity ? (
            <Link
              className="text-xs font-normal underline"
              to={executionDetailsPath({
                ...identity,
                executionId: record.latestExecution.executionId,
              })}
            >
              {record.latestExecution.executionId}
            </Link>
          ) : (
            <span className="text-xs font-normal">{record.latestExecution.executionId}</span>
          )}
        </>
      ) : (
        'Unavailable'
      )}
    </SummaryField>
    {CONFIGURATION_FIELDS.slice(0, 2).map(([field, label]) => (
      <SummaryField key={field} label={label}>
        <SharedConfigurationValue record={record} field={field} />
      </SummaryField>
    ))}
    <SummaryField label="Machine">{record.machineNames.join(', ') || 'Unavailable'}</SummaryField>
    <SummaryField label="HPC User">{record.hpcUsernames.join(', ') || 'Unavailable'}</SummaryField>
  </dl>
);

export const CaseConfigurationDetails = ({
  record,
  identity,
}: {
  record: CaseDetailOut;
  identity: ReadableCaseIdentity;
}) => {
  const groups = record.configurationGroups ?? [];
  if (groups.length === 0) return null;
  const baseline = getConfigurationBaseline(groups);
  const orderedGroups = baseline
    ? [baseline, ...groups.filter((group) => group !== baseline)]
    : groups;
  const differingFields = CONFIGURATION_FIELDS.filter(
    ([field]) =>
      new Set(groups.map((group) => group.configuration[field]?.source?.value ?? null)).size > 1,
  );

  return (
    <section className="min-w-0 border-t border-slate-200 pt-3" data-case-configuration>
      <h3 className="text-sm font-semibold">
        {groups.length === 1 ? 'Case Configuration' : 'Configuration Differences'}
      </h3>
      {groups.length > 1 ? (
        <p className="mt-1 text-xs text-muted-foreground">
          {baseline
            ? 'Baseline: most executions; hash breaks ties. '
            : 'No known case hash to use as baseline. '}
          Only changed configuration values appear below. Expand a row for full metadata and
          execution sources.
        </p>
      ) : null}
      <div className="mt-2 divide-y divide-slate-200">
        {orderedGroups.map((group) => {
          const isBaseline = groups.length > 1 && group === baseline;
          const changes = differingFields.filter(
            ([field]) =>
              isBaseline ||
              !baseline ||
              (group.configuration[field]?.source?.value ?? null) !==
                (baseline.configuration[field]?.source?.value ?? null),
          );
          const hasInternalChanges = CONFIGURATION_FIELDS.some(
            ([field]) => group.configuration[field]?.differences.length,
          );

          return (
            <details key={group.key} className="min-w-0 py-3" data-configuration-group>
              <summary className="grid cursor-pointer grid-cols-2 items-start gap-x-4 gap-y-2 text-sm lg:grid-cols-[minmax(0,1fr)_6rem_12rem_minmax(0,2fr)]">
                <span className="col-span-2 min-w-0 break-words lg:col-span-1">
                  <span className="block text-xs text-muted-foreground">Case Hash</span>
                  <span className="font-mono font-semibold" title={groupLabel(group)}>
                    {group.caseHash ? formatCaseHashLabel(group.caseHash) : groupLabel(group)}
                  </span>
                  {isBaseline ? <span className="ml-2 text-xs font-medium">Baseline</span> : null}
                  <span className="block text-xs text-muted-foreground">Expand metadata</span>
                </span>
                <span>
                  <span className="block text-xs text-muted-foreground">Executions</span>
                  <span className="font-semibold">{group.executionIds.length}</span>
                </span>
                <span>
                  <span className="block text-xs text-muted-foreground">Simulated Duration</span>
                  <span className="font-semibold">
                    <SimulatedDurationValue
                      duration={group.simulatedDuration}
                      withTooltip={false}
                    />
                  </span>
                </span>
                <span
                  className="col-span-2 min-w-0 space-y-1 [overflow-wrap:anywhere] lg:col-span-1"
                  data-configuration-differences
                >
                  {changes.map(([field, label]) => (
                    <span key={field} className="block">
                      <span className="text-xs text-muted-foreground">{label}: </span>
                      {group.configuration[field]?.source?.value ?? 'Unavailable'}
                    </span>
                  ))}
                  {groups.length > 1 && changes.length === 0 ? (
                    <span className="text-xs text-muted-foreground">
                      {isBaseline
                        ? 'No configuration differences'
                        : baseline
                          ? 'Same as baseline'
                          : 'No configuration differences'}
                    </span>
                  ) : null}
                  {hasInternalChanges ? (
                    <span className="block text-xs text-muted-foreground">
                      Changes within Case Hash
                    </span>
                  ) : null}
                </span>
              </summary>
              <div className="mt-3 space-y-3">
                <p className="break-all text-xs">Full Case Hash: {groupLabel(group)}</p>
                <p className="text-xs text-muted-foreground">
                  {describeSimulatedDuration(group.simulatedDuration)}
                </p>
                <p className="text-xs text-muted-foreground">
                  Configuration uses the earliest available value per field, ordered by run start
                  with run end fallback. Undated executions sort last; execution IDs break ties.
                  Values may come from different executions.
                </p>
                <dl className="grid min-w-0 gap-4 sm:grid-cols-2">
                  {CONFIGURATION_FIELDS.map(([field, label]) => (
                    <div key={field} className="min-w-0">
                      <dt className="mb-1 text-xs font-medium text-slate-500">{label}</dt>
                      <dd>
                        <ConfigurationValue
                          field={group.configuration[field]}
                          identity={identity}
                        />
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );
};

const SummaryField = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="min-w-0 space-y-1">
    <dt className="text-xs font-medium text-slate-500">{label}</dt>
    <dd className="text-sm font-semibold text-slate-950 [overflow-wrap:anywhere]">{children}</dd>
  </div>
);

const SharedConfigurationValue = ({ record, field }: { record: CaseDetailOut; field: string }) => {
  const summary = record.sharedConfiguration?.[field];

  return (
    <>
      {summary?.varies ? 'Varies by Case Hash' : (summary?.value ?? 'Unavailable')}
      {summary?.incomplete && (summary.value != null || summary.varies) ? (
        <span className="block text-xs font-normal text-muted-foreground">
          Some executions unavailable
        </span>
      ) : null}
      {summary?.hasDifferences ? (
        <span className="block text-xs font-normal text-muted-foreground">
          Changes within Case Hash
        </span>
      ) : null}
    </>
  );
};

const SimulatedDurationValue = ({
  duration,
  withTooltip = true,
}: {
  duration?: SimulationDurationOut;
  withTooltip?: boolean;
}) => {
  const value = (
    <span tabIndex={withTooltip ? 0 : undefined} className="inline-block">
      {formatSimulatedDuration(duration)}
      {duration?.calendarAssumed ? (
        <span className="block text-xs font-normal text-muted-foreground">
          Gregorian calendar assumed
        </span>
      ) : null}
      {(duration?.calendars.length ?? 0) > 1 ? (
        <span className="block text-xs font-normal text-muted-foreground">Mixed calendars</span>
      ) : null}
    </span>
  );
  if (!withTooltip) return value;

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>{value}</TooltipTrigger>
        <TooltipContent className="max-w-sm">{describeSimulatedDuration(duration)}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

const groupLabel = (group: CaseHashConfigurationOut) =>
  group.caseHash ?? `Missing Case Hash: ${group.executionIds[0]}`;

const ConfigurationValue = ({
  field,
  identity,
}: {
  field?: ConfigurationFieldOut;
  identity: ReadableCaseIdentity;
}) => (
  <div className="space-y-1 text-sm [overflow-wrap:anywhere]">
    {field?.source ? (
      <Observation observation={field.source} identity={identity} />
    ) : (
      <span>Unavailable</span>
    )}
    {field?.differences.length ? (
      <details>
        <summary className="cursor-pointer text-xs text-muted-foreground">
          Other observed values ({field.differences.length})
        </summary>
        <ul className="mt-1 space-y-2">
          {field.differences.map((observation) => (
            <li key={observation.executionUuid}>
              <Observation observation={observation} identity={identity} />
            </li>
          ))}
        </ul>
      </details>
    ) : null}
    {field?.missingExecutionIds.length ? (
      <details>
        <summary className="cursor-pointer text-xs text-muted-foreground">
          Unavailable in {field.missingExecutionIds.length} execution(s)
        </summary>
        <ul className="mt-1 space-y-1 text-xs">
          {field.missingExecutionIds.map((executionId) => (
            <li key={executionId}>
              <Link className="underline" to={executionDetailsPath({ ...identity, executionId })}>
                {executionId}
              </Link>
            </li>
          ))}
        </ul>
      </details>
    ) : null}
  </div>
);

const Observation = ({
  observation,
  identity,
}: {
  observation: ConfigurationObservationOut;
  identity: ReadableCaseIdentity;
}) => (
  <div>
    <div>{observation.value}</div>
    <div className="text-xs text-muted-foreground">
      <Link
        className="underline"
        to={executionDetailsPath({ ...identity, executionId: observation.executionId })}
      >
        {observation.executionId}
      </Link>
      {' · '}
      {observation.runDate ? formatCaseDate(observation.runDate) : 'Run date unavailable'}
    </div>
  </div>
);
