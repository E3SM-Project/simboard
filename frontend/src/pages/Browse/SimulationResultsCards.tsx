import BrowseToolbar from '@/pages/Browse/BrowseToolbar';
import SimulationResultCard from '@/pages/Browse/SimulationResultCard';
import type { SimulationOut } from '@/types/index';

interface SimulationResultCards {
  simulations: SimulationOut[];
  filteredData: SimulationOut[];
  selectedSimulationIds: string[];
  setSelectedSimulationIds: (ids: string[]) => void;
  handleCompareButtonClick: () => void;
}

const SimulationResultCards = ({
  simulations,
  filteredData,
  selectedSimulationIds,
  setSelectedSimulationIds,
  handleCompareButtonClick,
}: SimulationResultCards) => {
  const isCompareButtonDisabled = selectedSimulationIds.length < 2;

  return (
    <div>
      {/* Top controls */}
      <div className="flex items-center py-4">
        <BrowseToolbar
          simulations={simulations}
          buttonText="Compare"
          onCompareButtonClick={handleCompareButtonClick}
          selectedSimulationIds={selectedSimulationIds}
          setSelectedSimulationIds={setSelectedSimulationIds}
          isCompareButtonDisabled={isCompareButtonDisabled}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
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

export default SimulationResultCards;
