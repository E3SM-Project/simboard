import { Link } from 'react-router-dom';

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import {
  CASE_CONFIGURATION_FIELDS as CONFIGURATION_FIELDS,
  type CaseHashConfigurationDifference,
  describeSimulatedDuration,
  formatCaseDate,
  formatCaseHashLabel,
  formatSimulatedDuration,
  getConfigurationBaseline,
  getConfigurationDiffParts,
} from '@/features/catalog/caseUtils';
import { executionDetailsPath, type ReadableCaseIdentity } from '@/lib/catalog/urls';
import type {
  CaseDetailOut,
  CaseHashConfigurationOut,
  ConfigurationFieldOut,
  ConfigurationObservationOut,
  SimulationDurationOut,
} from '@/types';

// Compare stored technical metadata only; extraction belongs to #443.

export const CaseConfigurationSummary = ({
  record,
  identity,
}: {
  record: CaseDetailOut;
  identity?: ReadableCaseIdentity;
}) => (
  <dl
    className="grid grid-cols-1 gap-x-6 gap-y-4 text-sm sm:grid-cols-2 lg:grid-cols-4"
    aria-label="Case summary"
  >
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
              className="text-[13px] underline"
              to={executionDetailsPath({
                ...identity,
                executionId: record.latestExecution.executionId,
              })}
            >
              {record.latestExecution.executionId}
            </Link>
          ) : (
            <span className="text-[13px]">{record.latestExecution.executionId}</span>
          )}
        </>
      ) : (
        'Unavailable'
      )}
    </SummaryField>
    <SummaryField label="Total Simulated Duration">
      <SimulatedDurationValue duration={record.simulatedDuration} />
    </SummaryField>
    <SummaryField label="Machine">{record.machineNames.join(', ') || 'Unavailable'}</SummaryField>
    <SummaryField label="HPC Username">
      {record.hpcUsernames.join(', ') || 'Unavailable'}
    </SummaryField>
    {CONFIGURATION_FIELDS.slice(0, 4).map(([field, label]) => (
      <SummaryField key={field} label={label}>
        <SharedConfigurationValue record={record} field={field} identity={identity} />
      </SummaryField>
    ))}
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
  const baseline = getConfigurationBaseline(groups);
  const orderedGroups = baseline
    ? [baseline, ...groups.filter((group) => group !== baseline)]
    : groups;
  const differingFields = CONFIGURATION_FIELDS.filter(([field]) =>
    configurationFieldDiffers(record, field),
  );
  if (groups.length < 2 || differingFields.length === 0) return null;
  const reference = orderedGroups[0];

  return (
    <details
      id="case-configuration-differences"
      tabIndex={-1}
      aria-labelledby="case-configuration-differences-title"
      className="min-w-0 border-t border-border pt-3"
      data-case-configuration
    >
      <summary className="cursor-pointer">
        <h3 id="case-configuration-differences-title" className="inline text-sm font-semibold">
          Configuration Differences
        </h3>
      </summary>
      <p className="mt-1 text-xs text-muted-foreground">
        Case hashes identify CIME case instances. Different hashes usually mean the case was
        recreated or cloned. Only configuration fields that differ between case hashes are shown.
      </p>
      <div className="mt-2" data-configuration-differences>
        <Table
          className="table-fixed"
          style={{ minWidth: `${160 + orderedGroups.length * 224}px` }}
        >
          <TableHeader>
            <TableRow>
              <TableHead scope="col" className="sticky left-0 z-10 w-40 bg-card align-top">
                Field
              </TableHead>
              {orderedGroups.map((group) => (
                <TableHead
                  key={group.key}
                  scope="col"
                  className="w-56 py-2 align-top [overflow-wrap:anywhere]"
                >
                  <span
                    className="font-mono text-xs font-semibold text-foreground"
                    title={groupLabel(group)}
                  >
                    {group.caseHash ? formatCaseHashLabel(group.caseHash) : groupLabel(group)}
                  </span>
                  {group === reference ? (
                    <span className="ml-2 text-xs font-medium">Reference</span>
                  ) : null}
                  <span className="mt-1 block text-xs font-normal">
                    {group.executionIds.length}{' '}
                    {group.executionIds.length === 1 ? 'execution' : 'executions'}
                  </span>
                  <span className="block text-xs font-normal">
                    <SimulatedDurationValue
                      duration={group.simulatedDuration}
                      showCalendarNotes={false}
                    />
                  </span>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {differingFields.map(([field, label]) => (
              <TableRow
                key={field}
                className="[&:focus-within>td]:bg-sky-50 [&:focus-within>th]:bg-sky-50 [&:focus-within>th]:text-sky-900"
              >
                <TableHead
                  scope="row"
                  id={configurationFieldId(field)}
                  tabIndex={-1}
                  className="sticky left-0 z-10 scroll-mt-24 bg-card py-2 align-top text-xs font-medium text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                >
                  {label}
                </TableHead>
                {orderedGroups.map((group) => (
                  <TableCell key={group.key} className="align-top">
                    <ConfigurationValue
                      field={group.configuration[field]}
                      identity={identity}
                      referenceValue={
                        group === reference
                          ? undefined
                          : (reference.configuration[field]?.source?.value ?? null)
                      }
                    />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </details>
  );
};

export const CaseHashConfigurationDifferences = ({
  differences,
}: {
  differences: CaseHashConfigurationDifference[];
}) => {
  if (differences.length === 0) return null;

  return (
    <dl
      className="mt-2 space-y-1 text-xs text-muted-foreground"
      aria-label="Configuration differences"
    >
      {differences.map((difference) => (
        <div key={difference.field} className="min-w-0">
          <dt className="font-medium">{difference.label}</dt>
          <TooltipProvider delayDuration={150}>
            <Tooltip>
              <TooltipTrigger asChild>
                <dd className="flex min-w-0 items-center gap-1" tabIndex={0}>
                  <span className="sr-only">Baseline value: </span>
                  <span className="min-w-0 flex-1 truncate">{difference.baselineValue}</span>
                  <span aria-hidden="true" className="shrink-0">
                    →
                  </span>
                  <span className="sr-only">This group&apos;s value: </span>
                  <mark className="min-w-0 flex-1 truncate rounded-sm bg-amber-100 font-medium text-amber-950">
                    {difference.value}
                  </mark>
                </dd>
              </TooltipTrigger>
              <TooltipContent className="max-w-sm break-all text-xs">
                <p>
                  Baseline ({formatCaseHashLabel(difference.baselineHash)}):{' '}
                  {difference.baselineValue}
                </p>
                <p>This group&apos;s value: {difference.value}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      ))}
    </dl>
  );
};

const SummaryField = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="min-w-0 space-y-1">
    <dt className="text-[13px] font-semibold leading-4 text-muted-foreground">{label}</dt>
    <dd className="text-sm font-normal leading-5 text-foreground [overflow-wrap:anywhere]">
      {children}
    </dd>
  </div>
);

const SharedConfigurationValue = ({
  record,
  field,
  identity,
}: {
  record: CaseDetailOut;
  field: string;
  identity?: ReadableCaseIdentity;
}) => {
  const summary = record.sharedConfiguration?.[field];
  const differs = configurationFieldDiffers(record, field);
  const groups = record.configurationGroups ?? [];
  const source = groups.find((group) => group.configuration[field]?.source)?.configuration[field]
    ?.source;
  const value = summary?.value ?? source?.value ?? 'Unavailable';
  const changingGroups = groups.filter((group) => group.configuration[field]?.differences.length);

  return (
    <>
      {differs ? (
        record.configurationGroups?.length ? (
          <a
            href="#case-configuration-differences"
            aria-controls={configurationFieldId(field)}
            className="underline underline-offset-2"
            onClick={(event) => {
              if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
              const section = document.getElementById('case-configuration-differences');
              if (!section) return;
              event.preventDefault();
              if (section instanceof HTMLDetailsElement) section.open = true;
              const rowLabel = document.getElementById(configurationFieldId(field));
              (rowLabel ?? section).focus({ preventScroll: true });
              const target =
                section.getBoundingClientRect().height < window.innerHeight
                  ? section
                  : (section.querySelector('h3') ?? section);
              target.scrollIntoView({ block: 'center', inline: 'nearest' });
            }}
          >
            Differs by case hash
          </a>
        ) : (
          'Differs by case hash'
        )
      ) : source && identity ? (
        <Link
          className="hover:underline"
          title={`Source execution: ${source.executionId}`}
          to={executionDetailsPath({ ...identity, executionId: source.executionId })}
        >
          {value}
        </Link>
      ) : (
        value
      )}
      {summary?.incomplete && (summary.value != null || differs) ? (
        <span className="block text-xs font-normal text-muted-foreground">
          Some executions unavailable
        </span>
      ) : null}
      {!differs && identity && changingGroups.length > 0 ? (
        <details className="text-xs font-normal text-muted-foreground">
          <summary className="cursor-pointer">Changes within Case Hash</summary>
          <ul className="mt-1 space-y-2">
            {changingGroups.flatMap((group) =>
              group.configuration[field].differences.map((observation) => (
                <li key={`${group.key}:${observation.executionUuid}`}>
                  <span className="font-mono">
                    {group.caseHash ? formatCaseHashLabel(group.caseHash) : groupLabel(group)}
                  </span>
                  <Observation observation={observation} identity={identity} />
                </li>
              )),
            )}
          </ul>
        </details>
      ) : summary?.hasDifferences ? (
        <span className="block text-xs font-normal text-muted-foreground">
          Changes within Case Hash
        </span>
      ) : null}
    </>
  );
};

const configurationFieldDiffers = (record: CaseDetailOut, field: string) =>
  record.configurationGroups?.length
    ? new Set(
        record.configurationGroups.map(
          (group) => group.configuration[field]?.source?.value ?? null,
        ),
      ).size > 1
    : Boolean(record.sharedConfiguration?.[field]?.varies);

const configurationFieldId = (field: string) => `case-configuration-${field}`;

const SimulatedDurationValue = ({
  duration,
  showCalendarNotes = true,
}: {
  duration?: SimulationDurationOut;
  showCalendarNotes?: boolean;
}) => {
  const value = (
    <span
      tabIndex={0}
      className="inline-block"
      aria-label={`Simulated duration: ${formatSimulatedDuration(duration)}`}
    >
      {formatSimulatedDuration(duration)}
      {showCalendarNotes && duration?.calendarAssumed ? (
        <span className="block text-xs font-normal text-muted-foreground">
          Gregorian calendar assumed
        </span>
      ) : null}
      {showCalendarNotes && (duration?.calendars.length ?? 0) > 1 ? (
        <span className="block text-xs font-normal text-muted-foreground">Mixed calendars</span>
      ) : null}
    </span>
  );

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
  referenceValue,
}: {
  field?: ConfigurationFieldOut;
  identity: ReadableCaseIdentity;
  referenceValue?: string | null;
}) => (
  <div className="space-y-1 text-sm [overflow-wrap:anywhere]">
    {field?.source ? (
      <Observation observation={field.source} identity={identity} referenceValue={referenceValue} />
    ) : referenceValue != null ? (
      <span>
        <span className="sr-only select-none">Reference value available; this value is </span>
        <mark className="rounded-sm bg-amber-100 font-medium text-amber-950">Unavailable</mark>
      </span>
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
              <Observation
                observation={observation}
                identity={identity}
                referenceValue={referenceValue}
              />
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
  referenceValue,
}: {
  observation: ConfigurationObservationOut;
  identity: ReadableCaseIdentity;
  referenceValue?: string | null;
}) => {
  const parts =
    referenceValue === undefined
      ? [{ text: observation.value, changed: false }]
      : getConfigurationDiffParts(observation.value, referenceValue);

  return (
    <div>
      {parts.some((part) => part.changed) ? (
        <span className="sr-only select-none">Differs from reference column. </span>
      ) : null}
      <div
        title={
          referenceValue === undefined
            ? undefined
            : `Reference value: ${referenceValue ?? 'Unavailable'}`
        }
      >
        {parts.map((part, index) =>
          part.changed ? (
            <mark key={index} className="rounded-sm bg-amber-100 font-medium text-amber-950">
              {part.text}
            </mark>
          ) : (
            <span key={index}>{part.text}</span>
          ),
        )}
      </div>
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
};
