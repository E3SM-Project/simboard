import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { Info, Loader2, Plus, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { listCases } from '@/api/catalog';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LoadingState } from '@/components/ui/loading-state';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { getCaseDiagnosticsRuns } from '@/features/diagnostics/api';
import {
  type BasketEntry,
  type CompareRun,
  displayLabel,
  entryLabel,
  groupKey,
  isRunUrl,
  MAX_COMPARED_RUNS,
  type SelectedRun,
  selectedRunGroup,
  syncSelectedRuns,
  toEntry,
} from '@/features/diagnostics/compareState';
import { useComparisonBasket } from '@/features/diagnostics/comparisonBasket';
import { loadComparisonGroups } from '@/features/diagnostics/comparisonGroups';
import { validateComparison } from '@/features/diagnostics/comparisonValidation';
import { CaseBacklink } from '@/features/diagnostics/components/CaseBacklink';
import { DiagnosticRunList } from '@/features/diagnostics/components/DiagnosticRunList';
import {
  diagnosticIdentifier,
  periodGroups,
  RUN_GROUPS,
} from '@/features/diagnostics/discoveryState';
import type { CaseDiagnosticsOut } from '@/features/diagnostics/types';
import { readWorkspace, saveWorkspace } from '@/features/diagnostics/workspaceState';
import { caseDetailsPath } from '@/lib/catalog/urls';
import { cn } from '@/lib/utils';
import type { CaseListItemOut } from '@/types';

const LCRC = 'https://web.lcrc.anl.gov/public/e3sm/diagnostic_output';
const NERSC = 'https://portal.nersc.gov/project/m2136';
const CLIMO = 'e3sm_diags/180x360_aave/model_vs_obs_1985-2014/viewer/';
const v2Viewer = (run: string) => `${LCRC}/ac.forsyth2/E3SMv2/${run}/${CLIMO}`;
const v1Viewer = (run: string) => `${NERSC}/E3SMv1/e3sm_diags/${run}/${CLIMO}`;
const CRYO_DIAGS = `${LCRC}/wlin/E3SMv2/cryo/20210713.CRYO1850.ne30pg2_SOwISC12to60E2r4.IB_bugfixes.chrysalis/e3sm_diags/180x360_aave`;

/** The example comparisons shipped with IICE (E3SM's standalone intercomparison tool), kept as one-click starting points. */
const EXAMPLES: { name: string; runs: CompareRun[] }[] = [
  {
    name: 'E3SM Diags: E3SMv1 and v2, historical and AMIP',
    runs: [
      { url: v2Viewer('v2.LR.historical_0101'), label: 'E3SMv2 historical' },
      { url: v2Viewer('v2.LR.amip_0101'), label: 'E3SMv2 AMIP' },
      { url: v1Viewer('20180215.DECKv1b_H1.ne30_oEC.edison'), label: 'E3SMv1 historical' },
      { url: v1Viewer('20180316.DECKv1b_A1.ne30_oEC.edison'), label: 'E3SMv1 AMIP' },
    ],
  },
  {
    name: 'E3SM Diags: one cryosphere run at three periods',
    runs: ['0001-0020', '0021-0040', '0081-0100'].map((years) => ({
      url: `${CRYO_DIAGS}/model_vs_obs_${years}/viewer/`,
      label: `Years ${years}`,
    })),
  },
  {
    name: 'MPAS-Analysis: v2 piControl, early and late',
    runs: [
      ['ts_0001-0050_climo_0001-0050', 'v2.LR.piControl 0001-0050'],
      ['ts_0001-0500_climo_0451-0500', 'v2.LR.piControl 0451-0500'],
    ].map(([run, label]) => ({
      url: `${LCRC}/ac.golaz/E3SMv2/v2.LR.piControl/mpas_analysis/${run}/`,
      label,
    })),
  },
  {
    name: 'MPAS-Analysis: two cryosphere experiments',
    // An older layout: the "!" label names the case in the image filenames.
    runs: [
      ['20220526', 'CryoBranchN2DependentDefaultMinMaxKappa', 'N2dependentDefaultKappa'],
      ['20220511', 'CryoBranchN2_dependent', 'N2dependent'],
    ].map(([date, branch, short]) => ({
      url: `${LCRC}/ac.dcomeau/${date}.CRYO1850.ne30pg2_ECwISC30to60E2r1.chrysalis.${branch}/yrs1-10/`,
      label: `!ECwISC30to60E2r1.CRYO1850.${short} yrs 1-10`,
    })),
  },
];

