import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  List,
  Search,
  SlidersHorizontal,
} from 'lucide-react';
import { useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
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

const SortHeader = ({
  children,
  sortKey,
  activeSortKey,
  sortDirection,
  onSort,
}: {
  children: string;
  sortKey: ArtifactSortKey;
  activeSortKey: ArtifactSortKey;
  sortDirection: SortDirection;
  onSort: (sortKey: ArtifactSortKey) => void;
}) => {
  const isActive = activeSortKey === sortKey;
  const directionLabel = !isActive
    ? 'not sorted'
    : sortDirection === 'asc'
      ? 'ascending'
      : 'descending';

  return (
    <button
      type="button"
      className="inline-flex items-center gap-1 rounded-sm text-left hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      onClick={() => onSort(sortKey)}
      aria-label={`Sort by ${children}, currently ${directionLabel}`}
    >
      {children}
      {isActive ? (
        sortDirection === 'asc' ? (
          <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
        )
      ) : (
        <SlidersHorizontal className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
      )}
    </button>
  );
};

export const CaseArtifactsTable = ({
  artifacts,
  totalArtifactCount,
  onFilterExecutionIds,
}: {
  artifacts: CaseArtifactValue[];
  totalArtifactCount: number;
  onFilterExecutionIds: (executionIds: string[]) => void;
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

  const getAriaSort = (headerSortKey: ArtifactSortKey) =>
    sortKey === headerSortKey ? (sortDirection === 'asc' ? 'ascending' : 'descending') : undefined;

  return (
    <section className="space-y-4" aria-labelledby="artifacts-heading">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <h3 id="artifacts-heading" className="text-lg font-semibold text-slate-950">
            Artifacts
          </h3>
          <p className="text-sm text-slate-500">
            {totalArtifactCount} records · {artifacts.length} unique values
          </p>
        </div>
        <p className="text-sm text-slate-500">Unique values mapped to executions.</p>
      </div>

      {artifacts.length > 0 ? (
        <>
          <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50/70 p-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search artifact names or paths"
                className="bg-white pl-9"
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
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
              <Table className="min-w-[680px]">
                <TableHeader className="bg-slate-50">
                  <TableRow className="hover:bg-slate-50">
                    <TableHead className="w-40 bg-slate-50" aria-sort={getAriaSort('kind')}>
                      <SortHeader
                        activeSortKey={sortKey}
                        onSort={handleSort}
                        sortDirection={sortDirection}
                        sortKey="kind"
                      >
                        Type
                      </SortHeader>
                    </TableHead>
                    <TableHead className="bg-slate-50" aria-sort={getAriaSort('artifact')}>
                      <SortHeader
                        activeSortKey={sortKey}
                        onSort={handleSort}
                        sortDirection={sortDirection}
                        sortKey="artifact"
                      >
                        Artifact
                      </SortHeader>
                    </TableHead>
                    <TableHead className="w-48 bg-slate-50" aria-sort={getAriaSort('executions')}>
                      <SortHeader
                        activeSortKey={sortKey}
                        onSort={handleSort}
                        sortDirection={sortDirection}
                        sortKey="executions"
                      >
                        Executions
                      </SortHeader>
                    </TableHead>
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
                                className="truncate font-medium text-slate-950"
                                title={displayName}
                              >
                                {displayName}
                              </p>
                              {isExternal ? (
                                <a
                                  href={artifact.uri}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="shrink-0 text-slate-500 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                                  aria-label={`Open ${displayName} in a new tab`}
                                  title="Open in a new tab"
                                >
                                  <ExternalLink className="h-3.5 w-3.5" />
                                </a>
                              ) : null}
                            </div>
                            <code
                              className="block truncate text-xs text-slate-600"
                              title={artifact.uri}
                            >
                              {artifact.uri}
                            </code>
                          </div>
                        </TableCell>
                        <TableCell className="align-top">
                          <div className="flex items-center gap-1.5">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-8 whitespace-nowrap"
                              onClick={() => onFilterExecutionIds(artifact.executionIds)}
                              aria-label={`Filter executions linked to ${displayName}`}
                            >
                              {artifact.executionIds.length}{' '}
                              {artifact.executionIds.length === 1 ? 'execution' : 'executions'}
                            </Button>
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
                                <p className="text-sm font-medium text-slate-950">
                                  Linked executions
                                </p>
                                <ul className="mt-2 max-h-56 space-y-1 overflow-y-auto">
                                  {artifact.executionIds.map((executionId) => (
                                    <li key={executionId}>
                                      <code className="block rounded bg-slate-100 px-2 py-1 font-mono text-xs text-slate-800">
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
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/40 px-6 py-10 text-center">
              <p className="text-sm font-medium text-slate-900">
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
        <p className="text-sm text-slate-500">No execution artifacts available.</p>
      )}
    </section>
  );
};
