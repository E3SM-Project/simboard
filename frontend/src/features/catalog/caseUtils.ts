import { format } from 'date-fns';

import type { ExecutionSummaryOut } from '@/types';
import { compareModelDates, formatModelDate } from '@/utils/utils';

export const MISSING_CASE_HASH_LABEL = 'Missing Case Hash';

export interface ExecutionSummaryGroup {
  key: string;
  caseHash: string | null;
  label: string;
  isFallback: boolean;
  executions: ExecutionSummaryOut[];
}

export type ExecutionSummaryGroupFilter = 'all' | 'multiRun' | 'missing';

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

export const formatExecutionDateRange = (execution: ExecutionSummaryOut) =>
  `${formatModelDate(execution.simulationStartDate)} → ${formatModelDate(execution.simulationEndDate)}`;

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

export const formatCaseHashLabel = (caseHash: string | null, maxLength = 18) => {
  if (!caseHash) return MISSING_CASE_HASH_LABEL;
  if (caseHash.length <= maxLength) return caseHash;

  const leadingChars = Math.max(6, Math.floor((maxLength - 1) / 2));
  const trailingChars = Math.max(4, maxLength - leadingChars - 1);

  return `${caseHash.slice(0, leadingChars)}…${caseHash.slice(-trailingChars)}`;
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
