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

const BrowseToolbar = ({
  simulations,
  buttonText,
  onCompareButtonClick,
  selectedSimulationIds,
  setSelectedSimulationIds,
  isCompareButtonDisabled,
}: SelectedSimulationsBreadcrumbProps) => {
  return (
    <div className="flex items-center">
      <Button
        variant="default"
        size="sm"
        onClick={() => onCompareButtonClick()}
        disabled={isCompareButtonDisabled}
      >
        {buttonText}
      </Button>

      <div className="ml-4 flex flex-wrap items-center gap-2">
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
              className="flex items-center rounded bg-muted px-2 py-1 text-xs font-medium text-muted-foreground"
            >
              {row.name}
              <button
                type="button"
                className="ml-1 text-muted-foreground hover:text-destructive focus:outline-none"
                aria-label={`Remove ${row.name}`}
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
            className="ml-2 text-xs"
            onClick={() => setSelectedSimulationIds([])}
          >
            Deselect all
          </Button>
        )}
      </div>
    </div>
  );
};

export default BrowseToolbar;
