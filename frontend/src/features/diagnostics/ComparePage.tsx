import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Copy, ExternalLink, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { compareRuns } from '@/features/diagnostics/api';
import {
  type BasketEntry,
  COMPARE_PATH,
  type CompareRun,
  compareSearch,
  type CompareState,
  displayLabel,
  groupKey,
  imageUrl,
  MAX_COMPARED_RUNS,
  parseCompareState,
} from '@/features/diagnostics/compareState';
import { useComparisonBasket } from '@/features/diagnostics/comparisonBasket';
import { CaseBacklink } from '@/features/diagnostics/components/CaseBacklink';
import { RunEditor } from '@/features/diagnostics/components/RunEditor';
import type {
  ComparedPlotOut,
  CompareOut,
  CompareRunOut,
  GroupOut,
  PanelOut,
  PanelView,
  SetDetailOut,
} from '@/features/diagnostics/types';
import { readWorkspace, saveWorkspace } from '@/features/diagnostics/workspaceState';
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
  const [filter, setFilter] = useState(() => readWorkspace().filter);
  const [editing, setEditing] = useState(false);
  const navigate = useNavigate();
  const basket = useComparisonBasket();
  const { entries: basketEntries, applyComparison } = basket;
  const activatedRuns = useRef('');
  const selectedRuns = useMemo(
    () =>
      state.runs.map((run) => ({
        ...run,
        entry:
          basket.entries.find((entry) => entry.url === run.url) ??
          readWorkspace().runs.find((item) => item.url === run.url)?.entry,
      })),
    [state.runs, basket.entries],
  );

  useEffect(() => saveWorkspace({ filter }), [filter]);

  useEffect(() => {
    if (!state.runs.length) {
      activatedRuns.current = '';
      return;
    }
    // An explicit URL owns this comparison; never import other local runs into it.
    saveWorkspace({ runs: selectedRuns });
    const signature = JSON.stringify(state.runs);
    if (activatedRuns.current === signature) return;
    activatedRuns.current = signature;
    const entries = selectedRuns.flatMap((run) => (run.entry ? [run.entry] : []));
    const kinds = new Set(entries.map(groupKey));
    applyComparison(
      basketEntries.filter((entry) => kinds.has(groupKey(entry))).map((entry) => entry.url),
      state.runs.map((run) => run.url),
      entries,
    );
  }, [state.runs, selectedRuns, basketEntries, applyComparison]);

  const applyRuns = (runs: CompareRun[], additions: BasketEntry[]) => {
    if (
      !basket.applyComparison(
        state.runs.map((run) => run.url),
        runs.map((run) => run.url),
        additions,
      )
    )
      return 'The comparison tray is full for this diagnostic kind. Remove staged runs or choose fewer runs.';
    setEditing(false);
    navigate(`${COMPARE_PATH}?${compareSearch({ ...state, runs })}`);
  };

  const query = useQuery({
    queryKey: ['diagnostics', 'compare', state.runs, state.set],
    queryFn: () => compareRuns(state.runs, state.set),
    enabled: state.runs.length > 0 && state.runs.length <= MAX_COMPARED_RUNS,
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

  // Keep the URL naming exactly what is shown. While another set loads, the
  // previous response is still on screen and must not pull the URL back.
  useEffect(() => {
    if (query.isPlaceholderData) return;
    if (detail && activePlot && (state.set !== detail.name || state.plot !== activePlot.key)) {
      update({ set: detail.name, plot: activePlot.key });
    }
  }, [activePlot, detail, query.isPlaceholderData, state.plot, state.set, update]);

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
      if (
        editing ||
        event.defaultPrevented ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        (event.target as HTMLElement | null)?.closest(
          'input, textarea, select, [contenteditable="true"], [role="dialog"], [role="combobox"], [role="listbox"], [role="radiogroup"], [role="tablist"]',
        )
      )
        return;
      const delta = { ArrowDown: 1, j: 1, ArrowUp: -1, k: -1 }[event.key];
      if (delta) {
        event.preventDefault();
        step(delta);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [step, editing]);

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
        <header>
          <h1 className="text-xl font-semibold text-slate-950">Compare diagnostics</h1>
        </header>
        <div className="rounded-xl border bg-white p-3 sm:p-4">
          <RunEditor initialRuns={[]} onApply={applyRuns} />
        </div>
      </Shell>
    );
  }

  const names = (runs: CompareRunOut[]) => runs.map((r) => displayLabel(r)).join(', ');
  const failed = data?.runs.filter((r) => r.error) ?? [];
  const partial = data?.runs.filter((r) => !r.error && r.partial) ?? [];

  return (
    <Shell>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold text-slate-950">Compare diagnostics</h1>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {selectedRuns.map((run) => (
              <Badge
                key={`${run.url}|${run.label}`}
                variant="secondary"
                title={run.url}
                className="max-w-full break-all"
              >
                {displayLabel(run)}
                {run.entry ? <CaseBacklink entry={run.entry} /> : null}
              </Badge>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <Dialog open={editing} onOpenChange={setEditing}>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                Edit runs
              </Button>
            </DialogTrigger>
            <DialogContent
              overlayClassName="motion-reduce:animate-none"
              className="max-h-[90dvh] w-[calc(100%-2rem)] max-w-6xl overflow-y-auto motion-reduce:animate-none"
              aria-describedby={undefined}
            >
              <DialogHeader>
                <DialogTitle>Edit diagnostic runs</DialogTitle>
              </DialogHeader>
              <RunEditor
                initialRuns={state.runs}
                onApply={applyRuns}
                comparisonSet={state.set}
                onCancel={() => setEditing(false)}
              />
            </DialogContent>
          </Dialog>
          <Button variant="outline" size="sm" onClick={copyLink}>
            <Copy className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            Copy link
          </Button>
        </div>
      </header>

      {state.runs.length > MAX_COMPARED_RUNS ? (
        <Notice>
          This link has {state.runs.length} runs; compare at most {MAX_COMPARED_RUNS} at a time. Use
          Edit runs to remove some.
        </Notice>
      ) : query.isLoading ? (
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
            <Notice>
              Could not be read: {names(failed)}. Use Edit runs to replace or remove these runs.
            </Notice>
          ) : null}
          {partial.length > 0 ? (
            <Notice>
              Only partly read, so some shared plots may be missing: {names(partial)}.
            </Notice>
          ) : null}
          {failed.length || partial.length ? (
            <Button
              variant="outline"
              size="sm"
              disabled={query.isFetching}
              onClick={() => void query.refetch()}
            >
              Retry diagnostics
            </Button>
          ) : null}

          {data.sets.length === 0 ? (
            <p className="text-sm text-slate-500">
              These runs have no plots in common. Compare runs of the same kind, for example
              model-vs-observations runs with each other. Use Edit runs to change your selection.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-3">
                <span id="plot-set-label" className="text-sm font-medium">
                  Diagnostic category
                </span>
                <Select value={detail?.name} onValueChange={(set) => update({ set, plot: null })}>
                  <SelectTrigger aria-labelledby="plot-set-label" className="w-full sm:w-80">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {data.sets.map((set) => (
                      <SelectItem key={set.name} value={set.name}>
                        {set.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

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
                    {detail?.missing ? `${detail.missing} plots not in every run` : null}
                  </p>
                  {!visible.length ? (
                    <p className="text-sm text-slate-500">No variables match this filter.</p>
                  ) : null}
                  <ul className="max-h-60 space-y-0.5 overflow-y-auto pr-1 lg:max-h-[70vh]">
                    {visible.map((group) => (
                      <li key={group.id}>
                        <button
                          type="button"
                          aria-current={group.id === activeGroup?.id ? 'true' : undefined}
                          onClick={() =>
                            update({
                              plot: pickPlot(group, activePlot?.season, activePlot?.region).key,
                            })
                          }
                          className={cn(
                            'w-full rounded-md px-2 py-1.5 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
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
                      <div className="flex min-w-0 items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => step(-1)}
                          aria-label="Previous variable"
                        >
                          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                        </Button>
                        <h2 className="min-w-0 break-words text-base font-semibold text-slate-950">
                          {activeGroup.title}{' '}
                          <span className="font-normal text-slate-500">
                            vs{' '}
                            {new Set(activePlot.references.filter(Boolean)).size > 1
                              ? 'per-run references'
                              : activeGroup.reference}
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
                    {view === 'diff' && !activePlot.singlePanel ? (
                      <p className="text-xs text-slate-500">
                        Difference shows each run minus its own reference, not the difference
                        between selected simulations. Colors use each published image’s scale.
                      </p>
                    ) : null}
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

const Notice = ({ children }: { children: React.ReactNode }) => (
  <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
    {children}
  </p>
);

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="mx-auto w-full max-w-[1600px] space-y-4 px-4 py-6 sm:px-6">{children}</div>
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
      className="inline-flex max-w-full flex-wrap rounded-md border border-slate-200 p-0.5"
      onKeyDown={(event) => {
        const delta = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
        if (!delta && event.key !== 'Home' && event.key !== 'End') return;
        event.preventDefault();
        const index =
          event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? options.length - 1
              : (options.indexOf(value ?? '') + (delta ?? 0) + options.length) % options.length;
        onChange(options[index]);
        event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]')[index]?.focus();
      }}
    >
      {options.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={option === value}
          tabIndex={option === (value ?? options[0]) ? 0 : -1}
          onClick={() => onChange(option)}
          className={cn(
            'rounded px-2.5 py-1 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
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
  const cells = data.runs.map((run, i) => {
    const path = plot.paths[i];
    return {
      run,
      src: path && !run.error ? imageUrl(run.imageBaseUrl, path) : null,
      ref: plot.references[i],
    };
  });
  const references = cells.filter(
    (cell, index) =>
      cell.src &&
      !cells
        .slice(0, index)
        .some((previous) => previous.src === cell.src && previous.ref === cell.ref),
  );

  return (
    <div
      className={cn(
        'grid grid-cols-1 gap-3 xl:grid-cols-2',
        (cells.length > 4 || detail.name === 'polar') && '2xl:grid-cols-3',
      )}
    >
      {cells.map(({ run, src, ref }) => (
        <figure
          key={`${run.url}|${run.label}`}
          className="overflow-hidden rounded-lg border border-slate-200 bg-white"
        >
          <figcaption className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-1.5 text-xs">
            <span className="min-w-0 break-words font-medium text-slate-900" title={run.url}>
              {displayLabel(run)}
              {view !== 'test' && ref ? (
                <span className="block font-normal text-slate-500">Reference: {ref}</span>
              ) : null}
            </span>
            {src ? (
              <a
                href={src}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 rounded p-1 text-slate-500 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label={`Open the full image for ${displayLabel(run)}`}
              >
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            ) : null}
          </figcaption>
          {src ? (
            <PanelImage
              src={src}
              alt={`${displayLabel(run)}: ${plot.key}`}
              panel={panel}
              width={detail.imageWidth}
            />
          ) : (
            <p className="flex min-h-48 items-center justify-center p-4 text-sm text-slate-500">
              Plot unavailable for this run. Use Edit runs to replace it.
            </p>
          )}
        </figure>
      ))}
      {reference
        ? references.map((cell) => (
            <figure
              key={`${cell.ref}|${cell.src}`}
              className="overflow-hidden rounded-lg border border-dashed border-slate-300 bg-slate-50/50"
            >
              <figcaption className="border-b border-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600">
                Reference · {cell.ref} · {displayLabel(cell.run)}
              </figcaption>
              <PanelImage
                src={cell.src!}
                alt={`Reference: ${plot.key}`}
                panel={reference}
                width={detail.imageWidth}
              />
            </figure>
          ))
        : null}
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
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  if (failedSrc === src)
    return (
      <div
        role="status"
        className="flex min-h-48 flex-col items-center justify-center gap-2 p-4 text-center text-sm text-slate-500"
      >
        <p>Published image unavailable: {alt}</p>
        <Button variant="outline" size="sm" onClick={() => setFailedSrc(null)}>
          Retry image
        </Button>
        <a
          href={src}
          target="_blank"
          rel="noreferrer"
          className="rounded underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Open original image
        </a>
      </div>
    );
  if (!panel || !width) {
    return (
      <img
        src={src}
        alt={alt}
        loading="lazy"
        onError={() => setFailedSrc(src)}
        className="block h-auto w-full"
      />
    );
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
        onError={() => setFailedSrc(src)}
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
