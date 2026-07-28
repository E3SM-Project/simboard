import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import type { MetadataChangeOut } from '@/types';
import { formatDate } from '@/utils/utils';

interface MetadataHistoryProps {
  entries: MetadataChangeOut[];
  loading?: boolean;
  error?: string | null;
}

interface MetadataChangeEvent {
  key: string;
  entries: MetadataChangeOut[];
  editorName: string;
  changedAt: string;
  reason: string | null;
}

const VALUE_PREVIEW_LENGTH = 80;

const formatFieldName = (value: string) =>
  value
    .split('_')
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ');

const formatValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return 'Empty';
  if (typeof value === 'string') return value;

  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    return String(value);
  }
};

const summarizeValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return 'Empty';
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? '' : 's'}`;
  if (typeof value === 'object') {
    const fieldCount = Object.keys(value).length;
    return `${fieldCount} field${fieldCount === 1 ? '' : 's'}`;
  }

  const formattedValue = String(value);
  return formattedValue.length > VALUE_PREVIEW_LENGTH
    ? `${formattedValue.slice(0, VALUE_PREVIEW_LENGTH)}…`
    : formattedValue;
};

const needsDetails = (value: unknown): boolean =>
  (typeof value === 'string' && value.length > VALUE_PREVIEW_LENGTH) ||
  (typeof value === 'object' && value !== null);

const groupEntries = (entries: MetadataChangeOut[]): MetadataChangeEvent[] => {
  const events = new Map<string, MetadataChangeEvent>();

  entries.forEach((entry) => {
    const key = JSON.stringify([entry.changedAt, entry.editorId, entry.reason]);
    const existingEvent = events.get(key);

    if (existingEvent) {
      existingEvent.entries.push(entry);
      return;
    }

    events.set(key, {
      key,
      entries: [entry],
      editorName: entry.editor.full_name ?? entry.editor.email,
      changedAt: entry.changedAt,
      reason: entry.reason,
    });
  });

  return Array.from(events.values());
};

const ChangeDetailsDialog = ({ entry }: { entry: MetadataChangeOut }) => (
  <Dialog>
    <DialogTrigger asChild>
      <Button variant="link" size="sm" className="h-auto shrink-0 px-1 py-0 text-xs">
        View details
      </Button>
    </DialogTrigger>
    <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>{formatFieldName(entry.fieldName)}</DialogTitle>
        <DialogDescription>Full values before and after this change.</DialogDescription>
      </DialogHeader>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">Previous</p>
          <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 text-xs">
            {formatValue(entry.oldValue)}
          </pre>
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">New</p>
          <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/50 p-3 text-xs">
            {formatValue(entry.newValue)}
          </pre>
        </div>
      </div>
    </DialogContent>
  </Dialog>
);

export const MetadataHistory = ({
  entries,
  loading = false,
  error = null,
}: MetadataHistoryProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const events = groupEntries(entries);
  const canExpand = !loading && !error && events.length > 0;
  const latestEvent = events[0];

  const summary = loading
    ? 'Loading change history…'
    : error
      ? `Could not load change history: ${error}`
      : latestEvent
        ? `${latestEvent.editorName} changed ${latestEvent.entries.length} field${
            latestEvent.entries.length === 1 ? '' : 's'
          } · ${formatDate(latestEvent.changedAt)}`
        : 'No user-managed changes recorded yet.';

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <Card>
        <CardHeader className="p-0">
          <CollapsibleTrigger asChild disabled={!canExpand}>
            <button
              type="button"
              className={cn(
                'flex w-full items-center gap-3 rounded-xl p-5 text-left',
                canExpand &&
                  'transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'
              )}
            >
              <div className="min-w-0 flex-1">
                <CardTitle className="text-base">
                  Change History{events.length > 0 ? ` (${events.length})` : ''}
                </CardTitle>
                <p
                  className={cn(
                    'mt-1 truncate text-sm text-muted-foreground',
                    error && 'text-red-600'
                  )}
                >
                  {summary}
                </p>
              </div>
              {canExpand ? (
                <ChevronDown
                  aria-hidden="true"
                  className={cn(
                    'h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200',
                    isOpen && 'rotate-180'
                  )}
                />
              ) : null}
            </button>
          </CollapsibleTrigger>
        </CardHeader>

        {canExpand ? (
          <CollapsibleContent>
            <CardContent className="border-t p-0">
              <ol className="max-h-96 space-y-3 overflow-y-auto p-4">
                {events.map((event) => (
                  <li key={event.key} className="rounded-lg border border-border/70">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-border/70 px-3 py-2">
                      <p className="text-sm font-medium">
                        {event.editorName} changed {event.entries.length} field
                        {event.entries.length === 1 ? '' : 's'}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatDate(event.changedAt)}
                      </p>
                      {event.reason ? (
                        <p className="w-full text-xs text-muted-foreground">
                          <span className="font-medium text-foreground">Reason:</span>{' '}
                          {event.reason}
                        </p>
                      ) : null}
                    </div>
                    <ul className="divide-y divide-border/70 px-3">
                      {event.entries.map((entry) => (
                        <li
                          key={entry.id}
                          className="grid gap-1 py-2 sm:grid-cols-[minmax(8rem,0.6fr)_minmax(0,1fr)] sm:items-center sm:gap-3"
                        >
                          <p className="text-sm font-medium">
                            {formatFieldName(entry.fieldName)}
                          </p>
                          <div className="flex min-w-0 items-center gap-2">
                            <span className="line-clamp-2 min-w-0 flex-1 break-words rounded bg-muted/40 px-2 py-1 font-mono text-xs">
                              {summarizeValue(entry.oldValue)}
                            </span>
                            <span aria-hidden="true" className="shrink-0 text-muted-foreground">
                              →
                            </span>
                            <span className="line-clamp-2 min-w-0 flex-1 break-words rounded bg-muted/40 px-2 py-1 font-mono text-xs">
                              {summarizeValue(entry.newValue)}
                            </span>
                            {needsDetails(entry.oldValue) || needsDetails(entry.newValue) ? (
                              <ChangeDetailsDialog entry={entry} />
                            ) : null}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ol>
            </CardContent>
          </CollapsibleContent>
        ) : null}
      </Card>
    </Collapsible>
  );
};
