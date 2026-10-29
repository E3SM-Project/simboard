import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Copy, ExternalLink, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { compareRuns } from '@/features/diagnostics/api';
import {
  compareSearch,
  type CompareState,
  displayLabel,
  imageUrl,
  parseCompareState,
} from '@/features/diagnostics/compareState';
import type {
  ComparedPlotOut,
  CompareOut,
  GroupOut,
  PanelOut,
  PanelView,
  SetDetailOut,
} from '@/features/diagnostics/types';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';

const PANEL_LABELS: Record<PanelView, string> = {
  test: 'Run',
  ref: 'Reference',
  diff: 'Difference',
};

/** Pick a group's plot for a season and region, falling back gracefully. */
const pickPlot = (group: GroupOut, season?: string | null, region?: string | null) =>
  group.plots.find((p) => p.season === season && p.region === region) ??
  group.plots.find((p) => p.season === season) ??
  group.plots.find((p) => p.region === region) ??
  group.plots[0];

const unique = (values: (string | null)[]) =>
  [...new Set(values)].filter((v): v is string => Boolean(v));

/**
 * Plots from several diagnostics runs, side by side. The backend decides
 * which plots the runs share; this page only presents them. All state is in
 * the URL, so the address bar is the shareable link.
 */
export const ComparePage = () => {
  const [params, setParams] = useSearchParams();
  const state = useMemo(() => parseCompareState(params), [params]);
  const { toast } = useToast();
  const [filter, setFilter] = useState('');

  const query = useQuery({
    queryKey: ['diagnostics', 'compare', state.runs, state.set],
    queryFn: () => compareRuns(state.runs, state.set),
    enabled: state.runs.length > 0,
    staleTime: 10 * 60_000,
    placeholderData: keepPreviousData,
  });

  const update = useCallback(
    (patch: Partial<CompareState>) =>
      setParams(compareSearch({ ...state, ...patch }), { replace: true }),
    [setParams, state],
  );

  const data = query.data;
  const detail = data?.set ?? null;
  const groups = useMemo(() => detail?.groups ?? [], [detail]);
  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return needle
      ? groups.filter((g) => `${g.title} ${g.reference}`.toLowerCase().includes(needle))
      : groups;
  }, [filter, groups]);

  const activeGroup =
    groups.find((g) => g.plots.some((p) => p.key === state.plot)) ?? groups[0] ?? null;
  const activePlot = activeGroup?.plots.find((p) => p.key === state.plot) ?? activeGroup?.plots[0];
  const views = Object.keys(detail?.panels ?? {}) as PanelView[];
  const view = views.includes(state.view) ? state.view : 'test';

  // Keep the URL naming exactly what is shown.
  useEffect(() => {
    if (detail && activePlot && (state.set !== detail.name || state.plot !== activePlot.key)) {
      update({ set: detail.name, plot: activePlot.key });
    }
  }, [activePlot, detail, state.plot, state.set, update]);

  const step = useCallback(
    (delta: number) => {
      if (!activeGroup || visible.length === 0) return;
      const at = visible.findIndex((g) => g.id === activeGroup.id);
      const next = visible[(at + delta + visible.length) % visible.length];
      update({ plot: pickPlot(next, activePlot?.season, activePlot?.region).key });
    },
    [activeGroup, activePlot, update, visible],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement | null)?.tagName === 'INPUT') return;
      const delta = { ArrowDown: 1, j: 1, ArrowUp: -1, k: -1 }[event.key];
      if (delta) {
        event.preventDefault();
        step(delta);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [step]);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast({ title: 'Link copied' });
    } catch {
      toast({ title: 'Could not copy the link', variant: 'destructive' });
    }
  };

  if (state.runs.length === 0) {
    return (
      <Shell>
        <p className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600">
          Add runs from{' '}
          <Link to="/cases" className="underline">
            case pages
          </Link>{' '}
          or{' '}
          <Link to="/diagnostics" className="underline">
            paste their addresses
          </Link>
          , then choose Compare.
        </p>
      </Shell>
    );
  }

  const failed = data?.runs.filter((r) => r.error) ?? [];

  return (
    <Shell>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-950">Compare diagnostics</h1>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {state.runs.map((run) => (
              <Badge key={run.url} variant="secondary" title={run.url}>
                {displayLabel(run)}
              </Badge>
            ))}
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={copyLink}>
          <Copy className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
          Copy link
        </Button>
      </header>

      {query.isLoading ? (
        <p className="text-sm text-slate-500">Reading each run&apos;s published plots…</p>
      ) : query.isError ? (
        <div className="space-y-2 text-sm text-red-600">
          <p>The diagnostics archive could not be read just now.</p>
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            Try again
          </Button>
        </div>
      ) : data ? (
        <>
          {failed.length > 0 ? (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              Left out, could not be read:{' '}
              {failed.map((r) => r.label.replace(/^!/, '') || r.url).join(', ')}.
            </p>
          ) : null}

          {data.sets.length === 0 ? (
            <p className="text-sm text-slate-500">
              These runs have no plots in common. Compare runs of the same kind, for example
              model-vs-observations runs with each other.
            </p>
          ) : (
            <>
              <nav
                aria-label="Plot sets"
                className="flex flex-wrap gap-1 border-b border-slate-200"
              >
                {data.sets.map((set) => (
                  <button
                    key={set.name}
                    type="button"
                    onClick={() => update({ set: set.name, plot: null })}
                    aria-current={set.name === detail?.name ? 'page' : undefined}
                    className={cn(
                      '-mb-px border-b-2 px-3 py-1.5 text-sm',
                      set.name === detail?.name
                        ? 'border-slate-900 font-medium text-slate-950'
                        : 'border-transparent text-slate-500 hover:text-slate-800',
                    )}
                  >
                    {set.title}
                  </button>
                ))}
              </nav>

              <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
                <aside className="space-y-2">
                  <div className="relative">
                    <Search
                      className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-slate-400"
                      aria-hidden="true"
                    />
                    <Input
                      value={filter}
                      onChange={(event) => setFilter(event.target.value)}
                      placeholder="Filter variables"
                      aria-label="Filter variables"
                      className="pl-8"
                    />
                  </div>
                  <p className="text-xs text-slate-500">
                    {visible.length} variables · ↑/↓ to step
                    {detail?.missing ? ` · ${detail.missing} plots not in every run` : ''}
                  </p>
                  <ul className="max-h-[70vh] space-y-0.5 overflow-y-auto pr-1">
                    {visible.map((group) => (
                      <li key={group.id}>
                        <button
                          type="button"
                          onClick={() =>
                            update({
                              plot: pickPlot(group, activePlot?.season, activePlot?.region).key,
                            })
                          }
                          className={cn(
                            'w-full rounded-md px-2 py-1.5 text-left text-sm',
                            group.id === activeGroup?.id
                              ? 'bg-slate-900 text-white'
                              : 'text-slate-700 hover:bg-slate-100',
                          )}
                        >
                          <span className="font-medium">{group.title}</span>{' '}
                          <span
                            className={cn(
                              'text-xs',
                              group.id === activeGroup?.id ? 'text-slate-300' : 'text-slate-500',
                            )}
                          >
                            {group.reference}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </aside>

                {detail && activeGroup && activePlot ? (
                  <section className={cn('min-w-0 space-y-3', query.isFetching && 'opacity-70')}>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => step(-1)}
                          aria-label="Previous variable"
                        >
                          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                        </Button>
                        <h2 className="text-base font-semibold text-slate-950">
                          {activeGroup.title}{' '}
                          <span className="font-normal text-slate-500">
                            vs {activeGroup.reference}
                          </span>
                        </h2>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => step(1)}
                          aria-label="Next variable"
                        >
                          <ChevronRight className="h-4 w-4" aria-hidden="true" />
                        </Button>
                      </div>
                      <Choice
                        label="Season"
                        options={unique(activeGroup.plots.map((p) => p.season))}
                        value={activePlot.season}
                        onChange={(season) =>
                          update({ plot: pickPlot(activeGroup, season, activePlot.region).key })
                        }
                      />
                      <Choice
                        label="Region"
                        options={unique(activeGroup.plots.map((p) => p.region))}
                        value={activePlot.region}
                        onChange={(region) =>
                          update({ plot: pickPlot(activeGroup, activePlot.season, region).key })
                        }
                      />
                      {views.length > 1 && !activePlot.singlePanel ? (
                        <Choice
                          label="Panel"
                          options={views}
                          value={view}
                          format={(v) => PANEL_LABELS[v as PanelView]}
                          onChange={(v) => update({ view: v as PanelView })}
                        />
                      ) : null}
                    </div>
                    <Plots data={data} detail={detail} plot={activePlot} view={view} />
                  </section>
                ) : null}
              </div>
            </>
          )}
        </>
      ) : null}
    </Shell>
  );
};

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="mx-auto w-full max-w-[1600px] space-y-4 px-6 py-6">{children}</div>
);

