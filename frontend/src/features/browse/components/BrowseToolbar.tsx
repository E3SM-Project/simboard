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
    <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-start">
      <Button
        variant="default"
        size="sm"
        onClick={() => onCompareButtonClick()}
        disabled={isCompareButtonDisabled}
        className="w-full sm:w-auto"
      >
        {buttonText}
      </Button>

      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 sm:ml-4">
        <span
          className={`text-xs ${
            selectedSimulationIds.length === MAX_SELECTION
              ? 'text-warning font-bold'
              : 'text-muted-foreground'
          }`}
        >
          Selected: {selectedSimulationIds.length} / {MAX_SELECTION}
        </span>
        {selectedSimulationIds.map((id) => {
          const row = simulations.find((r) => r.id === id);
          if (!row) return null;
          return (
            <span
              key={id}
              className="flex max-w-full items-center rounded bg-muted px-2 py-1 text-xs font-medium text-muted-foreground"
            >
              <span className="truncate">{row.executionId}</span>
              <button
                type="button"
                className="ml-1 text-muted-foreground hover:text-destructive focus:outline-none"
                aria-label={`Remove ${row.executionId}`}
                onClick={() =>
                  setSelectedSimulationIds(selectedSimulationIds.filter((rowId) => rowId !== id))
                }
              >
                ×
              </button>
            </span>
          );
        })}
        {selectedSimulationIds.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="text-xs sm:ml-2"
            onClick={() => setSelectedSimulationIds([])}
          >
            Deselect all
          </Button>
        )}
      </div>
    </div>
  );
};
