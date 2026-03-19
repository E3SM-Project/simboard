import { BrowseToolbar } from '@/features/browse/components/BrowseToolbar';
import { SimulationResultCard } from '@/features/browse/components/SimulationResults/SimulationResultCard';
import type { SimulationOut } from '@/types/index';

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
              handleSelect={() => {
                if (selectedSimulationIds.includes(sim.id)) {
                  setSelectedSimulationIds(selectedSimulationIds.filter((id) => id !== sim.id));
                } else {
                  setSelectedSimulationIds([...selectedSimulationIds, sim.id]);
                }
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
};
