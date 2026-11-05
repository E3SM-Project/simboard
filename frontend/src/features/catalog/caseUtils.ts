import { format } from 'date-fns';

import { formatCaseHashLabel, MISSING_CASE_HASH_LABEL } from '@/lib/catalog/executionDiscovery';
import type {
  CaseHashConfigurationOut,
  ExecutionListItemOut,
  ExecutionSummaryOut,
  SimulationCoverageOut,
  SimulationDurationOut,
} from '@/types';
import { compareModelDates } from '@/utils/utils';

export {
  formatCaseHashLabel,
  formatExecutionDateRange,
  MISSING_CASE_HASH_LABEL,
} from '@/lib/catalog/executionDiscovery';

export const formatSimulationCoverage = (coverage?: SimulationCoverageOut) => {
  const years = coverage?.years;
  const value =
    years == null
      ? 'Unavailable'
      : new Intl.NumberFormat('en', { maximumFractionDigits: 3 }).format(years);

  return `${value}${coverage?.partial ? ' (partial)' : ''}`;
};

export const formatSimulatedDuration = (duration?: SimulationDurationOut) => {
  let value = duration?.days;
  let unit = 'day';
  if (value != null && value >= 7 && (duration?.calendars.length ?? 0) <= 1) {
    if (duration?.years != null && duration.years >= 1) {
      value = duration.years;
      unit = 'year';
    } else if (duration?.months != null && duration.months >= 1) {
      value = duration.months;
      unit = 'month';
    } else {
      value /= 7;
      unit = 'week';
    }
  }
  const formatted =
    value == null
      ? 'Unavailable'
      : new Intl.NumberFormat('en', {
          style: 'unit',
          unit,
          unitDisplay: 'long',
          maximumFractionDigits: 2,
        }).format(value);

  return `${formatted}${duration?.partial ? ' (partial)' : ''}`;
};

export const describeSimulatedDuration = (duration?: SimulationDurationOut) => {
  const details = [
    'Cumulative simulated duration of completed executions. Overlaps and retries count separately; gaps do not count.',
  ];
  if (duration?.partial) {
    details.push(
      `${duration.excludedExecutionCount} execution(s) excluded: unfinished runs, missing or invalid dates, or unsupported calendars.`,
    );
  }
  if (duration?.calendarAssumed) {
    details.push(
      'Calendar unavailable for some executions; uses the stored Gregorian date convention.',
    );
  }
  if ((duration?.calendars.length ?? 0) > 1) {
    details.push(
      'Mixed model calendars; total shown in model days, not equivalent months or years.',
    );
  }

  return details.join(' ');
};

export const getConfigurationBaseline = (groups: CaseHashConfigurationOut[]) =>
  [...groups]
    .filter((group) => group.caseHash != null)
    .sort(
      (left, right) =>
        right.executionIds.length - left.executionIds.length ||
        (left.caseHash ?? '').localeCompare(right.caseHash ?? '') ||
        left.key.localeCompare(right.key),
    )[0];

