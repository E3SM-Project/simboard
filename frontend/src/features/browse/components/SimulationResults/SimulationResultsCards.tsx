import { BrowseToolbar } from '@/features/browse/components/BrowseToolbar';
import { SimulationResultCard } from '@/features/browse/components/SimulationResults/SimulationResultCard';
import type { SimulationOut } from '@/types/index';

const MAX_SELECTION = 5;

interface SimulationResultCards {
  simulations: SimulationOut[];
  filteredData: SimulationOut[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
  handleCompareButtonClick: () => void;
}

export const SimulationResultCards = ({
  simulations,
  filteredData,
  selectedSimulationIds,
  setSelectedSimulationIds,
  handleCompareButtonClick,
}: SimulationResultCards) => {
  const isCompareButtonDisabled = selectedSimulationIds.length < 2;
  const handleSelectSimulation = (simulation: SimulationOut) => {
    const isSelected = selectedSimulationIds.includes(simulation.id);

    if (isSelected) {
      setSelectedSimulationIds(selectedSimulationIds.filter((id) => id !== simulation.id));
      return;
    }

    if (selectedSimulationIds.length >= MAX_SELECTION) {
      return;
    }

    setSelectedSimulationIds([...selectedSimulationIds, simulation.id]);
  };

  return (
    <div className="min-w-0">
      {/* Top controls */}
      <div className="py-4">
        <BrowseToolbar
          simulations={simulations}
          buttonText="Compare"
          onCompareButtonClick={handleCompareButtonClick}
          selectedSimulationIds={selectedSimulationIds}
          setSelectedSimulationIds={setSelectedSimulationIds}
          isCompareButtonDisabled={isCompareButtonDisabled}
        />
      </div>

      <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(320px,1fr))]">
        {filteredData.map((sim) => (
          <div key={sim.id} className="h-full">
            <SimulationResultCard
              simulation={sim}
              selected={selectedSimulationIds.includes(sim.id)}
              isSelectionDisabled={
                !selectedSimulationIds.includes(sim.id) &&
                selectedSimulationIds.length >= MAX_SELECTION
              }
              handleSelect={handleSelectSimulation}
            />
          </div>
        ))}
      </div>
    </div>
  );
};