interface RunEditorProps {
  initialRuns: CompareRun[];
  onApply: (runs: CompareRun[], entries: BasketEntry[], selected?: CompareRun[]) => string | void;
  onCancel?: () => void;
  comparisonSet?: string | null;
}

/** One draft for indexed case discovery and IICE-compatible manual addresses. */
export const RunEditor = ({
  initialRuns,
  onApply,
  onCancel,
  comparisonSet = null,
}: RunEditorProps) => {
  const client = useQueryClient();
  const basket = useComparisonBasket();
  const [runs, setRuns] = useState<SelectedRun[]>(() =>
    onCancel
      ? initialRuns.map((run) => ({
          ...run,
          entry: basket.entries.find((entry) => entry.url === run.url),
        }))
      : syncSelectedRuns(readWorkspace().runs, basket.entries),
  );
  const [tab, setTab] = useState(() => readWorkspace().tab);
  const [problem, setProblem] = useState('');
  const [selectionNotice, setSelectionNotice] = useState('');
  const [retryRuns, setRetryRuns] = useState<SelectedRun[] | null>(null);
  const [checking, setChecking] = useState(false);
  const validating = useRef(false);
  const mounted = useRef(false);
  const [manual, setManual] = useState<CompareRun>({ url: '', label: '' });
  const trayGroups = [...new Set([...runs.map(selectedRunGroup), ...basket.entries.map(groupKey)])];
  const knownKinds = new Set(runs.flatMap((run) => (run.entry ? [groupKey(run.entry)] : [])));
  const [selectionGroup, setSelectionGroup] = useState(
    () => [...knownKinds][0] ?? (!runs.length ? (trayGroups[0] ?? '') : ''),
  );
  const currentGroup = trayGroups.includes(selectionGroup) ? selectionGroup : (trayGroups[0] ?? '');
  const visibleRuns = onCancel
    ? runs
    : runs.filter((run) => selectedRunGroup(run) === currentGroup);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!onCancel) saveWorkspace({ runs, tab });
  }, [runs, tab, onCancel]);

  useEffect(() => {
    if (onCancel || checking) return;
    setRuns((current) => syncSelectedRuns(current, basket.entries, selectionGroup));
  }, [basket.entries, onCancel, selectionGroup, checking]);

  const changeRuns = (next: SelectedRun[]) => {
    if (validating.current) return false;
    if (
      !onCancel &&
      !basket.applyComparison(
        runs.map((run) => run.url),
        next.map((run) => run.url),
        next.flatMap((run) => (run.entry ? [run.entry] : [])),
      )
    ) {
      setProblem(`Compare at most ${MAX_COMPARED_RUNS} runs of one kind at a time.`);
      return false;
    }
    setRuns(next);
    setProblem('');
    setSelectionNotice('');
    setRetryRuns(null);

    return true;
  };

  const edit = (index: number, patch: Partial<CompareRun>) =>
    changeRuns(
      runs.map((run, i) =>
        i === index
          ? { ...run, ...patch, entry: patch.url && patch.url !== run.url ? undefined : run.entry }
          : run,
      ),
    );

  const add = (run: SelectedRun) => {
    if (!isRunUrl(run.url))
      return setProblem(
        'Use an HTTPS E3SM Diags viewer page or an MPAS-Analysis run directory, not a general resource directory.',
      );
    if (runs.some((item) => item.url === run.url.trim() && item.label === run.label.trim()))
      return setProblem(
        'This run and label are already selected. Choose another case, time range, or IICE case override.',
      );
    if (
      runs.filter((item) => selectedRunGroup(item) === selectedRunGroup(run)).length >=
      MAX_COMPARED_RUNS
    )
      return setProblem(`Compare at most ${MAX_COMPARED_RUNS} runs at a time.`);
    if (!changeRuns([...runs, { ...run, url: run.url.trim(), label: run.label.trim() }])) return;
    if (!runs.length) setSelectionGroup(selectedRunGroup(run));
    else if (!onCancel && selectedRunGroup(run) !== currentGroup) {
      const title =
        RUN_GROUPS.find((group) => group.key === selectedRunGroup(run))?.title ??
        'another comparison group';
      setSelectionNotice(`Run added to ${title}. Switch Comparison group to review it.`);
    }
    setManual({ url: '', label: '' });
  };

  const apply = async (next: SelectedRun[], selections = next) => {
    if (validating.current) return;
    setRetryRuns(null);
    if (!next.length)
      return setProblem('Add at least one diagnostic run. Add two or more to compare.');
    if (next.length > MAX_COMPARED_RUNS)
      return setProblem(`Compare at most ${MAX_COMPARED_RUNS} runs at a time.`);
    if (next.some((run) => !isRunUrl(run.url)))
      return setProblem(
        'One or more run addresses are invalid. Use a supported HTTPS diagnostic run address.',
      );
    if (
      new Set(next.map((run) => JSON.stringify([run.url.trim(), run.label.trim()]))).size !==
      next.length
    )
      return setProblem('Each selected run must have a different address or label.');
    const selected = next.map(({ url, label }) => ({ url: url.trim(), label: label.trim() }));
    validating.current = true;
    setChecking(true);
    setProblem('');
    try {
      let active = selected;
      let failure = await validateComparison(client, active, comparisonSet);
      if (!onCancel && selected.length > 1 && failure && !failure.retryable) {
        const groups = await loadComparisonGroups(client, selected);
        active = groups.find((group) => group.plots.size)?.runs ?? selected;
        if (active !== selected) failure = await validateComparison(client, active, comparisonSet);
      }
      if (!mounted.current) return;
      if (failure) {
        setProblem(failure.problem);
        if (failure.retryable) setRetryRuns(next);
        return;
      }
      const error = onApply(
        active,
        selections.flatMap((run) => (run.entry ? [run.entry] : [])),
        selections.map(({ url, label }) => ({ url: url.trim(), label: label.trim() })),
      );
      if (error) setProblem(error);
    } catch {
      if (mounted.current) {
        setProblem('Could not check run compatibility. Check your connection and try again.');
        setRetryRuns(next);
      }
    } finally {
      validating.current = false;
      if (mounted.current) setChecking(false);
    }
  };

  const browser = (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList className="grid w-full grid-cols-2">
        <TabsTrigger value="browse">Browse SimBoard</TabsTrigger>
        <TabsTrigger value="url">Add by URL</TabsTrigger>
      </TabsList>
      <TabsContent value="browse" className="space-y-3">
        <CaseBrowser
          isAdded={(url) => runs.some((run) => run.url === url)}
          onAdd={(entry) => add({ url: entry.url, label: entryLabel(entry), entry })}
          onRemove={(url) => changeRuns(runs.filter((run) => run.url !== url))}
        />
      </TabsContent>
      <TabsContent value="url" className="space-y-4">
        <form
          className="space-y-3 rounded-xl border p-3"
          onSubmit={(event) => {
            event.preventDefault();
            add(manual);
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="manual-run-url">Diagnostic run URL</Label>
            <Input
              id="manual-run-url"
              value={manual.url}
              placeholder="https://…/viewer/ or https://…/mpas_analysis/…/"
              onChange={(event) => setManual({ ...manual, url: event.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="manual-run-label">Label (optional)</Label>
            <Input
              id="manual-run-label"
              value={manual.label}
              onChange={(event) => setManual({ ...manual, label: event.target.value })}
            />
          </div>
          <Button type="submit" variant="outline" size="sm">
            <Plus className="mr-1 h-4 w-4" aria-hidden="true" />
            Add run
          </Button>
        </form>
        <details className="rounded-xl border p-3">
          <summary className="cursor-pointer text-sm font-medium">IICE example comparisons</summary>
          <ul className="mt-3 space-y-2">
            {EXAMPLES.map((example) => (
              <li key={example.name} className="flex items-center justify-between gap-3 text-sm">
                <span>{example.name}</span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => apply(example.runs)}
                >
                  Open
                </Button>
              </li>
            ))}
          </ul>
        </details>
      </TabsContent>
    </Tabs>
  );

  return (
    <div className="min-w-0 space-y-3">
      <fieldset disabled={checking} className="min-w-0 space-y-3">
        {onCancel ? (
          <p className="text-sm text-muted-foreground">
            Edit active runs here. Use Back to Diagnostics to browse cases and add runs.
          </p>
        ) : (
          browser
        )}
        <section className="space-y-2 border-t pt-3" aria-label="Selected runs">
          <h2 className="text-sm font-semibold" aria-live="polite">
            Selected runs ({visibleRuns.length}/{MAX_COMPARED_RUNS})
          </h2>
          {!onCancel && trayGroups.length > 1 ? (
            <Select
              value={currentGroup}
              onValueChange={(key) => {
                const next = [...runs];
                for (const entry of basket.entries.filter((entry) => groupKey(entry) === key)) {
                  if (!next.some((run) => run.url === entry.url && run.label === entryLabel(entry)))
                    next.push({ url: entry.url, label: entryLabel(entry), entry });
                }
                setRetryRuns(null);
                setSelectionNotice('');
                setSelectionGroup(key);
                setRuns(next);
                setProblem('');
              }}
            >
              <SelectTrigger aria-label="Comparison group" className="h-8 w-full text-xs sm:w-72">
                <SelectValue placeholder="Staged diagnostic group" />
              </SelectTrigger>
              <SelectContent>
                {trayGroups.map((key) => (
                  <SelectItem key={key} value={key}>
                    {RUN_GROUPS.find((group) => group.key === key)?.title ?? key} (
                    {runs.filter((run) => selectedRunGroup(run) === key).length +
                      basket.entries.filter(
                        (entry) =>
                          groupKey(entry) === key && !runs.some((run) => run.url === entry.url),
                      ).length}
                    /{MAX_COMPARED_RUNS})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
          {!visibleRuns.length ? (
            <p className="text-sm text-muted-foreground">No runs selected.</p>
          ) : null}
          <div
            className={cn(
              'space-y-1 overflow-y-auto p-0.5',
              onCancel ? 'max-h-[50dvh]' : 'max-h-44',
            )}
          >
            {visibleRuns.map((run, visibleIndex) => {
              const index = runs.indexOf(run);
              return (
                <div key={index} className="max-w-3xl rounded-md border px-2.5 py-1">
                  <div className="flex items-center justify-between gap-2">
                    <a
                      href={run.url}
                      target="_blank"
                      rel="noreferrer"
                      title={run.url}
                      className="min-w-0 text-sm font-medium text-blue-600 hover:underline [overflow-wrap:anywhere]"
                    >
                      {displayLabel(run)}
                    </a>
                    <div className="flex shrink-0 items-center gap-1">
                      {run.entry ? <CaseBacklink entry={run.entry} /> : null}
                      <Button
                        type="button"
                        size="icon"
                        className="h-7 w-7 shrink-0"
                        variant="ghost"
                        aria-label={`Remove run ${visibleIndex + 1}`}
                        onClick={() => changeRuns(runs.filter((_, i) => i !== index))}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </div>
                  </div>
                  {run.entry ? (
                    <p className="font-mono text-xs text-muted-foreground [overflow-wrap:anywhere]">
                      {diagnosticIdentifier(run.entry)}
                    </p>
                  ) : null}
                  <details className="text-xs text-muted-foreground">
                    <summary className="w-fit cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                      Edit address and label
                    </summary>
                    <div className="grid gap-2 py-2 sm:grid-cols-2">
                      <Input
                        aria-label={`Run ${visibleIndex + 1} address`}
                        value={run.url}
                        onChange={(event) => edit(index, { url: event.target.value })}
                      />
                      <Input
                        aria-label={`Run ${visibleIndex + 1} label`}
                        placeholder="Label (optional)"
                        value={run.label}
                        onChange={(event) => edit(index, { label: event.target.value })}
                      />
                    </div>
                  </details>
                </div>
              );
            })}
          </div>
        </section>
      </fieldset>
      <footer className="sticky bottom-0 z-10 space-y-2 border-t bg-card py-2">
        {selectionNotice ? (
          <p role="status" className="text-sm text-muted-foreground">
            {selectionNotice}
          </p>
        ) : null}
        {problem ? <Alert variant="error">{problem}</Alert> : null}
        {retryRuns && !checking ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              if (retryRuns) void apply(retryRuns);
            }}
          >
            Retry comparison
          </Button>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-2">
            {onCancel ? (
              <Button type="button" variant="outline" size="sm" onClick={onCancel}>
                Cancel
              </Button>
            ) : null}
            <Button
              type="button"
              size="sm"
              disabled={checking || !visibleRuns.length || visibleRuns.length > MAX_COMPARED_RUNS}
              aria-busy={checking}
              onClick={() => void apply(visibleRuns, runs)}
            >
              {checking ? (
                <>
                  <Loader2
                    className="mr-1 h-4 w-4 animate-spin motion-reduce:animate-none"
                    aria-hidden="true"
                  />
                  <span role="status">Checking compatibility…</span>
                </>
              ) : onCancel ? (
                'Apply changes'
              ) : (
                'Compare'
              )}
            </Button>
          </div>
        </div>
      </footer>
    </div>
  );
};

interface DiscoveredCase {
  record: CaseListItemOut;
  diagnostics: CaseDiagnosticsOut | null;
}

const CaseBrowser = ({
  isAdded,
  onAdd,
  onRemove,
}: {
  isAdded: (url: string) => boolean;
  onAdd: (entry: BasketEntry) => void;
  onRemove: (url: string) => void;
}) => {
  const client = useQueryClient();
  const [saved] = useState(readWorkspace);
  const [search, setSearch] = useState(saved.search);
  const [debounced, setDebounced] = useState(saved.search.trim());
  const [caseId, setCaseId] = useState(saved.caseId);
  const [page, setPage] = useState(saved.page);
  const [analysis, setAnalysis] = useState(saved.analysis);
  const [tool, setTool] = useState(saved.tool);
  useEffect(
    () => saveWorkspace({ search, caseId, analysis, tool, page }),
    [search, caseId, analysis, tool, page],
  );
  useEffect(() => {
    if (search.trim() === debounced) return;
    const timer = setTimeout(() => {
      setDebounced(search.trim());
      setCaseId(null);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search, debounced]);
  const query = useInfiniteQuery({
    queryKey: ['diagnostics', 'supported-cases', debounced],
    initialPageParam: debounced === saved.search.trim() ? saved.page : 1,
    queryFn: async ({ pageParam, signal }) => {
      const page = await listCases({
        search: debounced || undefined,
        page: pageParam,
        pageSize: 10,
        sortBy: 'name',
      });
      const cases: DiscoveredCase[] = [];
      // Limit archive discovery fan-out; never crawl the entire catalog automatically.
      for (let index = 0; index < page.items.length; index += 3) {
        if (signal.aborted) throw new Error('Search cancelled');
        cases.push(
          ...(await Promise.all(
            page.items.slice(index, index + 3).map(async (record) => {
              try {
                const diagnostics = await client.fetchQuery({
                  queryKey: ['diagnostics', 'case-runs', record.id],
                  queryFn: () => getCaseDiagnosticsRuns(record.id),
                  staleTime: 10 * 60_000,
                  retry: false,
                });
                const sources = diagnostics.sources.filter(
                  (source) => source.error !== 'url_not_allowed',
                );
                if (sources.length !== diagnostics.sources.length)
                  console.debug('Diagnostics discovery excluded unsupported directories', {
                    caseId: record.id,
                    count: diagnostics.sources.length - sources.length,
                  });

                return { record, diagnostics: { ...diagnostics, sources } };
              } catch {
                console.debug('Diagnostics discovery request failed', { caseId: record.id });
                return { record, diagnostics: null };
              }
            }),
          )),
        );
      }
      return {
        cases,
        page: page.page,
        nextPage: page.page * page.pageSize < page.total ? page.page + 1 : undefined,
      };
    },
    getNextPageParam: (page) => page.nextPage,
    staleTime: 10 * 60_000,
    retry: false,
  });
  const checked = query.data?.pages.flatMap((page) => page.cases) ?? [];
  const supported = checked.filter((item) =>
    item.diagnostics?.sources.some((source) => source.runs.length),
  );
  const selected = supported.find((item) => item.record.id === caseId) ?? supported[0];
  const incomplete = checked.filter(
    (item) =>
      !item.diagnostics ||
      item.diagnostics.sources.some((source) => source.error || source.partial),
  );
  const failed = incomplete.filter(
    (item) =>
      !item.diagnostics ||
      item.diagnostics.sources.some((source) => source.error && source.error !== 'url_not_allowed'),
  );
  const partial = incomplete.filter((item) =>
    item.diagnostics?.sources.some((source) => source.partial && !source.error),
  );

  return (
    <div className="grid min-w-0 gap-3 md:h-[min(70dvh,36rem)] md:grid-cols-[minmax(14rem,1fr)_minmax(0,2.5fr)]">
      <section
        aria-label="Browse cases"
        className="flex h-[32rem] min-h-0 min-w-0 flex-col rounded-xl border md:h-auto"
      >
        <div className="space-y-2 border-b p-3">
          <div className="flex items-center gap-2">
            <Label htmlFor="diagnostic-case-search" className="sr-only">
              Search cases
            </Label>
            <Input
              id="diagnostic-case-search"
              value={search}
              placeholder="Search by case name"
              onChange={(event) => setSearch(event.target.value)}
            />
            <TooltipProvider delayDuration={150}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0 text-muted-foreground"
                    aria-label="About supported diagnostics"
                  >
                    <Info className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent className="max-w-64">
                  Only publicly accessible E3SM Diags and MPAS-Analysis runs supported by the
                  comparison viewer are listed.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          {query.isFetching ? (
            <LoadingState
              kind="inline"
              label="Checking cases for supported diagnostics…"
              className="justify-start text-xs"
            />
          ) : !supported.length && !query.isError && !incomplete.length ? (
            <p role="status" className="text-xs text-muted-foreground">
              {query.hasNextPage
                ? 'No supported cases found on this page. Load more or narrow your search.'
                : 'No supported cases found.'}
            </p>
          ) : null}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {query.isError || incomplete.length ? (
            <Alert variant="warning" className="mb-2 space-y-2 text-xs">
              {query.isError ? (
                <p>Case search failed. Results may be incomplete. Retry discovery.</p>
              ) : null}
              {failed.length ? (
                <p>
                  Could not load diagnostics for {failed.map((item) => item.record.name).join(', ')}
                  . Results are incomplete. Retry discovery.
                </p>
              ) : null}
              {partial.length ? (
                <p>
                  Run discovery is incomplete for{' '}
                  {partial.map((item) => item.record.name).join(', ')}. Some runs may be missing.
                  Retry discovery.
                </p>
              ) : null}
              {query.isError || failed.length || partial.length ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    await Promise.all(
                      checked
                        .filter(
                          (item) =>
                            !item.diagnostics ||
                            item.diagnostics.sources.some(
                              (source) => source.error || source.partial,
                            ),
                        )
                        .map((item) =>
                          client.invalidateQueries({
                            queryKey: ['diagnostics', 'case-runs', item.record.id],
                            refetchType: 'none',
                          }),
                        ),
                    );
                    await query.refetch();
                  }}
                  disabled={query.isFetching}
                >
                  Retry discovery
                </Button>
              ) : null}
            </Alert>
          ) : null}
          <ul className="space-y-1">
            {supported.map(({ record, diagnostics }) => (
              <li key={record.id}>
                <Button
                  type="button"
                  variant="ghost"
                  className={cn(
                    'h-auto w-full justify-start gap-2 whitespace-normal px-2 py-2 text-left text-xs',
                    record.id === selected?.record.id &&
                      'bg-muted text-foreground ring-1 ring-inset ring-muted-foreground/40',
                  )}
                  aria-pressed={record.id === selected?.record.id}
                  aria-controls="available-case-diagnostics"
                  onClick={() => {
                    setCaseId(record.id);
                    setPage(
                      query.data?.pages.find((page) =>
                        page.cases.some((item) => item.record.id === record.id),
                      )?.page ?? 1,
                    );
                  }}
                >
                  <span
                    title={record.name}
                    className="line-clamp-2 min-w-0 flex-1 [overflow-wrap:anywhere]"
                  >
                    {record.name}
                  </span>
                  <span className="shrink-0 text-xs font-normal text-muted-foreground">
                    <span className="sr-only"> · </span>
                    {periodGroups(diagnostics?.sources ?? []).reduce(
                      (count, [, runs]) => count + runs.length,
                      0,
                    )}{' '}
                    runs
                  </span>
                </Button>
              </li>
            ))}
          </ul>
        </div>
        {query.hasNextPage ? (
          <div className="border-t p-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={query.isFetching || search.trim() !== debounced}
              onClick={() => void query.fetchNextPage()}
            >
              Load more cases
            </Button>
          </div>
        ) : null}
      </section>
      <section
        id="available-case-diagnostics"
        className="flex h-[32rem] min-h-0 min-w-0 flex-col rounded-xl border md:h-auto"
        aria-label={selected ? `Diagnostics for ${selected.record.name}` : 'Available diagnostics'}
      >
        <header className="space-y-1 border-b p-3">
          <h3 className="text-sm font-semibold [overflow-wrap:anywhere]" aria-live="polite">
            {selected?.record.name ?? 'Choose a case with supported diagnostics.'}
          </h3>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {selected?.diagnostics ? (
            <DiagnosticRunList
              sources={selected.diagnostics.sources}
              id={`browser-${selected.record.id}`}
              isAdded={isAdded}
              analysis={analysis}
              onAnalysisChange={setAnalysis}
              tool={tool}
              onToolChange={setTool}
              onAdd={(run) =>
                onAdd(
                  toEntry(
                    run,
                    selected.record.id,
                    selected.record.name,
                    caseDetailsPath({
                      machineName: selected.record.machineName,
                      hpcUsername: selected.record.hpcUsername,
                      caseName: selected.record.name,
                    }),
                  ),
                )
              }
              onRemove={onRemove}
            />
          ) : null}
        </div>
      </section>
    </div>
  );
};