interface ChoiceProps {
  label: string;
  options: string[];
  value: string | null;
  onChange: (value: string) => void;
  format?: (value: string) => string;
}

/** A segmented control; a single option is shown as plain text. */
const Choice = ({ label, options, value, onChange, format = (v) => v }: ChoiceProps) => {
  if (options.length < 2) {
    return options[0] ? <span className="text-sm text-slate-500">{format(options[0])}</span> : null;
  }
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex rounded-md border border-slate-200 p-0.5"
    >
      {options.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={option === value}
          onClick={() => onChange(option)}
          className={cn(
            'rounded px-2.5 py-1 text-xs font-medium',
            option === value ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100',
          )}
        >
          {format(option)}
        </button>
      ))}
    </div>
  );
};

interface PlotsProps {
  data: CompareOut;
  detail: SetDetailOut;
  plot: ComparedPlotOut;
  view: PanelView;
}

/**
 * One cell per run. E3SM Diags images stack run, reference and difference
 * panels; in "Run" view the shared reference panel is shown once, after the
 * runs, instead of once per run.
 */
const Plots = ({ data, detail, plot, view }: PlotsProps) => {
  const panel = plot.singlePanel ? undefined : detail.panels[view];
  const reference = view === 'test' && !plot.singlePanel ? detail.panels.ref : undefined;
  const cells = data.runs.flatMap((run, i) => {
    const path = plot.paths[i];
    return path && !run.error
      ? [{ run, src: imageUrl(run.imageBaseUrl, path), ref: plot.references[i] }]
      : [];
  });

  return (
    <div
      className={cn(
        'grid grid-cols-1 gap-3 xl:grid-cols-2',
        (cells.length > 4 || detail.name === 'polar') && '2xl:grid-cols-3',
      )}
    >
      {cells.map(({ run, src }) => (
        <figure
          key={run.url}
          className="overflow-hidden rounded-lg border border-slate-200 bg-white"
        >
          <figcaption className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-1.5 text-xs">
            <span className="truncate font-medium text-slate-900" title={run.url}>
              {displayLabel(run)}
            </span>
            <a
              href={src}
              target="_blank"
              rel="noreferrer"
              className="text-slate-500 hover:text-slate-800"
              aria-label={`Open the full image for ${displayLabel(run)}`}
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </a>
          </figcaption>
          <PanelImage
            src={src}
            alt={`${displayLabel(run)}: ${plot.key}`}
            panel={panel}
            width={detail.imageWidth}
          />
        </figure>
      ))}
      {reference && cells[0] ? (
        <figure className="overflow-hidden rounded-lg border border-dashed border-slate-300 bg-slate-50/50">
          <figcaption className="border-b border-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600">
            Reference · {cells[0].ref}
          </figcaption>
          <PanelImage
            src={cells[0].src}
            alt={`Reference: ${plot.key}`}
            panel={reference}
            width={detail.imageWidth}
          />
        </figure>
      ) : null}
    </div>
  );
};

/** One panel of a composite image scaled to the cell, or the whole image. */
const PanelImage = ({
  src,
  alt,
  panel,
  width,
}: {
  src: string;
  alt: string;
  panel?: PanelOut;
  width: number | null;
}) => {
  if (!panel || !width) {
    return <img src={src} alt={alt} loading="lazy" className="block h-auto w-full" />;
  }
  return (
    <div
      className="relative w-full overflow-hidden"
      style={{ aspectRatio: `${panel.width} / ${panel.height}` }}
    >
      <img
        src={src}
        alt={alt}
        loading="lazy"
        className="absolute max-w-none"
        style={{
          width: `${(width / panel.width) * 100}%`,
          left: `${(-panel.left / panel.width) * 100}%`,
          top: `${(-panel.top / panel.height) * 100}%`,
        }}
      />
    </div>
  );
};
