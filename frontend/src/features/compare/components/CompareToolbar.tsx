import { Button } from '@/components/ui/button';

interface CompareToolbarProps {
  simulationCount: number;
  onBackToBrowse?: () => void;
}

const CompareToolbar = ({ simulationCount, onBackToBrowse }: CompareToolbarProps) => {
  return (
    <div className="flex items-center justify-between mb-2 px-2 py-1 border-b border-gray-200 bg-gray-50 rounded-md shadow-sm">
      <span className="text-base font-medium text-gray-800">
        Comparing <span className="font-bold">{simulationCount}</span> simulation
        {simulationCount !== 1 ? 's' : ''}
      </span>
      <div className="flex gap-2">
        {/* Future actions can be added here */}
        <Button variant="outline" onClick={onBackToBrowse}>
          Back to Browse
        </Button>
        {/* Example: Highlight differences button */}
        {/* <Button variant="outline">Highlight differences</Button> */}
      </div>
    </div>
  );
};

export default CompareToolbar;
