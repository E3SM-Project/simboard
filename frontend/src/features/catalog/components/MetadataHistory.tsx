import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { MetadataChangeOut } from '@/types';
import { formatDate } from '@/utils/utils';

interface MetadataHistoryProps {
  entries: MetadataChangeOut[];
  loading?: boolean;
  error?: string | null;
}

const formatFieldName = (value: string) =>
  value
    .split('_')
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ');

const formatValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return 'Empty';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
};

export const MetadataHistory = ({
  entries,
  loading = false,
  error = null,
}: MetadataHistoryProps) => (
  <Card>
    <CardHeader className="pb-2">
      <CardTitle className="text-base">Change History</CardTitle>
    </CardHeader>
    <CardContent>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading change history…</p>
      ) : error ? (
        <p className="text-sm text-red-600">Could not load change history: {error}</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">No user-managed changes recorded yet.</p>
      ) : (
        <ol className="space-y-3">
          {entries.map((entry) => {
            const editorName = entry.editor.full_name ?? entry.editor.email;
            return (
              <li key={entry.id} className="rounded-lg border border-border/70 p-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-sm font-medium">{formatFieldName(entry.fieldName)}</p>
                  <p className="text-xs text-muted-foreground">
                    {editorName} · {formatDate(entry.changedAt)}
                  </p>
                </div>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <div>
                    <p className="text-xs font-medium text-muted-foreground">Previous</p>
                    <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-muted/40 p-2 text-xs">
                      {formatValue(entry.oldValue)}
                    </pre>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-muted-foreground">New</p>
                    <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-muted/40 p-2 text-xs">
                      {formatValue(entry.newValue)}
                    </pre>
                  </div>
                </div>
                {entry.reason ? (
                  <p className="mt-2 text-sm">
                    <span className="font-medium">Reason:</span> {entry.reason}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}
    </CardContent>
  </Card>
);
