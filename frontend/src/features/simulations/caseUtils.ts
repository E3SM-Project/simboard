import { format } from 'date-fns';

import type { SimulationSummaryOut } from '@/types';
import { compareModelDates, formatModelDate } from '@/utils/utils';

export const MISSING_CASE_HASH_LABEL = 'Missing Case Hash';

export interface SimulationSummaryGroup {
  key: string;
  caseHash: string | null;
  label: string;
  isFallback: boolean;
  simulations: SimulationSummaryOut[];
}

export type SimulationSummaryGroupFilter = 'all' | 'multiRun' | 'missing';

export interface SimulationSummaryDateWindow {
  startDate: string | null;
  endDate: string | null;
}

export const formatCaseDate = (value?: string | null) => {
  if (!value) return '—';

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  return format(date, 'yyyy-MM-dd');
};

export const formatSimulationDateRange = (simulation: SimulationSummaryOut) =>
  `${formatModelDate(simulation.simulationStartDate)} → ${formatModelDate(simulation.simulationEndDate)}`;

export const getSimulationSummaryDateWindow = (
  simulations: SimulationSummaryOut[],
): SimulationSummaryDateWindow => {
  if (simulations.length === 0) {
    return { startDate: null, endDate: null };
  }

  let earliestSimulation: SimulationSummaryOut | null = null;
  let latestSimulation: SimulationSummaryOut | null = null;

  for (const simulation of simulations) {
    if (
      earliestSimulation == null ||
      compareModelDates(simulation.simulationStartDate, earliestSimulation.simulationStartDate) < 0
    ) {
      earliestSimulation = simulation;
    }

    const simulationEndDate = simulation.simulationEndDate ?? simulation.simulationStartDate;
    const latestEndDate =
      latestSimulation?.simulationEndDate ?? latestSimulation?.simulationStartDate ?? null;

    if (
      latestSimulation == null ||
      compareModelDates(simulationEndDate, latestEndDate ?? simulationEndDate) > 0
    ) {
      latestSimulation = simulation;
    }
  }

  return {
    startDate: earliestSimulation?.simulationStartDate ?? null,
    endDate: latestSimulation?.simulationEndDate ?? latestSimulation?.simulationStartDate ?? null,
  };
};

export const sortSimulationSummaries = (simulations: SimulationSummaryOut[]) =>
  [...simulations].sort((left, right) =>
    compareModelDates(right.simulationStartDate, left.simulationStartDate),
  );

export const formatCaseHashLabel = (caseHash: string | null, maxLength = 18) => {
  if (!caseHash) return MISSING_CASE_HASH_LABEL;
  if (caseHash.length <= maxLength) return caseHash;

  const leadingChars = Math.max(6, Math.floor((maxLength - 1) / 2));
  const trailingChars = Math.max(4, maxLength - leadingChars - 1);

  return `${caseHash.slice(0, leadingChars)}…${caseHash.slice(-trailingChars)}`;
};

export const groupSimulationSummaries = (
  simulations: SimulationSummaryOut[],
): SimulationSummaryGroup[] => {
  const groups = new Map<
    string,
    SimulationSummaryGroup & {
      latestSimulationStartDate: string;
    }
  >();

  for (const simulation of sortSimulationSummaries(simulations)) {
    const isFallback = simulation.caseHash == null;
    const key = simulation.caseHash ?? '__missing_case_hash__';
    const latestSimulationStartDate = simulation.simulationStartDate;
    const existingGroup = groups.get(key);

    if (existingGroup) {
      existingGroup.simulations.push(simulation);
      if (
        compareModelDates(latestSimulationStartDate, existingGroup.latestSimulationStartDate) > 0
      ) {
        existingGroup.latestSimulationStartDate = latestSimulationStartDate;
      }
      continue;
    }

    groups.set(key, {
      key,
      caseHash: simulation.caseHash,
      label: isFallback ? MISSING_CASE_HASH_LABEL : formatCaseHashLabel(simulation.caseHash),
      isFallback,
      simulations: [simulation],
      latestSimulationStartDate,
    });
  }

  return [...groups.values()]
    .sort((left, right) => {
      if (left.isFallback !== right.isFallback) {
        return left.isFallback ? 1 : -1;
      }

      if (left.latestSimulationStartDate !== right.latestSimulationStartDate) {
        return compareModelDates(right.latestSimulationStartDate, left.latestSimulationStartDate);
      }

      if (left.simulations.length !== right.simulations.length) {
        return right.simulations.length - left.simulations.length;
      }

      return left.label.localeCompare(right.label);
    })
    .map((group) => ({
      key: group.key,
      caseHash: group.caseHash,
      label: group.label,
      isFallback: group.isFallback,
      simulations: group.simulations,
    }));
};

export const getDefaultExpandedGroupKeys = <T extends { key: string }>(groups: T[]) => {
  return groups.slice(0, 1).map((group) => group.key);
};

export const matchesSimulationGroupFilter = <
  T extends { isFallback: boolean; simulations: unknown[] },
>(
  group: T,
  filterMode: SimulationSummaryGroupFilter,
) => {
  switch (filterMode) {
    case 'multiRun':
      return group.simulations.length > 1;
    case 'missing':
      return group.isFallback;
    case 'all':
    default:
      return true;
  }
};
