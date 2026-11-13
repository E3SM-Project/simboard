import type { UseQueryResult } from '@tanstack/react-query';
import axios from 'axios';
import type { LucideIcon } from 'lucide-react';
import { type ReactNode, useId } from 'react';

import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { LoadingState } from '@/components/ui/loading-state';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';

interface OperationsSectionProps<T> {
  title: string;
  description: string;
  icon: LucideIcon;
  query: Pick<UseQueryResult<T>, 'data' | 'error' | 'isError' | 'isFetching' | 'refetch'>;
  badge?: (data: T) => ReactNode;
  children: (data: T) => ReactNode;
  className?: string;
}

/** Bordered dashboard section that loads, refreshes, and fails independently. */
export const OperationsSection = <T,>({
  title,
  description,
  icon: Icon,
  query,
  badge,
  children,
  className,
}: OperationsSectionProps<T>) => {
  const headingId = useId();
  const { data, isError, isFetching } = query;
  const errorDetail = getErrorDetail(query.error);
  const retry = (
    <Button type="button" size="sm" variant="outline" onClick={() => void query.refetch()}>
      Retry
    </Button>
  );

  return (
    <section
      aria-labelledby={headingId}
      className={cn('min-w-0 rounded-2xl border border-border bg-card p-4 shadow-sm', className)}
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Icon className="mt-1 h-5 w-5 shrink-0 text-muted-foreground" />
          <div>
            <h2 id={headingId} className="text-lg font-semibold">
              {title}
            </h2>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
        </div>
        {data !== undefined ? (
          <div className="flex items-center gap-3">
            {isFetching ? <LoadingState kind="inline" label="Refreshing" /> : null}
            {badge?.(data)}
          </div>
        ) : null}
      </div>

      {data !== undefined && isError ? (
        <Alert variant="error" className="mb-4 flex items-center justify-between gap-3">
          <span>Could not refresh {title.toLowerCase()}. Showing previously loaded data.</span>
          {retry}
        </Alert>
      ) : null}

      {data !== undefined ? (
        children(data)
      ) : isError ? (
        <Alert variant="error" className="rounded-xl p-6 text-center">
          <p className="mb-3">
            Could not load {title.toLowerCase()}.{errorDetail ? ` ${errorDetail}` : null}
          </p>
          {retry}
        </Alert>
      ) : (
        <LoadingState kind="section" label={`Loading ${title.toLowerCase()}`} />
      )}
    </section>
  );
};

/** Return the API's message, such as "Site 'X' not found.", when it sent one. */
const getErrorDetail = (error: unknown) => {
  const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;

  return typeof detail === 'string' ? detail : null;
};

/** Section total; hidden at zero because the empty state already says so. */
export const CountPill = ({ count, label }: { count: number; label: string }) =>
  count > 0 ? (
    <span
      aria-live="polite"
      className="whitespace-nowrap rounded-full bg-muted px-3 py-1 text-xs font-medium text-foreground"
    >
      {count} {label}
    </span>
  ) : null;

interface OperationsTableProps {
  columns: { label: string; className?: string }[];
  children: ReactNode;
  className?: string;
}

/** Height-limited table with a sticky header. */
export const OperationsTable = ({ columns, children, className }: OperationsTableProps) => (
  <div className="overflow-hidden rounded-xl border border-border [&>div]:max-h-[24rem]">
    <Table className={className}>
      <TableHeader className="bg-muted-subtle">
        <TableRow className="hover:bg-muted-subtle">
          {columns.map(({ label, className: columnClassName }) => (
            <TableHead
              key={label}
              className={cn('sticky top-0 z-10 bg-muted-subtle', columnClassName)}
            >
              {label}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>{children}</TableBody>
    </Table>
  </div>
);

// Empty states explain filtered results; the page header holds the one Reset control.

/** Dashed block for a section with nothing to show. */
export const EmptyPanel = ({ message }: { message: string }) => (
  <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
    {message}
  </div>
);

export const EmptyRow = ({ colSpan, message }: { colSpan: number; message: string }) => (
  <TableRow className="hover:bg-transparent">
    <TableCell colSpan={colSpan} className="py-6 text-center text-muted-foreground">
      {message}
    </TableCell>
  </TableRow>
);
