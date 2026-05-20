import { format } from 'date-fns';

import type { CaseOut, SimulationSummaryOut } from '@/types';

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
  `${formatCaseDate(simulation.simulationStartDate)} → ${formatCaseDate(simulation.simulationEndDate)}`;

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
      new Date(simulation.simulationStartDate).getTime() <
        new Date(earliestSimulation.simulationStartDate).getTime()
    ) {
      earliestSimulation = simulation;
    }

    const simulationEndDate = simulation.simulationEndDate ?? simulation.simulationStartDate;
    const latestEndDate =
      latestSimulation?.simulationEndDate ?? latestSimulation?.simulationStartDate ?? null;

    if (
      latestSimulation == null ||
      new Date(simulationEndDate).getTime() > new Date(latestEndDate ?? simulationEndDate).getTime()
    ) {
      latestSimulation = simulation;
    }
  }

  return {
    startDate: earliestSimulation?.simulationStartDate ?? null,
    endDate:
      latestSimulation?.simulationEndDate ?? latestSimulation?.simulationStartDate ?? null,
  };
};

export const getReferenceSimulation = (caseRecord: CaseOut) =>
  caseRecord.simulations.find((simulation) => simulation.id === caseRecord.referenceSimulationId) ??
  null;

export const sortSimulationSummaries = (simulations: SimulationSummaryOut[]) =>
  [...simulations].sort((left, right) => {
    if (left.isReference !== right.isReference) {
      return left.isReference ? -1 : 1;
    }

    return (
      new Date(right.simulationStartDate).getTime() - new Date(left.simulationStartDate).getTime()
    );
  });

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
      latestSimulationStartTime: number;
    }
  >();

  for (const simulation of sortSimulationSummaries(simulations)) {
    const isFallback = simulation.caseHash == null;
    const key = simulation.caseHash ?? '__missing_case_hash__';
    const latestSimulationStartTime = new Date(simulation.simulationStartDate).getTime();
    const existingGroup = groups.get(key);

    if (existingGroup) {
      existingGroup.simulations.push(simulation);
      existingGroup.latestSimulationStartTime = Math.max(
        existingGroup.latestSimulationStartTime,
        latestSimulationStartTime,
      );
      continue;
    }

    groups.set(key, {
      key,
      caseHash: simulation.caseHash,
      label: isFallback ? MISSING_CASE_HASH_LABEL : formatCaseHashLabel(simulation.caseHash),
      isFallback,
      simulations: [simulation],
      latestSimulationStartTime,
    });
  }

  return [...groups.values()]
    .sort((left, right) => {
      if (left.isFallback !== right.isFallback) {
        return left.isFallback ? 1 : -1;
      }

      if (left.latestSimulationStartTime !== right.latestSimulationStartTime) {
        return right.latestSimulationStartTime - left.latestSimulationStartTime;
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

export const getDefaultExpandedGroupKeys = (groups: SimulationSummaryGroup[]) => {
  if (groups.length <= 3) {
    return groups.map((group) => group.key);
  }

  if (groups.length <= 6) {
    return groups.slice(0, 3).map((group) => group.key);
  }

  return groups.slice(0, 1).map((group) => group.key);
};

export const matchesSimulationGroupFilter = (
  group: SimulationSummaryGroup,
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
