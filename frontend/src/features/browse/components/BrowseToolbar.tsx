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
    <div className="w-full rounded-2xl border border-slate-200 bg-slate-50/80 p-3 shadow-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button
            variant="default"
            size="sm"
            onClick={() => onCompareButtonClick()}
            disabled={isCompareButtonDisabled}
            className="h-10 rounded-xl px-4 shadow-sm"
          >
            {buttonText}
          </Button>

          <div className="inline-flex w-fit items-center rounded-full border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm">
            <span className="mr-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
              Selected
            </span>
            <span className="font-semibold text-slate-950">
              {selectedSimulationIds.length} / {MAX_SELECTION}
            </span>
          </div>
        </div>

        {selectedSimulationIds.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 shrink-0 rounded-full px-3 text-xs font-medium text-slate-500 transition-colors hover:bg-white hover:text-slate-900 lg:self-start"
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
                className="flex min-w-0 max-w-full items-center rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm sm:max-w-[280px] xl:max-w-[240px] 2xl:max-w-[300px]"
              >
                <span className="min-w-0 truncate">{row.executionId}</span>
                <button
                  type="button"
                  className="ml-1 shrink-0 rounded-full text-slate-400 transition-colors hover:text-destructive focus:outline-none"
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
