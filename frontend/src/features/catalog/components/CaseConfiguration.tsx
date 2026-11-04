import { Link } from 'react-router-dom';

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatCaseDate, formatSimulationCoverage } from '@/features/catalog/caseUtils';
import { executionDetailsPath, type ReadableCaseIdentity } from '@/lib/catalog/urls';
import type {
  CaseDetailOut,
  CaseHashConfigurationOut,
  ConfigurationFieldOut,
  ConfigurationObservationOut,
} from '@/types';

// Source-code path and dedicated model hash UI belong to #443.
const CONFIGURATION_FIELDS = [
  ['compset_alias', 'Compset alias'],
  ['grid_alias', 'Grid alias'],
  ['git_tag', 'Model tag/version'],
  ['compset_long_name', 'Compset long name'],
  ['grid_long_name', 'Grid long name'],
] as const;

export const CaseConfigurationSummary = ({ record }: { record: CaseDetailOut }) => (
  <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3" aria-label="Shared configuration">
    {CONFIGURATION_FIELDS.slice(0, 3).map(([field, label]) => {
      const summary = record.sharedConfiguration?.[field];

      return (
        <div key={field} className="min-w-0">
          <dt className="text-xs font-medium text-slate-500">{label}</dt>
          <dd className="break-words font-semibold text-slate-950 [overflow-wrap:anywhere]">
            {summary?.varies ? 'Varies by Case Hash' : (summary?.value ?? 'Unavailable')}
          </dd>
          {summary?.incomplete && (summary.value != null || summary.varies) ? (
            <p className="text-xs text-muted-foreground">Some executions unavailable</p>
          ) : null}
          {summary?.hasDifferences ? (
            <p className="text-xs text-muted-foreground">Changes within Case Hash</p>
          ) : null}
        </div>
      );
    })}
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
  const differingFields = CONFIGURATION_FIELDS.filter(
    ([field]) => record.sharedConfiguration?.[field]?.varies,
  );

  return (
    <details className="min-w-0 border-t border-slate-200 pt-3" data-case-configuration>
      <summary className="cursor-pointer text-sm font-semibold">Configuration by Case Hash</summary>
      <div className="mt-3 min-w-0 space-y-4">
        <p className="text-xs text-muted-foreground">
          Baselines use the earliest available value per field, ordered by run start with run end
          fallback. Undated executions sort last; execution IDs break ties. Values may come from
          different executions. Missing-hash executions remain separate.
        </p>
        {differingFields.length > 0 ? (
          <div className="min-w-0" data-configuration-differences>
            <h3 className="mb-2 text-sm font-semibold">Configuration differences</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Field</TableHead>
                  {groups.map((group) => (
                    <TableHead key={group.key} scope="col" className="min-w-48 max-w-72 break-all">
                      {groupLabel(group)}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {differingFields.map(([field, label]) => (
                  <TableRow key={field}>
                    <TableHead scope="row">{label}</TableHead>
                    {groups.map((group) => (
                      <TableCell key={group.key} className="min-w-48 max-w-72 align-top">
                        <ConfigurationValue
                          field={group.configuration[field]}
                          identity={identity}
                        />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No configuration differences between Case Hash baselines.
          </p>
        )}
        {groups.map((group) => (
          <details
            key={group.key}
            className="min-w-0 rounded-md border p-3"
            data-configuration-group
          >
            <summary className="cursor-pointer break-all text-sm font-semibold">
              {groupLabel(group)}
            </summary>
            <p className="mt-2 text-sm">
              Simulated years covered: {formatSimulationCoverage(group.coverage)}
            </p>
            <dl className="mt-3 grid min-w-0 gap-4 sm:grid-cols-2">
              {CONFIGURATION_FIELDS.map(([field, label]) => (
                <div key={field} className="min-w-0">
                  <dt className="mb-1 text-xs font-medium text-slate-500">{label}</dt>
                  <dd>
                    <ConfigurationValue field={group.configuration[field]} identity={identity} />
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        ))}
      </div>
    </details>
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
