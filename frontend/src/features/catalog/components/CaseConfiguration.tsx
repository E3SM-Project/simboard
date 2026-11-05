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

// Compare stored technical metadata only; extraction belongs to #443.
const CONFIGURATION_FIELDS = [
  ['compset_alias', 'Compset Alias'],
  ['compset_long_name', 'Compset Long Name'],
  ['grid_alias', 'Grid Alias'],
  ['grid_long_name', 'Grid Long Name'],
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

  return (
    <section
      id="case-configuration-differences"
      tabIndex={-1}
      aria-labelledby="case-configuration-differences-title"
      className="min-w-0 border-t border-slate-200 pt-3"
      data-case-configuration
    >
      <h3 id="case-configuration-differences-title" className="text-sm font-semibold">
        Configuration Differences
      </h3>
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
              <TableHead scope="col" className="sticky left-0 z-10 w-40 bg-white align-top">
                Field
              </TableHead>
              {orderedGroups.map((group) => (
                <TableHead
                  key={group.key}
                  scope="col"
                  className="w-56 py-2 align-top [overflow-wrap:anywhere]"
                >
                  <span
                    className="font-mono text-xs font-semibold text-slate-950"
                    title={groupLabel(group)}
                  >
                    {group.caseHash ? formatCaseHashLabel(group.caseHash) : groupLabel(group)}
                  </span>
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
                  className="sticky left-0 z-10 scroll-mt-24 bg-white py-2 align-top text-xs font-medium text-slate-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                >
                  {label}
                </TableHead>
                {orderedGroups.map((group) => (
                  <TableCell key={group.key} className="align-top">
                    <ConfigurationValue field={group.configuration[field]} identity={identity} />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
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
