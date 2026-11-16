import type { ExecutionListItemOut, ExecutionSummaryOut } from '@/types';
import { formatModelDate } from '@/utils/utils';

export interface ExecutionCandidate {
  summary: ExecutionSummaryOut;
  details?: ExecutionListItemOut;
}

export const MAX_CASE_EXECUTIONS = 5;
export const MISSING_CASE_HASH_LABEL = 'Missing Case Hash';

export const EXECUTION_METADATA_FIELDS = [
  ['machineName', 'Machine'],
  ['initializationType', 'Initialization'],
  ['compsetAlias', 'Compset Alias'],
  ['gridAlias', 'Grid Alias'],
] as const;

type MetadataKey = (typeof EXECUTION_METADATA_FIELDS)[number][0];

export const knownExecutionValue = (value?: string | null) => {
  const text = value?.trim();
  return text && !['unknown', 'unavailable', 'n/a', '—'].includes(text.toLowerCase()) ? text : null;
};

export const hasCaseHashContext = (executions: ExecutionSummaryOut[]) =>
  new Set(executions.map((execution) => execution.caseHash)).size > 1;

export const getVaryingExecutionFields = (executions: ExecutionCandidate[]): MetadataKey[] =>
  EXECUTION_METADATA_FIELDS.filter(
    ([key]) =>
      new Set(
        executions
          .map(({ details }) => knownExecutionValue(details?.[key]))
          .filter((value) => value != null),
      ).size > 1,
  ).map(([key]) => key);

export const formatExecutionDateRange = (execution: ExecutionSummaryOut) =>
  `${formatModelDate(execution.simulationStartDate)} → ${formatModelDate(execution.simulationEndDate)}`;

export const formatRunDateRange = (startDate?: string | null, endDate?: string | null) => {
  if (!startDate && !endDate) return '—';
  const start = startDate?.slice(0, 10) ?? '—';
  const end = endDate?.slice(0, 10) ?? '—';

  if (!startDate) return end;
  if (!endDate) return start;
  return start === end ? start : `${start} → ${end}`;
};

export const formatCaseHashLabel = (caseHash: string | null, maxLength = 18) => {
  if (!caseHash) return MISSING_CASE_HASH_LABEL;
  if (caseHash.length <= maxLength) return caseHash;
  const leadingChars = Math.max(6, Math.floor((maxLength - 1) / 2));
  const trailingChars = Math.max(4, maxLength - leadingChars - 1);

  return `${caseHash.slice(0, leadingChars)}…${caseHash.slice(-trailingChars)}`;
};

export const getExecutionSummary = (
  candidate: ExecutionCandidate,
  discovery: ReturnType<typeof getExecutionDiscoveryContext>,
) => {
  const { summary, details } = candidate;
  const { varyingFields, showRunDates, showCaseHash } = discovery;
  const metadata = EXECUTION_METADATA_FIELDS.flatMap(([key, label]) => {
    const value = knownExecutionValue(details?.[key]);
    return varyingFields.includes(key) && value ? [`${label}: ${value}`] : [];
  }).join(' · ');
  const context = [
    ...(showRunDates && (details?.runStartDate || details?.runEndDate)
      ? [`Run: ${formatRunDateRange(details.runStartDate, details.runEndDate)}`]
      : []),
    ...(metadata ? [metadata] : []),
    ...(showCaseHash
      ? [
          summary.caseHash
            ? `Hash: ${formatCaseHashLabel(summary.caseHash)}`
            : MISSING_CASE_HASH_LABEL,
        ]
      : []),
  ].join(' · ');

  return {
    executionId: summary.executionId,
    simulationPeriod: formatExecutionDateRange(summary),
    context,
    metadata,
  };
};

export const getExecutionDiscoveryContext = (executions: ExecutionCandidate[]) => {
  const runDates = new Set(
    executions
      .map(({ details }) => formatRunDateRange(details?.runStartDate, details?.runEndDate))
      .filter((value) => value !== '—'),
  );
  return {
    varyingFields: getVaryingExecutionFields(executions),
    showRunDates: runDates.size > 1,
    showCaseHash: hasCaseHashContext(executions.map(({ summary }) => summary)),
  };
};

export const matchesExecutionSearch = (
  candidate: ExecutionCandidate,
  discovery: ReturnType<typeof getExecutionDiscoveryContext>,
  query: string,
) => {
  const summary = getExecutionSummary(candidate, discovery);
  const metadata = [
    ...EXECUTION_METADATA_FIELDS.map(([key]) => knownExecutionValue(candidate.details?.[key])),
    knownExecutionValue(candidate.details?.compsetLongName),
    knownExecutionValue(candidate.details?.gridLongName),
  ];

  return [
    summary.executionId,
    summary.simulationPeriod,
    summary.context,
    candidate.summary.caseHash ?? MISSING_CASE_HASH_LABEL,
    formatRunDateRange(candidate.details?.runStartDate, candidate.details?.runEndDate),
    ...metadata,
  ]
    .join(' ')
    .toLowerCase()
    .includes(query.trim().toLowerCase());
};

export const toggleCaseExecution = (ids: string[], id: string) =>
  ids.includes(id)
    ? ids.filter((selected) => selected !== id)
    : ids.length < MAX_CASE_EXECUTIONS
      ? [...ids, id]
      : ids;

export const reconcileExecutionOrder = (previous: string[], selected: string[]) => [
  ...previous.filter((id) => selected.includes(id)),
  ...selected.filter((id) => !previous.includes(id)),
];
