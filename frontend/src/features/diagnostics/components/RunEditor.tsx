import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';

import { listCases } from '@/api/catalog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { getCaseDiagnosticsRuns } from '@/features/diagnostics/api';
import {
  type BasketEntry,
  type CompareRun,
  displayLabel,
  entryLabel,
  groupKey,
  isRunUrl,
  MAX_COMPARED_RUNS,
  toEntry,
} from '@/features/diagnostics/compareState';
import { useComparisonBasket } from '@/features/diagnostics/comparisonBasket';
import { DiagnosticRunList } from '@/features/diagnostics/components/DiagnosticRunList';
import { RUN_GROUPS } from '@/features/diagnostics/discoveryState';
import type { CaseDiagnosticsOut } from '@/features/diagnostics/types';
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

interface DraftRun extends CompareRun {
  entry?: BasketEntry;
}

interface RunEditorProps {
  initialRuns: CompareRun[];
  onApply: (runs: CompareRun[], entries: BasketEntry[]) => string | void;
  onCancel?: () => void;
}

/** One draft for indexed case discovery and IICE-compatible manual addresses. */
export const RunEditor = ({ initialRuns, onApply, onCancel }: RunEditorProps) => {
  const basket = useComparisonBasket();
  const [runs, setRuns] = useState<DraftRun[]>(initialRuns);
  const [problem, setProblem] = useState('');
  const [manual, setManual] = useState<CompareRun>({ url: '', label: '' });
  const [importGroup, setImportGroup] = useState('');
  const trayGroups = [...new Set(basket.entries.map(groupKey))];
  const known = runs.find(
    (run) => run.entry || basket.entries.some((entry) => entry.url === run.url),
  );
  const knownEntry = known?.entry ?? basket.entries.find((entry) => entry.url === known?.url);
  const desiredGroup = importGroup || (knownEntry ? groupKey(knownEntry) : '');
  const activeImportGroup = trayGroups.includes(desiredGroup) ? desiredGroup : trayGroups[0];
  const knownKinds = new Set(runs.flatMap((run) => (run.entry ? [groupKey(run.entry)] : [])));

  const edit = (index: number, patch: Partial<CompareRun>) =>
    setRuns(
      runs.map((run, i) =>
        i === index
          ? { ...run, ...patch, entry: patch.url && patch.url !== run.url ? undefined : run.entry }
          : run,
      ),
    );

  const add = (run: DraftRun) => {
    if (!isRunUrl(run.url))
      return setProblem(
        'Use an HTTPS E3SM Diags viewer page or an MPAS-Analysis run directory, not a general resource directory.',
      );
    if (runs.some((item) => item.url === run.url.trim() && item.label === run.label.trim()))
      return setProblem(
        'This run and label are already selected. Choose another case, time range, or IICE case override.',
      );
    if (runs.length >= MAX_COMPARED_RUNS)
      return setProblem(`Compare at most ${MAX_COMPARED_RUNS} runs at a time.`);
    setRuns([...runs, { ...run, url: run.url.trim(), label: run.label.trim() }]);
    setProblem('');
    setManual({ url: '', label: '' });
  };

  const apply = (next: DraftRun[]) => {
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
    const error = onApply(
      next.map(({ url, label }) => ({ url: url.trim(), label: label.trim() })),
      next.flatMap((run) => (run.entry ? [run.entry] : [])),
    );
    if (error) setProblem(error);
  };

  return (
    <div className="min-w-0 space-y-5">
      <Tabs defaultValue="browse">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="browse">Browse SimBoard</TabsTrigger>
          <TabsTrigger value="url">Add by URL</TabsTrigger>
        </TabsList>
        <TabsContent value="browse" className="space-y-3">
          <CaseBrowser
            isAdded={(url) => runs.some((run) => run.url === url)}
            onAdd={(entry) => add({ url: entry.url, label: entryLabel(entry), entry })}
            onRemove={(url) => setRuns(runs.filter((run) => run.url !== url))}
          />
        </TabsContent>
        <TabsContent value="url" className="space-y-4">
          <form
            className="space-y-3 rounded-lg border p-3"
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
          <details className="rounded-lg border p-3">
            <summary className="cursor-pointer text-sm font-medium">
              IICE example comparisons
            </summary>
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
      <section className="space-y-3 border-t pt-4" aria-label="Selected runs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">
            Selected runs ({runs.length}/{MAX_COMPARED_RUNS})
          </h2>
          {basket.entries.length ? (
            <div className="flex max-w-full flex-wrap items-center gap-2">
              {trayGroups.length > 1 ? (
                <Select value={activeImportGroup} onValueChange={setImportGroup}>
                  <SelectTrigger
                    aria-label="Tray group to import"
                    className="w-full text-xs sm:w-64"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {trayGroups.map((key) => (
                      <SelectItem key={key} value={key}>
                        {RUN_GROUPS.find((group) => group.key === key)?.title ?? key}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  const selected = [...runs];
                  for (const entry of basket.entries.filter(
                    (entry) => groupKey(entry) === activeImportGroup,
                  ))
                    if (!selected.some((run) => run.url === entry.url))
                      selected.push({ url: entry.url, label: entryLabel(entry), entry });
                  if (selected.length > MAX_COMPARED_RUNS)
                    setProblem(
                      `Select at most ${MAX_COMPARED_RUNS} runs. Remove some from the tray before importing.`,
                    );
                  else {
                    setRuns(selected);
                    setProblem('');
                  }
                }}
              >
                Import tray selections
              </Button>
            </div>
          ) : null}
        </div>
        {!runs.length ? (
          <p className="text-sm text-slate-500">
            Choose diagnostics above, import tray selections, or open an example. Only shared plots
            appear in comparisons.
          </p>
        ) : null}
        {knownKinds.size > 1 ? (
          <p role="status" className="text-sm text-amber-800">
            These selections include different diagnostic kinds and may have no shared plots.
            Compare matching tools and comparison types.
          </p>
        ) : null}
        {runs.map((run, index) => (
          <div key={index} className="space-y-2 rounded-lg border p-3">
            <div className="flex items-center justify-between gap-2">
              <a
                className="min-w-0 break-words text-sm font-medium hover:underline"
                href={run.url}
                target="_blank"
                rel="noreferrer"
                title={run.url}
              >
                {displayLabel(run)}
              </a>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label={`Remove run ${index + 1}`}
                onClick={() => setRuns(runs.filter((_, i) => i !== index))}
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <Input
                aria-label={`Run ${index + 1} address`}
                value={run.url}
                onChange={(event) => edit(index, { url: event.target.value })}
              />
              <Input
                aria-label={`Run ${index + 1} label`}
                placeholder="Label (optional)"
                value={run.label}
                onChange={(event) => edit(index, { label: event.target.value })}
              />
            </div>
          </div>
        ))}
      </section>
      {problem ? (
        <p role="alert" className="text-sm text-red-600">
          {problem}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button type="button" onClick={() => apply(runs)}>
          {onCancel ? 'Apply changes' : 'Compare'}
        </Button>
        {onCancel ? (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
      </div>
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
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [caseId, setCaseId] = useState<string | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(search.trim());
      setCaseId(null);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);
  const query = useInfiniteQuery({
    queryKey: ['diagnostics', 'supported-cases', debounced],
    initialPageParam: 1,
    queryFn: async ({ pageParam, signal }) => {
      const page = await listCases({
        search: debounced || undefined,
        page: pageParam,
        pageSize: 6,
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
                return { record, diagnostics };
              } catch {
                return { record, diagnostics: null };
              }
            }),
          )),
        );
      }
      return {
        cases,
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
  const selected = supported.find((item) => item.record.id === caseId);
  const incomplete = checked.some(
    (item) =>
      !item.diagnostics ||
      item.diagnostics.sources.some((source) => source.error || source.partial),
  );

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <Label htmlFor="diagnostic-case-search">Search cases with supported diagnostics</Label>
        <Input
          id="diagnostic-case-search"
          value={search}
          placeholder="Search by case name"
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>
      <p className="text-xs text-slate-500">
        Only confirmed E3SM Diags and MPAS-Analysis runs appear. General zppy directories are not
        comparison runs.
      </p>
      <div role="status" className="text-sm text-slate-500">
        {query.isFetching
          ? 'Checking cases for supported diagnostics…'
          : !supported.length
            ? query.hasNextPage
              ? 'No supported cases in checked results. Load more or narrow your search.'
              : incomplete
                ? 'No supported cases found; some archives could not be checked.'
                : 'No supported cases found.'
            : `${supported.length} supported cases found in checked results.`}
      </div>
      {query.isError || incomplete ? (
        <div className="flex flex-wrap items-center gap-2 text-sm text-amber-800">
          <span>Some results could not be read.</span>
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
                      item.diagnostics.sources.some((source) => source.error || source.partial),
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
        </div>
      ) : null}
      <ul className="max-h-48 space-y-1 overflow-y-auto">
        {supported.map(({ record, diagnostics }) => (
          <li key={record.id}>
            <Button
              type="button"
              variant={record.id === caseId ? 'secondary' : 'ghost'}
              className="h-auto w-full justify-start whitespace-normal break-words text-left"
              aria-pressed={record.id === caseId}
              onClick={() => setCaseId(record.id)}
            >
              {record.name} ·{' '}
              {diagnostics?.sources.reduce((count, source) => count + source.runs.length, 0)} runs
            </Button>
          </li>
        ))}
      </ul>
      {query.hasNextPage ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={query.isFetching || search.trim() !== debounced}
          onClick={() => void query.fetchNextPage()}
        >
          Load more cases
        </Button>
      ) : null}
      {selected ? (
        <section
          className="space-y-4 rounded-lg border p-3"
          aria-label={`Diagnostics for ${selected.record.name}`}
        >
          <h3 className="break-words text-sm font-semibold">{selected.record.name}</h3>
          {selected.record.latestExecution ? (
            <p className="break-words text-xs text-slate-500">
              Latest case execution: {selected.record.latestExecution.executionId} (not diagnostic
              run provenance)
            </p>
          ) : null}
          {selected.diagnostics?.sources.map((source, index) => (
            <DiagnosticRunList
              key={source.rootUrl}
              source={source}
              id={`browser-${selected.record.id}-${index}`}
              isAdded={isAdded}
              onAdd={(run) => onAdd(toEntry(run, selected.record.id, selected.record.name))}
              onRemove={onRemove}
            />
          ))}
        </section>
      ) : null}
    </div>
  );
};
