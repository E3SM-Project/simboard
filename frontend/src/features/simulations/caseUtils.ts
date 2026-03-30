import { format } from 'date-fns';

import type { CaseOut, SimulationSummaryOut } from '@/types';

export const formatCaseDate = (value?: string | null) => {
  if (!value) return '—';

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  return format(date, 'yyyy-MM-dd');
};

export const formatSimulationDateRange = (simulation: SimulationSummaryOut) =>
  `${formatCaseDate(simulation.simulationStartDate)} → ${formatCaseDate(simulation.simulationEndDate)}`;

export const getCanonicalSimulation = (caseRecord: CaseOut) =>
  caseRecord.simulations.find((simulation) => simulation.id === caseRecord.canonicalSimulationId) ??
  null;

export const sortSimulationSummaries = (simulations: SimulationSummaryOut[]) =>
  [...simulations].sort((left, right) => {
    if (left.isCanonical !== right.isCanonical) {
      return left.isCanonical ? -1 : 1;
    }

    return (
      new Date(right.simulationStartDate).getTime() - new Date(left.simulationStartDate).getTime()
    );
  });
