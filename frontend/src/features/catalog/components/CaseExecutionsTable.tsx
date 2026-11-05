import { ArrowUpDown, ChevronDown, ChevronUp } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { TableCellText } from '@/components/ui/table-cell-text';
import {
  type ExecutionDateSort,
  formatExecutionDateRange,
  formatExecutionDuration,
} from '@/features/catalog/caseUtils';
import { ExecutionMetadataDetails } from '@/features/catalog/components/ExecutionMetadataDetails';
import {
  type ExecutionCandidate,
  formatRunDateRange,
  getExecutionDiscoveryContext,
  knownExecutionValue,
  MAX_CASE_EXECUTIONS,
} from '@/lib/catalog/executionDiscovery';
import { executionDetailsPath, type ReadableCaseIdentity } from '@/lib/catalog/urls';

const OPTIONAL_COLUMNS = [
  { key: 'initializationType', label: 'Initialization', width: 144, sortKey: 'initialization' },
  { key: 'machineName', label: 'Machine', width: 112, sortKey: 'machine' },
  { key: 'compsetAlias', label: 'Compset Alias', width: 160 },
  { key: 'compsetLongName', label: 'Compset Long Name', width: 240 },
  { key: 'gridAlias', label: 'Grid Alias', width: 160 },
  { key: 'gridLongName', label: 'Grid Long Name', width: 240 },
] as const;

export type ExecutionColumnKey = (typeof OPTIONAL_COLUMNS)[number]['key'];

export const ExecutionColumnsMenu = ({
  visibleColumns,
  onToggle,
}: {
  visibleColumns: ExecutionColumnKey[];
  onToggle: (key: ExecutionColumnKey) => void;
}) => (
  <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <Button variant="outline" size="sm">
        Columns
        <ChevronDown className="h-3.5 w-3.5" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent
      align="end"
      aria-label="Execution columns"
      className="data-[state=closed]:!animate-none"
    >
      {OPTIONAL_COLUMNS.map((column) => (
        <DropdownMenuCheckboxItem
          key={column.key}
          checked={visibleColumns.includes(column.key)}
          onCheckedChange={() => onToggle(column.key)}
          onSelect={(event) => event.preventDefault()}
        >
          {column.label}
        </DropdownMenuCheckboxItem>
      ))}
    </DropdownMenuContent>
  </DropdownMenu>
);

export const CaseExecutionsTable = ({
  executions,
  discovery,
  visibleColumns,
  selectedIds,
  onToggleSelection,
  sort,
  onSort,
  identity,
  from,
}: {
  executions: ExecutionCandidate[];
  discovery: ReturnType<typeof getExecutionDiscoveryContext>;
  visibleColumns: ExecutionColumnKey[];
  selectedIds: string[];
  onToggleSelection: (id: string) => void;
  sort: ExecutionDateSort;
  onSort: (key: ExecutionDateSort['key']) => void;
  identity: ReadableCaseIdentity;
  from: string;
}) => {
  const columns = OPTIONAL_COLUMNS.filter((column) => visibleColumns.includes(column.key));

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-background [&>div]:max-h-[28rem]">
      <Table
        className="table-fixed"
        style={{ minWidth: 768 + columns.reduce((width, column) => width + column.width, 0) }}
      >
        <colgroup>
          <col style={{ width: 64 }} />
          <col style={{ width: 208 }} />
          <col style={{ width: 112 }} />
          <col style={{ width: 176 }} />
          <col style={{ width: 208 }} />
          {columns.map((column) => (
            <col key={column.key} style={{ width: column.width }} />
          ))}
        </colgroup>
        <TableHeader className="sticky top-0 z-10 bg-slate-50">
          <TableRow>
            <TableHead>Select</TableHead>
            <ExecutionSortHeader
              label="Simulation dates"
              sortKey="simulation"
              sort={sort}
              onSort={onSort}
            />
            <TableHead title="Simulated duration">Duration</TableHead>
            <ExecutionSortHeader label="Run dates" sortKey="run" sort={sort} onSort={onSort} />
            <ExecutionSortHeader
              label="Execution ID"
              sortKey="executionId"
              sort={sort}
              onSort={onSort}
            />
            {columns.map((column) =>
              'sortKey' in column ? (
                <ExecutionSortHeader
                  key={column.key}
                  label={column.label}
                  sortKey={column.sortKey}
                  sort={sort}
                  onSort={onSort}
                />
              ) : (
                <TableHead key={column.key}>{column.label}</TableHead>
              ),
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {executions.map((candidate) => {
            const { summary, details } = candidate;
            const selected = selectedIds.includes(summary.id);

            return (
              <TableRow key={summary.id}>
                <TableCell className="align-top">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      checked={selected}
                      disabled={!selected && selectedIds.length >= MAX_CASE_EXECUTIONS}
                      onCheckedChange={() => onToggleSelection(summary.id)}
                      aria-label={`Select ${summary.executionId} for compare`}
                    />
                    <ExecutionMetadataDetails candidate={candidate} discovery={discovery} />
                  </div>
                </TableCell>
                <TableCell className="whitespace-nowrap align-top">
                  {formatExecutionDateRange(summary)}
                </TableCell>
                <TableCell className="align-top">{formatExecutionDuration(summary)}</TableCell>
                <TableCell className="align-top">
                  <span title={`${details?.runStartDate ?? '—'} → ${details?.runEndDate ?? '—'}`}>
                    {formatRunDateRange(details?.runStartDate, details?.runEndDate)}
                  </span>
                </TableCell>
                <TableCell className="align-top">
                  <Link
                    to={executionDetailsPath({ ...identity, executionId: summary.executionId })}
                    state={{ from }}
                    className="block font-mono text-xs text-blue-600 hover:underline"
                  >
                    <TableCellText value={summary.executionId} lines={2} />
                  </Link>
                </TableCell>
                {columns.map((column) => (
                  <TableCell key={column.key} className="align-top">
                    <TableCellText value={knownExecutionValue(details?.[column.key])} lines={2} />
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
};

const ExecutionSortHeader = ({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  sortKey: ExecutionDateSort['key'];
  sort: ExecutionDateSort;
  onSort: (key: ExecutionDateSort['key']) => void;
}) => {
  const direction =
    sort.key === sortKey ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none';
  const Icon =
    direction === 'none' ? ArrowUpDown : direction === 'ascending' ? ChevronUp : ChevronDown;

  return (
    <TableHead aria-sort={direction === 'none' ? undefined : direction}>
      <button
        type="button"
        className="inline-flex items-center gap-1 rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        onClick={() => onSort(sortKey)}
        aria-label={`Sort by ${label}, currently ${direction === 'none' ? 'not sorted' : direction}`}
      >
        {label}
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      </button>
    </TableHead>
  );
};
