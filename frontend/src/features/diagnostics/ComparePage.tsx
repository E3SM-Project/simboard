import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Copy, ExternalLink, Info, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { LoadingState } from '@/components/ui/loading-state';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { compareRuns } from '@/features/diagnostics/api';
import {
  type BasketEntry,
  COMPARE_PATH,
  type CompareRun,
  compareSearch,
  type CompareState,
  displayLabel,
  entryLabel,
  groupKey,
  imageUrl,
  MAX_COMPARED_RUNS,
  parseCompareState,
} from '@/features/diagnostics/compareState';
import { useComparisonBasket } from '@/features/diagnostics/comparisonBasket';
import { comparisonGroupId, loadComparisonGroups } from '@/features/diagnostics/comparisonGroups';
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

/** Dashed block for empty and no-match states. */
const EMPTY_STATE = 'rounded-xl border border-dashed p-6 text-sm text-muted-foreground';
/** Keyboard key in a shortcut hint. */
const KBD = 'rounded border bg-muted-subtle px-1 font-mono text-[0.6875rem] text-foreground';

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
  const client = useQueryClient();
  const filter = state.filter ?? readWorkspace().filter;
  const [editing, setEditing] = useState(false);
  const navigate = useNavigate();
  const basket = useComparisonBasket();
  const { applyComparison } = basket;
  const activatedRuns = useRef('');
  const filterInput = useRef<HTMLInputElement>(null);
  const selectedRuns = useMemo(
    () =>
      (state.selected ?? state.runs).map((run) => ({
        ...run,
        entry:
          basket.entries.find((entry) => entry.url === run.url) ??
          readWorkspace().runs.find((item) => item.url === run.url)?.entry,
      })),
    [state.selected, state.runs, basket.entries],
  );
  const activeRuns = state.runs.map((run) => ({
    ...run,
    entry: selectedRuns.find((item) => item.url === run.url)?.entry,
  }));
  const groupQuery = useQuery({
    queryKey: ['diagnostics', 'comparison-groups', state.selected ?? state.runs],
    queryFn: () => loadComparisonGroups(client, state.selected ?? state.runs),
    enabled: selectedRuns.length > 1,
    staleTime: 10 * 60_000,
    retry: false,
  });
  const comparisonGroups = useMemo(() => groupQuery.data ?? [], [groupQuery.data]);
  const comparisonId = comparisonGroupId(state.runs);

  useEffect(() => {
    if (
      state.selected ||
      comparisonGroups.length < 2 ||
      comparisonGroups.some((group) => !group.plots.size)
    )
      return;
    const first = comparisonGroups[0];
    setParams(compareSearch({ ...state, runs: first.runs, selected: state.runs }), {
      replace: true,
    });
  }, [comparisonGroups, state, setParams]);

  useEffect(() => saveWorkspace({ filter }), [filter]);

  useEffect(() => {
    if (!state.runs.length) {
      activatedRuns.current = '';
      return;
    }
    // An explicit URL owns this comparison; never import other local runs into it.
    saveWorkspace({ runs: selectedRuns });
    const signature = JSON.stringify(state.selected ?? state.runs);
    if (activatedRuns.current === signature) return;
    activatedRuns.current = signature;
    const entries = selectedRuns.flatMap((run) => (run.entry ? [run.entry] : []));
    const kinds = new Set(entries.map(groupKey));
    const applied = applyComparison(
      basket.entries.filter((entry) => kinds.has(groupKey(entry))).map((entry) => entry.url),
      selectedRuns.map((run) => run.url),
      entries,
    );
    if (!applied)
      toast({
        title: 'Could not update your selection',
        variant: 'destructive',
      });
  }, [state.runs, state.selected, selectedRuns, basket.entries, applyComparison, toast]);

  const applyRuns = (runs: CompareRun[], additions: BasketEntry[], selections?: CompareRun[]) => {
    if (
      !basket.applyComparison(
        state.runs.map((run) => run.url),
        (state.runs.length ? runs : (selections ?? runs)).map((run) => run.url),
        additions,
      )
    )
      return 'Your selection is full for this diagnostic kind. Remove selected runs or choose fewer runs.';
    setEditing(false);
    const selected = state.runs.length
      ? [
          ...selectedRuns.filter(
            (run) =>
              !state.runs.some((active) => active.url === run.url && active.label === run.label),
          ),
          ...runs,
        ]
      : (selections ?? runs);
    if (!state.runs.length) {
      for (const entry of basket.entries) {
        if (!selected.some((run) => run.url === entry.url))
          selected.push({ url: entry.url, label: entryLabel(entry) });
      }
    }
    navigate(`${COMPARE_PATH}?${compareSearch({ ...state, runs, selected })}`);
  };

  const query = useQuery({
    queryKey: ['diagnostics', 'compare', state.runs, state.set],
    queryFn: () => compareRuns(state.runs, state.set),
    enabled: state.runs.length > 0 && state.runs.length <= MAX_COMPARED_RUNS,
    staleTime: 10 * 60_000,
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
          <h1 className="text-2xl font-semibold tracking-tight">Compare diagnostics</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            View E3SM Diags and MPAS-Analysis plots from several runs side by side. Browse cases for
            published diagnostics or add a run by URL, select up to {MAX_COMPARED_RUNS} runs of one
            kind, then choose Compare.
          </p>
        </header>
        <div className="rounded-xl border bg-card p-3 sm:p-4">
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
      <Button asChild variant="outline" size="sm" className="w-fit">
        <Link to="/diagnostics">
          <ChevronLeft className="mr-1 h-4 w-4" aria-hidden="true" />
          Back to Diagnostics
        </Link>
      </Button>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Compare diagnostics</h1>
          <p className="mt-1 text-xs text-muted-foreground" aria-live="polite">
            {state.runs.length} compared · {selectedRuns.length} selected
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {activeRuns.map((run) => (
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
              className="max-h-[90dvh] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto motion-reduce:animate-none"
            >
              <DialogHeader>
                <DialogTitle>Edit diagnostic runs</DialogTitle>
                <DialogDescription>
                  Apply changes updates only compared runs. Other selected runs stay in your
                  selection.
                </DialogDescription>
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
      {comparisonGroups.length > 1 ? (
        <div className="flex flex-wrap items-center gap-2">
          <span id="comparison-group-label" className="text-sm font-medium">
            Comparison group
          </span>
          <TooltipProvider delayDuration={150}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="-ml-1 h-8 w-8 text-muted-foreground"
                  aria-label="About comparison group"
                >
                  <Info className="h-4 w-4" aria-hidden="true" />
                </Button>
              </TooltipTrigger>
              <TooltipContent className="max-w-64">
                Selected runs are grouped by the plots they share. Only runs in the same group can
                be compared side by side.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <Select
            value={comparisonGroups.some((group) => group.id === comparisonId) ? comparisonId : ''}
            onValueChange={(id) => {
              const group = comparisonGroups.find((item) => item.id === id);
              if (group) {
                const detail =
                  group.details.find((item) => item.name === state.set) ?? group.details[0];
                const variables =
                  detail?.groups
                    .map((variable) => ({
                      ...variable,
                      plots: variable.plots.filter((plot) =>
                        group.plots.has(JSON.stringify([detail.name, plot.key])),
                      ),
                    }))
                    .filter((variable) => variable.plots.length) ?? [];
                const variable =
                  variables.find(
                    (item) => item.id === activeGroup?.id || item.title === activeGroup?.title,
                  ) ?? variables[0];
                setParams(
                  compareSearch({
                    ...state,
                    runs: group.runs,
                    selected: state.selected ?? state.runs,
                    set: detail?.name ?? state.set,
                    plot: variable
                      ? pickPlot(variable, activePlot?.season, activePlot?.region).key
                      : state.plot,
                  }),
                );
              }
            }}
          >
            <SelectTrigger aria-labelledby="comparison-group-label" className="w-full sm:w-96">
              <SelectValue placeholder="Current comparison" />
            </SelectTrigger>
            <SelectContent>
              {comparisonGroups.map((group, index) => (
                <SelectItem key={group.id} value={group.id}>
                  {group.title}
                  {comparisonGroups.filter((item) => item.title === group.title).length > 1
                    ? ` · Group ${index + 1}`
                    : ''}{' '}
                  ({group.runs.length} runs){!group.plots.size ? ' · No plots' : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}
      {groupQuery.isError ? (
        <Alert variant="warning" className="flex flex-wrap items-center gap-2">
          <p>Could not check comparison groups. Your current comparison is unchanged.</p>
          <Button variant="outline" size="sm" onClick={() => void groupQuery.refetch()}>
            Retry groups
          </Button>
        </Alert>
      ) : null}

      {state.runs.length > MAX_COMPARED_RUNS ? (
        <Alert variant="warning" role="group">
          This link has {state.runs.length} runs; compare at most {MAX_COMPARED_RUNS} at a time. Use
          Edit runs to remove some.
        </Alert>
      ) : query.isLoading ? (
        <LoadingState kind="section" label="Reading each run's published plots…" />
      ) : query.isError ? (
        <Alert variant="error" role="group" className="flex flex-wrap items-center gap-2">
          <p>The diagnostics archive could not be read just now.</p>
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            Try again
          </Button>
        </Alert>
      ) : data ? (
        <>
          {failed.length > 0 ? (
            <Alert variant="warning">
              Could not be read: {names(failed)}. Use Edit runs to replace or remove these runs.
            </Alert>
          ) : null}
          {partial.length > 0 ? (
            <Alert variant="warning">
              Only partly read, so some shared plots may be missing: {names(partial)}.
            </Alert>
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
            <p className={EMPTY_STATE}>
              These runs have no plots in common. Compare runs of the same kind, for example
              model-vs-observations runs with each other. Switch comparison group, edit runs, or use
              Back to Diagnostics to add runs.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
                <span id="plot-set-label" className="text-sm font-medium">
                  Plot set
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
                      className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <Input
                      ref={filterInput}
                      value={filter}
                      onChange={(event) => update({ filter: event.target.value })}
                      placeholder="Filter variables"
                      aria-label="Filter variables"
                      className="pl-8"
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {detail?.missing ? `${detail.missing} plots not in every run` : null}
                  </p>
                  {!visible.length ? (
                    <div className={cn(EMPTY_STATE, 'space-y-2')}>
                      <p>No variables match this filter.</p>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          update({ filter: '' });
                          filterInput.current?.focus();
                        }}
                      >
                        Clear filter
                      </Button>
                    </div>
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
                              ? 'bg-muted text-foreground ring-1 ring-inset ring-border'
                              : 'text-foreground hover:bg-muted',
                          )}
                        >
                          <span className="font-medium">{group.title}</span>{' '}
                          <span className="text-xs text-muted-foreground">{group.reference}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  {visible.length > 1 ? (
                    <p className="text-xs text-muted-foreground">
                      <kbd className={KBD}>j</kbd>/<kbd className={KBD}>k</kbd> or{' '}
                      <kbd className={KBD}>↑</kbd>/<kbd className={KBD}>↓</kbd> to change variable
                    </p>
                  ) : null}
                </aside>

                {detail && activeGroup && activePlot ? (
                  <section className="min-w-0 space-y-3">
                    {query.isFetching ? (
                      <LoadingState kind="inline" label="Refreshing plots…" />
                    ) : null}
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
                        <h2 className="min-w-0 break-words text-lg font-semibold text-foreground">
                          {activeGroup.title}{' '}
                          <span className="font-normal text-muted-foreground">
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
                      <p className="text-xs text-muted-foreground">
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

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="mx-auto w-full max-w-screen-2xl space-y-4 px-4 py-6 sm:px-6">{children}</div>
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
    return options[0] ? (
      <span className="text-sm text-muted-foreground">{format(options[0])}</span>
    ) : null;
  }
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex max-w-full flex-wrap gap-0.5 rounded-lg bg-muted p-1"
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
            'rounded-md px-2.5 py-1 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            option === value
              ? 'bg-background text-foreground shadow'
              : 'text-muted-foreground hover:text-foreground',
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
 * panels; in "Run" view each run's reference panel follows the runs, labeled
 * with its reference and run, and identical images are shown once.
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
          className="overflow-hidden rounded-xl border border-border bg-card"
        >
          <figcaption className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5 text-xs">
            <span className="min-w-0 break-words font-medium text-foreground" title={run.url}>
              {displayLabel(run)}
              {view !== 'test' && ref ? (
                <span className="block font-normal text-muted-foreground">Reference: {ref}</span>
              ) : null}
            </span>
            {src ? (
              <a
                href={src}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
            <p className="flex min-h-48 items-center justify-center p-4 text-sm text-muted-foreground">
              Plot unavailable for this run. Use Edit runs to replace it.
            </p>
          )}
        </figure>
      ))}
      {reference
        ? references.map((cell) => (
            <figure
              key={`${cell.ref}|${cell.src}`}
              className="overflow-hidden rounded-xl border border-dashed border-border bg-muted-subtle"
            >
              <figcaption className="border-b border-border px-3 py-1.5 text-xs font-medium text-muted-foreground">
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
        className="flex min-h-48 flex-col items-center justify-center gap-2 p-4 text-center text-sm text-muted-foreground"
      >
        <p>Published image unavailable: {alt}</p>
        <Button variant="outline" size="sm" onClick={() => setFailedSrc(null)}>
          Retry image
        </Button>
        <a
          href={src}
          target="_blank"
          rel="noreferrer"
          className="rounded text-blue-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
