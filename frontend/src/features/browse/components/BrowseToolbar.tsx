import { Button } from '@/components/ui/button';
import type { SimulationOut } from '@/types/index';

interface SelectedSimulationsBreadcrumbProps {
  simulations: SimulationOut[];
  buttonText: string;
  onCompareButtonClick: () => void;
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
  isCompareButtonDisabled: boolean;
}

const MAX_SELECTION = 5;

export const BrowseToolbar = ({
  simulations,
  buttonText,
  onCompareButtonClick,
  selectedSimulationIds,
  setSelectedSimulationIds,
  isCompareButtonDisabled,
}: SelectedSimulationsBreadcrumbProps) => {
  return (
    <div className="w-full rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button
            variant="default"
            size="sm"
            onClick={() => onCompareButtonClick()}
            disabled={isCompareButtonDisabled}
            className="h-10 rounded-lg px-4 shadow-none"
          >
            {buttonText}
          </Button>

          <div className="flex items-baseline gap-2 text-sm text-slate-600">
            <span className="font-medium text-slate-500">Selected</span>
            <span className="font-semibold text-slate-950">
              {selectedSimulationIds.length} / {MAX_SELECTION}
            </span>
          </div>
        </div>

        {selectedSimulationIds.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 shrink-0 rounded-md px-2 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 lg:self-start"
            onClick={() => setSelectedSimulationIds([])}
          >
            Deselect all
          </Button>
        )}
      </div>

      {selectedSimulationIds.length > 0 && (
        <div className="mt-3 flex min-w-0 flex-wrap items-start gap-2">
          {selectedSimulationIds.map((id) => {
            const row = simulations.find((r) => r.id === id);
            if (!row) return null;
            return (
              <span
                key={id}
                className="flex min-w-0 max-w-full items-center rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 sm:max-w-[220px] xl:max-w-[200px] 2xl:max-w-[220px]"
              >
                <span className="min-w-0 truncate">{row.executionId}</span>
                <button
                  type="button"
                  className="ml-1 shrink-0 rounded-sm text-slate-400 transition-colors hover:text-destructive focus:outline-none"
                  aria-label={`Remove ${row.executionId}`}
                  onClick={() =>
                    setSelectedSimulationIds(
                      selectedSimulationIds.filter((rowId) => rowId !== id),
                    )
                  }
                >
                  ×
                </button>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
};
