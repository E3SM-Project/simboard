import { ChevronRight } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface CompareToolbarProps {
  backLabel?: string;
  canCompareDifferences: boolean;
  changedSectionCount: number;
  diffsEnabled: boolean;
  diffsOnlyEnabled: boolean;
  onDiffOnlyToggle: (checked: boolean) => void;
  onDiffToggle: (checked: boolean) => void;
  simulationCount: number;
  onBackToBrowse?: () => void;
  onSummaryToggle: () => void;
  summaryExpanded: boolean;
  summaryHighlightCount: number;
  toolbarDescription?: string;
  totalChangedRows: number;
}

const CompareToolbar = ({
  backLabel = 'Back to Browse',
  canCompareDifferences,
  changedSectionCount,
  diffsEnabled,
  diffsOnlyEnabled,
  onBackToBrowse,
  onDiffOnlyToggle,
  onDiffToggle,
  onSummaryToggle,
  simulationCount,
  summaryExpanded,
  summaryHighlightCount,
  toolbarDescription,
  totalChangedRows,
}: CompareToolbarProps) => {
  return (
    <section className="sticky top-4 z-30 rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-sm backdrop-blur">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <h2 className="mt-1 text-xl font-semibold text-slate-950">
            Comparing {simulationCount} simulation{simulationCount === 1 ? '' : 's'}
          </h2>
          {toolbarDescription ? (
            <p className="mt-1 max-w-2xl text-sm text-slate-600">{toolbarDescription}</p>
          ) : null}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="border-slate-300 bg-slate-50 text-slate-700">
              {changedSectionCount} changed section{changedSectionCount === 1 ? '' : 's'}
            </Badge>
            <Badge variant="outline" className="border-slate-300 bg-slate-50 text-slate-700">
              {totalChangedRows} changed row{totalChangedRows === 1 ? '' : 's'}
            </Badge>
            {diffsOnlyEnabled && (
              <Badge className="border-0 bg-slate-900 text-white shadow-none">Diff-only mode</Badge>
            )}
          </div>
        </div>

        <div className="flex w-full flex-col gap-3 lg:w-auto lg:min-w-[24rem]">
          <div className="flex flex-wrap gap-2">
            {onBackToBrowse ? <Button variant="outline" onClick={onBackToBrowse}>{backLabel}</Button> : null}
            {(summaryExpanded || summaryHighlightCount > 0) && (
              <Button variant="outline" onClick={onSummaryToggle}>
                <ChevronRight
                  className={`h-4 w-4 transition-transform ${
                    summaryExpanded ? 'rotate-90' : 'rotate-0'
                  }`}
                />
                {summaryExpanded ? 'Hide Highlights' : `Show ${summaryHighlightCount} Highlights`}
              </Button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={diffsOnlyEnabled}
                disabled={!canCompareDifferences}
                onChange={(event) => onDiffOnlyToggle(event.target.checked)}
              />
              <span className="select-none">Differences only</span>
            </label>
            <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={diffsEnabled}
                disabled={!canCompareDifferences}
                onChange={(event) => onDiffToggle(event.target.checked)}
              />
              <span className="select-none">Highlight differences</span>
            </label>
          </div>

          {!canCompareDifferences && (
            <p className="text-xs text-slate-500">
              Unhide or add another simulation to compare differences.
            </p>
          )}
        </div>
      </div>
    </section>
  );
};

export default CompareToolbar;
