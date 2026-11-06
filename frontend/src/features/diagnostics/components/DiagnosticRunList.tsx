import { Check, ExternalLink, Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  diagnosticClimatologyPeriod,
  diagnosticIdentifier,
  diagnosticPeriod,
  diagnosticTimeSeriesPeriod,
  diagnosticTitle,
  periodGroups,
  RUN_GROUPS,
  runGroup,
} from '@/features/diagnostics/discoveryState';
import type { DiagnosticsRunOut, DiagnosticsSourceOut } from '@/features/diagnostics/types';
import { cn } from '@/lib/utils';

const ANALYSES = [
  {
    key: 'all',
    label: 'All',
    description: 'Grouped by climatology years when available; otherwise time-series years.',
  },
  { key: 'climatology', label: 'Climatology', description: 'Grouped by climatology years.' },
  { key: 'time_series', label: 'Time Series', description: 'Grouped by time-series years.' },
] as const;

export interface DiagnosticRunListProps {
  sources: DiagnosticsSourceOut[];
  id: string;
  isAdded: (url: string) => boolean;
  onAdd: (run: DiagnosticsRunOut) => void;
  onRemove: (url: string) => void;
}

/** Shared discovery presentation; callers own staging or workspace drafts. */
export const DiagnosticRunList = ({ sources, id, ...actions }: DiagnosticRunListProps) => (
  <div className="min-w-0 space-y-3">
    <div className="space-y-2">
      {sources.map((source, index) => (
        <section
          key={source.rootUrl}
          id={`${id}-source-${index}`}
          tabIndex={-1}
          className="scroll-mt-20 rounded focus-visible:ring-2 focus-visible:ring-ring"
        >
          {/* Preserve existing resource shortcuts and bookmarked tool-group anchors. */}
          {[...new Set(source.runs.map(runGroup))].map((group) => (
            <span
              key={group}
              id={`${id}-source-${index}-${group}`}
              tabIndex={-1}
              role="group"
              aria-label={`${RUN_GROUPS.find((item) => item.key === group)?.title ?? group} in ${source.label || 'diagnostics directory'}; runs grouped by period below`}
              className="block scroll-mt-20 rounded focus-visible:ring-2 focus-visible:ring-ring"
            />
          ))}
          <a
            href={source.rootUrl}
            target="_blank"
            rel="noreferrer"
            title={source.rootUrl}
            className="inline-flex max-w-full items-center gap-1 rounded text-xs font-medium text-slate-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="min-w-0 break-words [overflow-wrap:anywhere]">
              {source.label || 'Browse diagnostics directory'}
            </span>
            <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
          {source.error ? (
            <p className="text-sm text-amber-800">
              {source.error === 'url_not_allowed'
                ? 'This directory is not on a supported public diagnostics server.'
                : 'This directory could not be read. Browse the original output or try again.'}
            </p>
          ) : null}
          {source.partial ? (
            <p className="text-xs text-amber-700">
              Some runs may be missing: part of the archive could not be read.
            </p>
          ) : null}
        </section>
      ))}
    </div>
    <Tabs defaultValue="all">
      <TabsList
        aria-label="Filter diagnostics by analysis"
        className="grid w-full max-w-sm grid-cols-3"
      >
        {ANALYSES.map((analysis) => (
          <TabsTrigger key={analysis.key} value={analysis.key} className="px-2 text-xs">
            {analysis.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {ANALYSES.map((analysis) => {
        const groups = periodGroups(sources, analysis.key);

        return (
          <TabsContent key={analysis.key} value={analysis.key} className="space-y-3">
            <p className="text-xs text-slate-500">
              {analysis.description} Selecting a run includes all its analyses.
            </p>
            {!groups.length &&
            analysis.key !== 'all' &&
            sources.some((source) => source.runs.length) ? (
              <p role="status" className="text-sm text-slate-500">
                No runs have indexed{' '}
                {analysis.key === 'climatology' ? 'climatology' : 'time-series'} years. Check All
                for other runs.
              </p>
            ) : null}
            {groups.map(([period, runs], index) => (
              <section key={period} aria-labelledby={`${id}-${analysis.key}-period-${index}`}>
                <h4
                  id={`${id}-${analysis.key}-period-${index}`}
                  className="mb-1.5 flex items-center gap-2 border-b pb-1.5 text-sm font-semibold text-slate-900"
                >
                  {period}
                  <span className="text-xs font-normal text-slate-500">{runs.length} runs</span>
                </h4>
                <ul className="space-y-1">
                  {runs.map((run) => (
                    <DiagnosticRunRow key={run.url} run={run} {...actions} />
                  ))}
                </ul>
              </section>
            ))}
          </TabsContent>
        );
      })}
    </Tabs>
  </div>
);

const DiagnosticRunRow = ({
  run,
  isAdded,
  onAdd,
  onRemove,
}: Pick<DiagnosticRunListProps, 'isAdded' | 'onAdd' | 'onRemove'> & {
  run: DiagnosticsRunOut;
}) => {
  const selected = isAdded(run.url);
  const title = diagnosticTitle(run);
  const identifier = diagnosticIdentifier(run);
  const tool = run.tool === 'e3sm_diags' ? 'E3SM Diags' : 'MPAS-Analysis';
  const climatology = diagnosticClimatologyPeriod(run);
  const timeSeries = diagnosticTimeSeriesPeriod(run);
  const combinedPeriods =
    climatology && timeSeries ? `Climatology: ${climatology} · Time Series: ${timeSeries}` : '';
  const label = `${tool} · ${identifier} · ${title} · ${combinedPeriods || diagnosticPeriod(run)}`;

  return (
    <li
      className={cn(
        'flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 rounded-md border px-2.5 py-2 text-sm',
        selected ? 'border-slate-400 bg-slate-50' : 'border-slate-200 bg-white',
      )}
    >
      <div className="min-w-0 flex-1 basis-48">
        <p className="font-medium text-slate-900">{title}</p>
        <p className="text-xs text-slate-500 [overflow-wrap:anywhere]">
          {tool} · <span>{identifier}</span>
        </p>
        {combinedPeriods ? <p className="text-xs text-slate-500">{combinedPeriods}</p> : null}
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <Button asChild variant="ghost" size="sm" className="h-8 px-2">
          <a
            href={run.url}
            target="_blank"
            rel="noreferrer"
            title={run.url}
            aria-label={`Open ${label} (new tab)`}
          >
            Open <ExternalLink className="ml-1 h-3.5 w-3.5" aria-hidden="true" />
          </a>
        </Button>
        <Button
          type="button"
          variant={selected ? 'secondary' : 'outline'}
          size="sm"
          className="h-8 w-20 px-2"
          aria-pressed={selected}
          aria-label={`${selected ? 'Remove' : 'Add'} ${label}`}
          onClick={() => (selected ? onRemove(run.url) : onAdd(run))}
        >
          {selected ? (
            <Check className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <Plus className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
          )}
          {selected ? 'Added' : 'Add'}
        </Button>
      </div>
    </li>
  );
};
