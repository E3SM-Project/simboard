import { ChevronDown } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  type ExecutionCandidate,
  getExecutionDiscoveryContext,
  getExecutionSummary,
  matchesExecutionSearch,
  MAX_CASE_EXECUTIONS,
  toggleCaseExecution,
} from '@/lib/catalog/executionDiscovery';
import { compareModelDates } from '@/utils/utils';

export const ExecutionPicker = ({
  executions,
  selectedIds,
  onSelectionChange,
  loadMore,
  loadingMore,
}: {
  executions: ExecutionCandidate[];
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
  loadMore?: () => void;
  loadingMore?: boolean;
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('simulation-asc');
  const discovery = useMemo(() => getExecutionDiscoveryContext(executions), [executions]);
  const options = useMemo(() => {
    const direction = sort.endsWith('asc') ? 1 : -1;
    return executions
      .filter((candidate) => matchesExecutionSearch(candidate, discovery, query))
      .sort((left, right) => {
        let comparison;
        if (sort.startsWith('simulation')) {
          comparison = compareModelDates(
            left.summary.simulationStartDate,
            right.summary.simulationStartDate,
          );
        } else {
          const leftDate = left.details?.runEndDate ?? left.details?.runStartDate;
          const rightDate = right.details?.runEndDate ?? right.details?.runStartDate;
          if (!leftDate && rightDate) return 1;
          if (leftDate && !rightDate) return -1;
          comparison = (leftDate ?? '').localeCompare(rightDate ?? '');
        }
        return comparison * direction || left.summary.id.localeCompare(right.summary.id);
      });
  }, [executions, discovery, query, sort]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size="sm" className="shrink-0">
          Edit executions ({selectedIds.length}/{MAX_CASE_EXECUTIONS})
          <ChevronDown className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        aria-label="Select executions"
        className="z-[60] flex max-h-[min(36rem,var(--radix-popover-content-available-height))] w-[26rem] max-w-[calc(100vw-2rem)] flex-col gap-3 data-[state=closed]:!animate-none"
        onEscapeKeyDown={(event) => event.stopPropagation()}
      >
        <p className="text-sm font-semibold">Select executions</p>
        <Input
          aria-label="Search execution candidates"
          placeholder="Search executions"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault();
              event.currentTarget
                .closest('[role="dialog"]')
                ?.querySelector<HTMLButtonElement>('[role="checkbox"]:not(:disabled)')
                ?.focus();
            }
          }}
        />
        <select
          aria-label="Sort execution candidates"
          value={sort}
          onChange={(event) => setSort(event.target.value)}
          className="h-8 rounded-md border bg-background px-2 text-xs"
        >
          <option value="simulation-asc">Simulation date: earliest first</option>
          <option value="simulation-desc">Simulation date: latest first</option>
          <option value="run-desc">Run date: latest first</option>
          <option value="run-asc">Run date: earliest first</option>
        </select>
        <div
          className="min-h-0 overflow-y-auto"
          role="group"
          aria-label="Execution candidates"
          onKeyDown={(event) => {
            if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
            const checkboxes = [
              ...event.currentTarget.querySelectorAll<HTMLButtonElement>(
                '[role="checkbox"]:not(:disabled)',
              ),
            ];
            const current = checkboxes.indexOf(event.target as HTMLButtonElement);
            const index =
              event.key === 'Home'
                ? 0
                : event.key === 'End'
                  ? checkboxes.length - 1
                  : current + (event.key === 'ArrowDown' ? 1 : -1);
            const next = checkboxes[Math.max(0, Math.min(index, checkboxes.length - 1))];
            if (next) {
              event.preventDefault();
              next.focus({ preventScroll: true });
              next.scrollIntoView({ block: 'nearest' });
            }
          }}
        >
          {options.map((candidate) => {
            const summary = getExecutionSummary(candidate, discovery);
            const checked = selectedIds.includes(candidate.summary.id);
            return (
              <label
                key={candidate.summary.id}
                className="flex cursor-pointer items-start gap-2 border-b py-3 text-xs last:border-0 has-[:disabled]:cursor-default has-[:disabled]:opacity-60"
              >
                <Checkbox
                  className="mt-0.5 shrink-0"
                  checked={checked}
                  disabled={!checked && selectedIds.length >= MAX_CASE_EXECUTIONS}
                  onCheckedChange={() =>
                    onSelectionChange(toggleCaseExecution(selectedIds, candidate.summary.id))
                  }
                  aria-label={`Compare ${summary.executionId}`}
                  aria-describedby="execution-picker-help"
                />
                <span className="min-w-0">
                  <span
                    className="block truncate font-mono font-medium text-blue-700"
                    title={summary.executionId}
                  >
                    {summary.executionId}
                  </span>
                  <span className="block">Simulation: {summary.simulationPeriod}</span>
                  {summary.context ? (
                    <span className="mt-0.5 block truncate text-slate-500" title={summary.context}>
                      {summary.context}
                    </span>
                  ) : null}
                </span>
              </label>
            );
          })}
          {options.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">No executions match this search.</p>
          ) : null}
        </div>
        {loadMore ? (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              All executions listed. Run-date and metadata search cover loaded metadata only.
            </p>
            <Button variant="outline" size="sm" disabled={loadingMore} onClick={loadMore}>
              {loadingMore ? 'Loading metadata…' : 'Load more metadata'}
            </Button>
          </div>
        ) : null}
        <div className="flex items-center justify-between gap-2">
          <p
            id="execution-picker-help"
            className="text-xs text-muted-foreground"
            aria-live="polite"
          >
            {selectedIds.length >= MAX_CASE_EXECUTIONS
              ? `Limit: ${MAX_CASE_EXECUTIONS} executions. Remove one to add another.`
              : 'Select 2–5 executions. Changes apply immediately.'}
          </p>
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
            Done
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
};
