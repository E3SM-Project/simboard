import {
  BadgeCheck,
  Clock,
  FlaskConical,
  GitBranch,
  Lightbulb,
  Rocket,
  Server,
  Tag,
} from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import { SimulationStatusBadge } from '@/components/shared/SimulationStatusBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { TableCellText } from '@/components/ui/table-cell-text';
import { SimulationBrowseDetailsDialog } from '@/features/browse/components/SimulationResults/SimulationBrowseDetailsDialog';
import type { SimulationOut } from '@/types/index';

interface SimulationResultCard {
  simulation: SimulationOut;
  selected: boolean;
  isSelectionDisabled: boolean;
  handleSelect: (sim: SimulationOut) => void;
}

const shouldIgnoreSelection = (target: EventTarget | null): boolean =>
  target instanceof Element &&
  Boolean(target.closest('button, a, input, [role="button"], [data-prevent-selection]'));

export const SimulationResultCard = ({
  simulation,
  selected,
  isSelectionDisabled,
  handleSelect,
}: SimulationResultCard) => {
  // -------------------- Router --------------------
  const navigate = useNavigate();
  const location = useLocation();
  const currentPath = `${location.pathname}${location.search}`;

  // -------------------- Derived Data --------------------
  const startStr = simulation.simulationStartDate
    ? new Date(simulation.simulationStartDate).toISOString().slice(0, 10)
    : 'N/A';
  const endStr = simulation.simulationEndDate
    ? new Date(simulation.simulationEndDate).toISOString().slice(0, 10)
    : 'N/A';

  return (
    <Card
      className={`flex h-full w-full flex-col rounded-2xl border bg-white p-0 shadow-sm transition-shadow ${
        selected
          ? 'border-slate-300 ring-1 ring-slate-200'
          : 'border-slate-200 hover:shadow-md'
      } ${isSelectionDisabled ? 'cursor-default' : 'cursor-pointer'}`}
      onClick={(event) => {
        if (shouldIgnoreSelection(event.target)) {
          return;
        }

        if (!isSelectionDisabled || selected) {
          handleSelect(simulation);
        }
      }}
    >
      <div className="flex flex-col items-start gap-4 p-5 sm:flex-row">
        <Checkbox
          checked={selected}
          onCheckedChange={() => handleSelect(simulation)}
          aria-label="Select for comparison"
          className="mt-1"
          disabled={isSelectionDisabled && !selected}
          onClick={(event) => event.stopPropagation()}
          style={{ width: 24, height: 24 }}
        />
        <div className="w-full max-w-2xl min-w-0 flex-1">
          <CardHeader className="mb-4 flex flex-col items-start gap-2.5 p-0">
            <div className="min-w-0">
              <span className="block break-words text-base font-semibold tracking-tight text-slate-950">
                {simulation.executionId}
              </span>
              <div className="mt-1 min-w-0 text-sm leading-6 text-slate-500">
                <span className="font-medium text-slate-600">Case:</span>
                <TableCellText
                  value={simulation.caseName}
                  lines={2}
                  fullValueMode="tooltip"
                  className="mt-0.5 text-sm leading-6 text-slate-500 [overflow-wrap:anywhere]"
                />
              </div>
            </div>
            <div className="flex w-full flex-wrap items-center gap-2 text-xs uppercase tracking-[0.12em] text-slate-400">
              <span>Status</span>
              <SimulationStatusBadge status={simulation.status} />
            </div>
          </CardHeader>

          <CardContent
            className="p-0"
            style={{
              minHeight: '340px', // adjust as needed for consistent bottom alignment
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* One metadata item per line with bold labels */}
            <dl className="mb-2 space-y-2 text-sm">
              <div className="flex items-start gap-2">
                <dt className="flex shrink-0 items-center gap-2 whitespace-nowrap font-semibold text-slate-700">
                  <Rocket className="w-4 h-4" /> Campaign:
                </dt>
                <dd className="min-w-0 flex-1 font-normal text-slate-600">
                  <TableCellText
                    value={simulation.campaign}
                    lines={2}
                    fullValueMode="tooltip"
                    className="text-sm leading-6 text-slate-600 [overflow-wrap:anywhere]"
                  />
                </dd>
              </div>

              <div className="flex items-start gap-2">
                <dt className="flex shrink-0 items-center gap-2 whitespace-nowrap font-semibold text-slate-700">
                  <Lightbulb className="w-4 h-4" /> Experiment:
                </dt>
                <dd className="min-w-0 flex-1 font-normal text-slate-600">
                  <TableCellText
                    value={simulation.experimentType}
                    lines={2}
                    fullValueMode="tooltip"
                    className="text-sm leading-6 text-slate-600 [overflow-wrap:anywhere]"
                  />
                </dd>
              </div>

              <div className="flex items-start gap-2">
                <dt className="flex items-center gap-2 whitespace-nowrap font-semibold text-slate-700">
                  <Clock className="w-4 h-4" /> Model Run Dates:
                </dt>
                <dd className="break-words font-normal text-slate-600">
                  {startStr} {'\u2192'} {endStr}
                </dd>
              </div>
            </dl>

            <div className="my-2 w-full border-t border-slate-200" />

            <div className="mb-4 mt-2 space-y-2 text-xs text-slate-700">
              <div className="flex items-start gap-2">
                <FlaskConical className="mt-0.5 h-3 w-3 shrink-0 text-slate-700" />
                <span className="font-semibold">Grid:</span>
                <span className="min-w-0 break-words font-normal text-slate-500">
                  {simulation.gridName}
                </span>
              </div>
              <div className="flex items-start gap-2">
                <Server className="mt-0.5 h-3 w-3 shrink-0 text-slate-700" />
                <span className="font-semibold">Machine:</span>
                <span className="min-w-0 break-words font-normal text-slate-500">
                  {simulation.machine.name}
                </span>
              </div>
            </div>

            <div className="mb-4 mt-2 flex flex-wrap items-center gap-2">
              <Badge
                variant="secondary"
                className="flex items-center gap-1 border border-slate-200 bg-slate-50 px-2 py-1 text-sm text-slate-700"
              >
                <Tag className="w-4 h-4" />
                Tag:
                <span className="text-xs px-1 py-1 ml-1">{simulation.gitTag}</span>
              </Badge>
              <Badge
                variant="secondary"
                className="flex items-center gap-1 border border-slate-200 bg-slate-50 px-2 py-1 text-sm text-slate-700"
              >
                Reference: {simulation.isReference ? 'Yes' : 'No'}
                {!simulation.isReference && simulation.changeCount > 0 && (
                  <span className="ml-1 text-xs text-muted-foreground">
                    (Changes: {simulation.changeCount})
                  </span>
                )}
              </Badge>
              <Badge
                className={`text-xs px-2 py-1 ${
                  simulation.simulationType === 'production'
                    ? 'bg-green-600 text-white'
                    : simulation.simulationType === 'master'
                      ? 'bg-blue-600 text-white'
                      : 'bg-yellow-400 text-black'
                }`}
                style={{
                  backgroundColor:
                    simulation.simulationType === 'production'
                      ? '#16a34a'
                      : simulation.simulationType === 'master'
                        ? '#2563eb'
                        : '#facc15',
                  color:
                    simulation.simulationType === 'production' ||
                    simulation.simulationType === 'master'
                      ? '#fff'
                      : '#000',
                }}
              >
                {simulation.simulationType === 'production' ? (
                  <>
                    <BadgeCheck className="w-4 h-4 mr-1" /> Production Run
                  </>
                ) : simulation.simulationType === 'master' ? (
                  <>
                    <GitBranch className="w-4 h-4 mr-1" /> Master Run
                  </>
                ) : (
                  <>
                    <FlaskConical className="w-4 h-4 mr-1" /> Experimental Run
                  </>
                )}
              </Badge>
            </div>

            <div style={{ height: '6px' }} />

            <SimulationBrowseDetailsDialog
              simulation={simulation}
              triggerClassName="mb-4 w-full justify-between rounded-xl border-slate-200 bg-slate-50/70 px-4 py-6 text-left text-base text-slate-900 hover:bg-slate-100"
            />

            <div className="flex flex-col sm:flex-row items-center gap-4 mt-4 justify-end">
              <Button
                variant="outline"
                size="sm"
                className="w-full sm:w-40"
                onClick={(event) => {
                  event.stopPropagation();
                  navigate(`/simulations/${simulation.id}`, { state: { from: currentPath } });
                }}
              >
                All Details
              </Button>
            </div>
          </CardContent>
        </div>
      </div>
    </Card>
  );
};
