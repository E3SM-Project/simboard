import { ArrowUpDown, ChevronDown, ChevronUp } from 'lucide-react';
import type { ThHTMLAttributes } from 'react';

import { TableHead } from '@/components/ui/table';

export type SortDirection = 'asc' | 'desc' | false;

interface SortableTableHeadProps
  extends Omit<ThHTMLAttributes<HTMLTableCellElement>, 'children' | 'onClick' | 'aria-sort'> {
  label: string;
  direction: SortDirection;
  onSort: () => void;
}

/** Table header cell with a sort button that exposes the current direction via `aria-sort`. */
export const SortableTableHead = ({ label, direction, onSort, ...props }: SortableTableHeadProps) => {
  const ariaSort = direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : undefined;
  const Icon = direction === 'asc' ? ChevronUp : direction === 'desc' ? ChevronDown : ArrowUpDown;

  return (
    <TableHead aria-sort={ariaSort} {...props}>
      <button
        type="button"
        className="inline-flex select-none items-center gap-1 rounded-sm text-left hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        onClick={onSort}
        aria-label={`Sort by ${label}, currently ${ariaSort ?? 'not sorted'}`}
      >
        {label}
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      </button>
    </TableHead>
  );
};