export const getConfigurationDiffParts = (
  value: string,
  reference: string | null,
): Array<{ text: string; changed: boolean }> => {
  if (value === '') return [];
  if (value === reference) return [{ text: value, changed: false }];
  const tokens = value.split(/([_%./\s-]+)/).filter(Boolean);
  const referenceTokens = (reference ?? '').split(/([_%./\s-]+)/).filter(Boolean);
  // Bound work for unusually large metadata values; keep their text intact.
  if (tokens.length * referenceTokens.length > 100_000) {
    return [{ text: value, changed: true }];
  }
  const lengths = Array.from(
    { length: referenceTokens.length + 1 },
    () => new Uint32Array(tokens.length + 1),
  );
  for (let i = referenceTokens.length - 1; i >= 0; i--) {
    for (let j = tokens.length - 1; j >= 0; j--) {
      lengths[i][j] =
        referenceTokens[i] === tokens[j]
          ? 1 + lengths[i + 1][j + 1]
          : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }
  const unchanged = new Set<number>();
  let i = 0;
  let j = 0;
  while (i < referenceTokens.length && j < tokens.length) {
    if (referenceTokens[i] === tokens[j]) {
      unchanged.add(j);
      i++;
      j++;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      i++;
    } else {
      j++;
    }
  }
  const parts: Array<{ text: string; changed: boolean }> = [];
  tokens.forEach((text, index) => {
    const changed = !unchanged.has(index);
    const previous = parts.at(-1);
    if (previous?.changed === changed) previous.text += text;
    else parts.push({ text, changed });
  });
  // A deletion has no new token to mark. Highlight the remaining value instead.
  if (parts.every((part) => !part.changed)) return [{ text: value, changed: true }];

  return parts;
};

export interface ExecutionSummaryGroup {
  key: string;
  caseHash: string | null;
  label: string;
  isFallback: boolean;
  executions: ExecutionSummaryOut[];
}

export type ExecutionSummaryGroupFilter = 'all' | 'multiRun' | 'missing';

export interface ExecutionDateSort {
  key: 'simulation' | 'run';
  direction: 'asc' | 'desc';
}

interface ExecutionWithDates {
  summary: ExecutionSummaryOut;
  details?: Pick<ExecutionListItemOut, 'runStartDate' | 'runEndDate'>;
}

export interface ExecutionDateWindow {
  startDate: string | null;
  endDate: string | null;
}

export const formatCaseDate = (value?: string | null) => {
  if (!value) return '—';

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  return format(date, 'yyyy-MM-dd');
};

export const getExecutionDateWindow = (executions: ExecutionSummaryOut[]): ExecutionDateWindow => {
  if (executions.length === 0) {
    return { startDate: null, endDate: null };
  }

  let earliestExecution: ExecutionSummaryOut | null = null;
  let latestExecution: ExecutionSummaryOut | null = null;

  for (const execution of executions) {
    if (
      earliestExecution == null ||
      compareModelDates(execution.simulationStartDate, earliestExecution.simulationStartDate) < 0
    ) {
      earliestExecution = execution;
    }

    const simulationEndDate = execution.simulationEndDate ?? execution.simulationStartDate;
    const latestEndDate =
      latestExecution?.simulationEndDate ?? latestExecution?.simulationStartDate ?? null;

    if (
      latestExecution == null ||
      compareModelDates(simulationEndDate, latestEndDate ?? simulationEndDate) > 0
    ) {
      latestExecution = execution;
    }
  }

  return {
    startDate: earliestExecution?.simulationStartDate ?? null,
    endDate: latestExecution?.simulationEndDate ?? latestExecution?.simulationStartDate ?? null,
  };
};

export const sortExecutionSummaries = (executions: ExecutionSummaryOut[]) =>
  [...executions].sort((left, right) =>
    compareModelDates(right.simulationStartDate, left.simulationStartDate),
  );

export const sortCaseExecutions = <T extends ExecutionWithDates>(
  executions: T[],
  sort: ExecutionDateSort,
): T[] =>
  [...executions].sort((left, right) => {
    let comparison: number;
    if (sort.key === 'simulation') {
      comparison = compareModelDates(
        left.summary.simulationStartDate,
        right.summary.simulationStartDate,
      );
    } else {
      const leftTime = getExecutionRunTime(left);
      const rightTime = getExecutionRunTime(right);
      if (leftTime == null || rightTime == null) {
        if (leftTime != null) return -1;
        if (rightTime != null) return 1;
        comparison = 0;
      } else {
        comparison = leftTime - rightTime;
      }
    }

    return (
      comparison * (sort.direction === 'asc' ? 1 : -1) ||
      left.summary.id.localeCompare(right.summary.id)
    );
  });

const getExecutionRunTime = ({ details }: ExecutionWithDates): number | null => {
  const date = details?.runEndDate ?? details?.runStartDate;
  const timestamp = date ? new Date(date).getTime() : NaN;

  return Number.isNaN(timestamp) ? null : timestamp;
};

export const groupExecutionSummaries = (
  executions: ExecutionSummaryOut[],
): ExecutionSummaryGroup[] => {
  const groups = new Map<
    string,
    ExecutionSummaryGroup & {
      latestExecutionStartDate: string;
    }
  >();

  for (const execution of sortExecutionSummaries(executions)) {
    const isFallback = execution.caseHash == null;
    const key = execution.caseHash ?? '__missing_case_hash__';
    const latestExecutionStartDate = execution.simulationStartDate;
    const existingGroup = groups.get(key);

    if (existingGroup) {
      existingGroup.executions.push(execution);
      if (compareModelDates(latestExecutionStartDate, existingGroup.latestExecutionStartDate) > 0) {
        existingGroup.latestExecutionStartDate = latestExecutionStartDate;
      }
      continue;
    }

    groups.set(key, {
      key,
      caseHash: execution.caseHash,
      label: isFallback ? MISSING_CASE_HASH_LABEL : formatCaseHashLabel(execution.caseHash),
      isFallback,
      executions: [execution],
      latestExecutionStartDate,
    });
  }

  return [...groups.values()]
    .sort((left, right) => {
      if (left.isFallback !== right.isFallback) {
        return left.isFallback ? 1 : -1;
      }

      if (left.latestExecutionStartDate !== right.latestExecutionStartDate) {
        return compareModelDates(right.latestExecutionStartDate, left.latestExecutionStartDate);
      }

      if (left.executions.length !== right.executions.length) {
        return right.executions.length - left.executions.length;
      }

      return left.label.localeCompare(right.label);
    })
    .map((group) => ({
      key: group.key,
      caseHash: group.caseHash,
      label: group.label,
      isFallback: group.isFallback,
      executions: group.executions,
    }));
};

export const getDefaultExpandedGroupKeys = <T extends { key: string }>(groups: T[]) => {
  return groups.slice(0, 1).map((group) => group.key);
};

export const matchesExecutionGroupFilter = <
  T extends { isFallback: boolean; executions: unknown[] },
>(
  group: T,
  filterMode: ExecutionSummaryGroupFilter,
) => {
  switch (filterMode) {
    case 'multiRun':
      return group.executions.length > 1;
    case 'missing':
      return group.isFallback;
    case 'all':
    default:
      return true;
  }
};
