import { BrowseToolbar } from '@/features/browse/components/BrowseToolbar';
import { ExecutionResultCard } from '@/features/browse/components/ExecutionResults/ExecutionResultCard';
import { cn } from '@/lib/utils';
import type { ExecutionListItemOut } from '@/types/index';

const MAX_SELECTION = 5;

interface ExecutionResultCards {
  executions: ExecutionListItemOut[];
  filteredData: ExecutionListItemOut[];
  selectedExecutionIds: string[];
  setSelectedExecutionIds: (ids: string[]) => void;
  handleCompareButtonClick: () => void;
}

export const ExecutionResultCards = ({
  executions,
  filteredData,
  selectedExecutionIds,
  setSelectedExecutionIds,
  handleCompareButtonClick,
}: ExecutionResultCards) => {
  const isCompareButtonDisabled = selectedExecutionIds.length < 2;
  const isSingleResult = filteredData.length === 1;

  const handleSelectExecution = (execution: ExecutionListItemOut) => {
    const isSelected = selectedExecutionIds.includes(execution.id);

    if (isSelected) {
      setSelectedExecutionIds(selectedExecutionIds.filter((id) => id !== execution.id));
      return;
    }

    if (selectedExecutionIds.length >= MAX_SELECTION) {
      return;
    }

    setSelectedExecutionIds([...selectedExecutionIds, execution.id]);
  };

  return (
    <div className="min-w-0">
      {/* Top controls */}
      <div className="py-4">
        <BrowseToolbar
          executions={executions}
          buttonText="Open Cross-Case Compare"
          onCompareButtonClick={handleCompareButtonClick}
          selectedExecutionIds={selectedExecutionIds}
          setSelectedExecutionIds={setSelectedExecutionIds}
          isCompareButtonDisabled={isCompareButtonDisabled}
        />
      </div>

      <div className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(320px,1fr))]">
        {filteredData.map((execution) => (
          <div
            key={execution.id}
            className={cn('h-full', isSingleResult && 'max-w-[420px] justify-self-start')}
          >
            <ExecutionResultCard
              execution={execution}
              selected={selectedExecutionIds.includes(execution.id)}
              isSelectionDisabled={
                !selectedExecutionIds.includes(execution.id) &&
                selectedExecutionIds.length >= MAX_SELECTION
              }
              handleSelect={handleSelectExecution}
            />
          </div>
        ))}
      </div>
    </div>
  );
};
