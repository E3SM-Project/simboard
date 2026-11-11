import { ExternalLink, List, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { SortableTableHead } from '@/components/ui/sortable-table-head';
import { Table, TableBody, TableCell, TableHeader, TableRow } from '@/components/ui/table';
import type { ArtifactKind } from '@/types/artifact';

export interface CaseArtifactValue {
  id: string;
  kind: ArtifactKind;
  uri: string;
  label: string | null;
  executionIds: string[];
}

interface ArtifactKindMeta {
  title: string;
  badgeClassName: string;
}

type ArtifactSortKey = 'kind' | 'artifact' | 'executions';
type SortDirection = 'asc' | 'desc';
type ArtifactKindFilter = ArtifactKind | 'all';

const ARTIFACT_KIND_META: Record<ArtifactKind, ArtifactKindMeta> = {
  output: {
    title: 'Output',
    badgeClassName: 'border-sky-200 bg-sky-50 text-sky-800',
  },
  archive: {
    title: 'Archive',
    badgeClassName: 'border-violet-200 bg-violet-50 text-violet-800',
  },
  run_script: {
    title: 'Run script',
    badgeClassName: 'border-amber-200 bg-amber-50 text-amber-800',
  },
  postprocessing_script: {
    title: 'Post-processing script',
    badgeClassName: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  },
};

const ARTIFACT_KIND_ORDER: ArtifactKind[] = [
  'output',
  'archive',
  'run_script',
  'postprocessing_script',
];

const isExternalArtifactUri = (uri: string) =>
  uri.startsWith('http://') || uri.startsWith('https://') || uri.startsWith('file:');

const getArtifactFilename = (uri: string) => {
  const segments = uri.split('/').filter(Boolean);
  return segments.at(-1) ?? uri;
};

const getArtifactDisplayName = (artifact: CaseArtifactValue) =>
  artifact.label?.trim() || getArtifactFilename(artifact.uri);

const sortArtifacts = (
  artifacts: CaseArtifactValue[],
  sortKey: ArtifactSortKey,
  sortDirection: SortDirection,
) => {
  const multiplier = sortDirection === 'asc' ? 1 : -1;

  return [...artifacts].sort((left, right) => {
    let comparison = 0;
    if (sortKey === 'kind') {
      comparison = ARTIFACT_KIND_ORDER.indexOf(left.kind) - ARTIFACT_KIND_ORDER.indexOf(right.kind);
      if (comparison === 0) {
        comparison = getArtifactDisplayName(left).localeCompare(getArtifactDisplayName(right));
      }
    } else if (sortKey === 'artifact') {
      comparison = getArtifactDisplayName(left).localeCompare(getArtifactDisplayName(right));
    } else {
      comparison = left.executionIds.length - right.executionIds.length;
      if (comparison === 0) {
        comparison = getArtifactDisplayName(left).localeCompare(getArtifactDisplayName(right));
      }
    }

    return comparison * multiplier;
  });
};

export const CaseArtifactsTable = ({
  artifacts,
  totalArtifactCount,
}: {
  artifacts: CaseArtifactValue[];
  totalArtifactCount: number;
}) => {
  const [query, setQuery] = useState('');
  const [kindFilter, setKindFilter] = useState<ArtifactKindFilter>('all');
  const [sortKey, setSortKey] = useState<ArtifactSortKey>('kind');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  const visibleArtifacts = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const filtered = artifacts.filter((artifact) => {
      if (kindFilter !== 'all' && artifact.kind !== kindFilter) return false;
      if (normalizedQuery.length === 0) return true;

      return [artifact.uri, artifact.label ?? '', getArtifactFilename(artifact.uri)]
        .join(' ')
        .toLowerCase()
        .includes(normalizedQuery);
    });

    return sortArtifacts(filtered, sortKey, sortDirection);
  }, [artifacts, kindFilter, query, sortDirection, sortKey]);

  const handleSort = (nextSortKey: ArtifactSortKey) => {
    if (nextSortKey === sortKey) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
      return;
    }

    setSortKey(nextSortKey);
    setSortDirection('asc');
  };

  return (
    <details className="space-y-4" aria-labelledby="artifacts-heading">
      <summary className="cursor-pointer rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
        <h3 id="artifacts-heading" className="inline text-lg font-semibold text-foreground">
          Artifacts
        </h3>
        <span className="ml-2 text-sm text-muted-foreground">
          {totalArtifactCount} records · {artifacts.length} unique values
        </span>
      </summary>
      <p className="text-sm text-muted-foreground">
        Files, directories, and scripts recorded for executions in this case. Each row shows a
        unique value and its linked executions.
      </p>

      {artifacts.length > 0 ? (
        <>
          <div className="flex flex-col gap-3 rounded-xl border border-border bg-muted-subtle/70 p-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search artifact names or paths"
                className="bg-card pl-9"
                aria-label="Search artifact names or paths"
              />
            </div>
            <div className="flex flex-wrap gap-1.5" aria-label="Filter artifacts by type">
              <Button
                type="button"
                size="sm"
                variant={kindFilter === 'all' ? 'default' : 'outline'}
                onClick={() => setKindFilter('all')}
                aria-pressed={kindFilter === 'all'}
              >
                All
              </Button>
              {ARTIFACT_KIND_ORDER.map((kind) => (
                <Button
                  key={kind}
                  type="button"
                  size="sm"
                  variant={kindFilter === kind ? 'default' : 'outline'}
                  onClick={() => setKindFilter(kind)}
                  aria-pressed={kindFilter === kind}
                >
                  {ARTIFACT_KIND_META[kind].title}
                </Button>
              ))}
            </div>
          </div>

          {visibleArtifacts.length > 0 ? (
            <div className="overflow-hidden rounded-xl border border-border bg-card [&>div]:max-h-[28rem]">
              <Table className="min-w-[680px]">
                <TableHeader className="bg-muted-subtle">
                  <TableRow className="hover:bg-muted-subtle">
                    <SortableTableHead
                      className="sticky top-0 z-10 w-40 bg-muted-subtle"
                      label="Type"
                      direction={sortKey === 'kind' && sortDirection}
                      onSort={() => handleSort('kind')}
                    />
                    <SortableTableHead
                      className="sticky top-0 z-10 bg-muted-subtle"
                      label="Artifact"
                      direction={sortKey === 'artifact' && sortDirection}
                      onSort={() => handleSort('artifact')}
                    />
                    <SortableTableHead
                      className="sticky top-0 z-10 w-48 bg-muted-subtle"
                      label="Executions"
                      direction={sortKey === 'executions' && sortDirection}
                      onSort={() => handleSort('executions')}
                    />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleArtifacts.map((artifact) => {
                    const displayName = getArtifactDisplayName(artifact);
                    const isExternal = isExternalArtifactUri(artifact.uri);

                    return (
                      <TableRow key={artifact.id}>
                        <TableCell className="align-top">
                          <Badge
                            variant="outline"
                            className={ARTIFACT_KIND_META[artifact.kind].badgeClassName}
                          >
                            {ARTIFACT_KIND_META[artifact.kind].title}
                          </Badge>
                        </TableCell>
                        <TableCell className="min-w-0 align-top">
                          <div className="min-w-0 space-y-1">
                            <div className="flex min-w-0 items-center gap-1.5">
                              <p
                                className="truncate font-medium text-foreground"
                                title={displayName}
                              >
                                {displayName}
                              </p>
                              {isExternal ? (
                                <a
                                  href={artifact.uri}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="shrink-0 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                                  aria-label={`Open ${displayName} in a new tab`}
                                  title="Open in a new tab"
                                >
                                  <ExternalLink className="h-3.5 w-3.5" />
                                </a>
                              ) : null}
                            </div>
                            <code
                              className="block truncate text-xs text-muted-foreground"
                              title={artifact.uri}
                            >
                              {artifact.uri}
                            </code>
                          </div>
                        </TableCell>
                        <TableCell className="align-top">
                          <div className="flex items-center gap-1.5">
                            <span className="min-w-6 text-sm tabular-nums">
                              {artifact.executionIds.length}
                            </span>
                            <Popover>
                              <PopoverTrigger asChild>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8"
                                  aria-label={`Show execution IDs for ${displayName}`}
                                  title="Show linked execution IDs"
                                >
                                  <List className="h-4 w-4" />
                                </Button>
                              </PopoverTrigger>
                              <PopoverContent align="start" className="w-80 p-3">
                                <p className="text-sm font-medium text-foreground">
                                  Linked executions
                                </p>
                                <ul className="mt-2 max-h-56 space-y-1 overflow-y-auto">
                                  {artifact.executionIds.map((executionId) => (
                                    <li key={executionId}>
                                      <code className="block rounded bg-muted px-2 py-1 font-mono text-xs text-foreground">
                                        {executionId}
                                      </code>
                                    </li>
                                  ))}
                                </ul>
                              </PopoverContent>
                            </Popover>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border bg-muted-subtle/40 px-6 py-10 text-center">
              <p className="text-sm font-medium text-foreground">
                No artifacts match these filters.
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => {
                  setQuery('');
                  setKindFilter('all');
                }}
              >
                Reset filters
              </Button>
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-muted-foreground">No execution artifacts available.</p>
      )}
    </details>
  );
};
