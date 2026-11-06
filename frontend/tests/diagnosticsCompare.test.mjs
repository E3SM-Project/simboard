import assert from 'node:assert/strict';
import test from 'node:test';
import { URLSearchParams } from 'node:url';

import {
  comparePath,
  compareSearch,
  displayLabel,
  entryLabel,
  groupKey,
  imageUrl,
  isRunUrl,
  parseCompareState,
  runPeriod,
  reconcileBasket,
  toEntry,
} from '../src/features/diagnostics/compareState.ts';
import {
  diagnosticClimatologyPeriod,
  diagnosticIdentifier,
  diagnosticPeriod,
  diagnosticTimeSeriesPeriod,
  diagnosticTitle,
  periodGroups,
  relatedDirectories,
  resourceTarget,
} from '../src/features/diagnostics/discoveryState.ts';

const LCRC = 'https://web.lcrc.anl.gov/public/e3sm/diagnostic_output';
const VIEWER = `${LCRC}/x/case/e3sm_diags/a/model_vs_obs_1985-2014/viewer/`;

const run = (overrides = {}) => ({
  tool: 'e3sm_diags',
  url: VIEWER,
  subsection: 'atm_monthly_180x360_aave',
  comparison: 'model_vs_obs',
  startYear: 1985,
  endYear: 2014,
  tsStartYear: null,
  tsEndYear: null,
  ...overrides,
});

test('comparison state round-trips through the URL', () => {
  const state = {
    runs: [
      { url: VIEWER, label: 'Historical 1985-2014' },
      { url: `${LCRC}/y/viewer/`, label: 'has | a pipe' },
    ],
    set: 'polar',
    plot: 'polar/GPCP/PRECT-ANN-polar_N',
    view: 'diff',
  };
  const parsed = parseCompareState(new URLSearchParams(compareSearch(state)));
  assert.deepEqual(parsed, {
    ...state,
    runs: [state.runs[0], { url: `${LCRC}/y/viewer/`, label: 'has   a pipe' }],
  });
});

test('defaults are left out of the URL and restored when read', () => {
  const path = comparePath([{ url: VIEWER, label: '' }]);
  assert.equal(path, `/diagnostics/compare?run=${encodeURIComponent(`${VIEWER}|`)}`);
  const state = parseCompareState(new URLSearchParams('run=x&view=bogus'));
  assert.deepEqual(state, { runs: [{ url: 'x', label: '' }], set: null, plot: null, view: 'test' });
});

test('labels preserve supplied text and shorten only the unlabeled UI fallback', () => {
  assert.equal(displayLabel({ url: VIEWER, label: '!my.case yrs 1-10' }), 'my.case yrs 1-10');
  assert.equal(displayLabel({ url: VIEWER, label: 'a!b' }), 'a!b');
  assert.equal(displayLabel({ url: VIEWER, label: '' }), 'case 1985-2014');
  assert.equal(displayLabel({ url: 'https://example.test/', label: '' }), 'example.test');
  assert.equal(displayLabel({ url: 'not a URL', label: '' }), 'Diagnostic run');
  assert.equal(
    parseCompareState(
      new URLSearchParams(
        compareSearch({ runs: [{ url: VIEWER, label: '' }], set: null, plot: null, view: 'test' }),
      ),
    ).runs[0].url,
    VIEWER,
  );
});

test('run periods are zero-padded model years', () => {
  assert.equal(runPeriod({ startYear: 1, endYear: 50 }), '0001-0050');
  assert.equal(runPeriod({ startYear: null, endYear: 50 }), '');
});

test('discovery groups actual periods across sources and keeps unique runs', () => {
  const obs = run();
  const model = run({
    url: `${LCRC}/model/viewer/`,
    comparison: 'model_vs_model',
    subsection: 'atm_monthly_180x360_aave_mvm_PI100',
  });
  const early = run({ url: `${LCRC}/early/viewer/`, startYear: 1, endYear: 50 });
  const unknown = run({
    url: `${LCRC}/ambiguous_1985-2014/viewer/`,
    startYear: null,
    endYear: null,
  });
  assert.deepEqual(periodGroups([{ runs: [unknown, obs] }, { runs: [model, obs, early] }]), [
    ['0001–0050', [early]],
    ['1985–2014', [obs, model]],
    ['Unknown period', [unknown]],
  ]);
  assert.equal(diagnosticPeriod(unknown), 'Unknown period');
  assert.equal(diagnosticPeriod(run({ startYear: null })), 'Unknown period');
  assert.deepEqual(periodGroups([]), []);
});

test('diagnostic rows retain exact identifiers and explicit comparison metadata', () => {
  for (const subsection of [
    'atm_monthly_180x360_aave',
    'atm_monthly_180x360_aave_mvm_PI100',
    'lnd_monthly_mvm_lnd',
  ]) {
    assert.equal(diagnosticIdentifier(run({ subsection })), subsection);
  }
  assert.equal(diagnosticTitle(run()), 'Climatology · Model vs. Observations');
  assert.equal(
    diagnosticTitle(run({ comparison: 'model_vs_model' })),
    'Climatology · Model vs. Model',
  );
  assert.equal(diagnosticTitle(run({ comparison: null })), 'Climatology');
  assert.equal(
    diagnosticIdentifier(
      run({
        subsection: null,
        url: `${LCRC}/case/e3sm_diags/atm_monthly_180x360_aave/model_vs_obs_1985-2014/viewer/`,
      }),
    ),
    'atm_monthly_180x360_aave',
  );
  assert.equal(
    diagnosticIdentifier(run({ subsection: null, url: `${LCRC}/case/e3sm_diags/index.html` })),
    'Identifier unavailable',
  );
});

test('MPAS keeps both analysis periods without inventing comparison categories', () => {
  const mpas = run({
    tool: 'mpas_analysis',
    url: `${LCRC}/case/mpas_analysis/ts_0001-0500_climo_0451-0500/`,
    subsection: null,
    comparison: null,
    startYear: 451,
    endYear: 500,
    tsStartYear: 1,
    tsEndYear: 500,
  });
  assert.equal(diagnosticPeriod(mpas), '0451–0500');
  assert.equal(diagnosticClimatologyPeriod(mpas), '0451–0500');
  assert.equal(diagnosticPeriod(mpas, 'climatology'), '0451–0500');
  assert.equal(diagnosticPeriod(mpas, 'time_series'), '0001–0500');
  assert.equal(diagnosticTimeSeriesPeriod(mpas), '0001–0500');
  assert.equal(diagnosticTitle(mpas), 'Climatology · Time Series');
  assert.equal(diagnosticIdentifier(mpas), 'ts_0001-0500_climo_0451-0500');
  const timeSeries = { ...mpas, startYear: null, endYear: null };
  assert.equal(diagnosticPeriod(timeSeries), '0001–0500');
  assert.equal(diagnosticTitle(timeSeries), 'Time Series');
  const unknown = { ...timeSeries, tsStartYear: null, tsEndYear: null };
  assert.equal(diagnosticPeriod(unknown), 'Unknown period');
  assert.equal(diagnosticTitle(unknown), 'Diagnostic run');
});

test('analysis filters regroup whole runs using only the matching indexed years', () => {
  const obs = run();
  const mpas = run({
    tool: 'mpas_analysis',
    url: `${LCRC}/case/mpas_analysis/ts_0001-0100_climo_0051-0100/`,
    comparison: null,
    subsection: null,
    startYear: 51,
    endYear: 100,
    tsStartYear: 1,
    tsEndYear: 100,
  });
  const timeSeries = { ...mpas, url: `${LCRC}/time-series/`, startYear: null, endYear: null };
  const unknown = run({
    url: `${LCRC}/ambiguous_1985-2014/viewer/`,
    startYear: null,
    endYear: null,
  });
  const sources = [{ runs: [obs, mpas, timeSeries, unknown] }, { runs: [mpas] }];
  const original = globalThis.structuredClone(sources);
  assert.deepEqual(periodGroups(sources), [
    ['0001–0100', [timeSeries]],
    ['0051–0100', [mpas]],
    ['1985–2014', [obs]],
    ['Unknown period', [unknown]],
  ]);
  assert.deepEqual(periodGroups(sources, 'climatology'), [
    ['0051–0100', [mpas]],
    ['1985–2014', [obs]],
  ]);
  assert.deepEqual(periodGroups(sources, 'time_series'), [['0001–0100', [mpas, timeSeries]]]);
  assert.equal(periodGroups(sources, 'time_series')[0][1][0], mpas);
  assert.deepEqual(sources, original);
  assert.equal(diagnosticPeriod(unknown, 'climatology'), 'Unknown period');
  assert.equal(diagnosticPeriod(unknown, 'time_series'), 'Unknown period');
});

test('analysis filters do not classify missing or incomplete periods from names', () => {
  const partial = run({ startYear: null, tsStartYear: 1, tsEndYear: null });
  assert.deepEqual(periodGroups([{ runs: [partial] }]), [['Unknown period', [partial]]]);
  assert.deepEqual(periodGroups([{ runs: [partial] }], 'climatology'), []);
  assert.deepEqual(periodGroups([{ runs: [partial] }], 'time_series'), []);
  assert.deepEqual(periodGroups([{ runs: [run()] }], 'time_series'), []);
});

test('isRunUrl accepts the layouts the backend reads', () => {
  for (const url of [
    VIEWER,
    `${VIEWER}index.html`,
    `${LCRC}/x/case/mpas_analysis/ts_0001-0050_climo_0001-0050/`,
    `${LCRC}/ac.x/case/yrs1-10/`,
    `${LCRC}/case_yrs1-10/html/`,
  ]) {
    assert.ok(isRunUrl(url), url);
  }
  for (const url of ['http://insecure/viewer/', `${LCRC}/x/case/`, 'not a url']) {
    assert.ok(!isRunUrl(url), url);
  }
});

test('image URLs encode each path segment', () => {
  assert.equal(
    imageUrl('https://h.test/run/', 'lat_lon/Cloud Calipso/a b.png'),
    'https://h.test/run/lat_lon/Cloud%20Calipso/a%20b.png',
  );
});

test('runs group by tool and kind; MPAS runs are one group', () => {
  const obs = toEntry(run(), 'c1', 'v3.LR.historical');
  const mvm = toEntry(run({ comparison: 'model_vs_model' }), 'c1', 'v3.LR.historical');
  const mpas = toEntry(run({ tool: 'mpas_analysis', comparison: null }), 'c2', 'v3.LR.piControl');
  assert.notEqual(groupKey(obs), groupKey(mvm));
  assert.equal(groupKey(mpas), 'mpas_analysis');
  assert.equal(entryLabel(obs), 'v3.LR.historical 1985-2014');
});

test('resource matching respects origin, path boundaries, and common parent sections', () => {
  const root = `${LCRC}/x/case/`;
  const sources = [
    {
      rootUrl: root,
      runs: [
        run(),
        run({ tool: 'mpas_analysis', comparison: null, url: `${root}mpas_analysis/ts_0001-0050/` }),
      ],
    },
  ];
  assert.equal(resourceTarget('c1', root, sources), 'diagnostics-c1-source-0');
  assert.equal(
    resourceTarget('c1', VIEWER, sources),
    'diagnostics-c1-source-0-e3sm_diags:model_vs_obs',
  );
  assert.equal(
    resourceTarget('c1', `${root}mpas_analysis/`, sources),
    'diagnostics-c1-source-0-mpas_analysis',
  );
  assert.equal(resourceTarget('c1', `${root}raw_output/`, sources), null);
  assert.equal(
    resourceTarget('c1', `${LCRC}/x/`, [
      ...sources,
      { rootUrl: `${LCRC}/x/other/`, runs: [run({ url: `${LCRC}/x/other/viewer/` })] },
    ]),
    'diagnostics-c1',
  );
  assert.equal(resourceTarget('c1', root, [{ rootUrl: root, runs: [] }]), null);
  assert.equal(relatedDirectories(root, `${LCRC}/x/case-other/`), false);
  assert.equal(relatedDirectories(root, root.replace('https:', 'http:')), false);
  assert.equal(relatedDirectories(root, `${root}?different=1`), false);
  assert.equal(relatedDirectories('not a URL', root), false);
});

test('workspace edits reconcile only explicit known selections and respect basket limits', () => {
  const a = toEntry(run(), 'c1', 'Case one');
  const b = toEntry(run({ url: `${LCRC}/b/viewer/` }), 'c2', 'Case two');
  const c = toEntry(run({ url: `${LCRC}/c/viewer/` }), 'c3', 'Case three');
  assert.deepEqual(reconcileBasket([a, b], [a.url], [c.url], [c]), [b, c]);
  assert.deepEqual(reconcileBasket([a, b], [], ['https://external.test/viewer/'], []), [a, b]);
  assert.deepEqual(reconcileBasket([a], [a.url], [a.url], [a]), [a]);
  assert.equal(
    reconcileBasket(
      Array.from({ length: 6 }, (_, i) => ({ ...a, url: `${LCRC}/${i}/viewer/` })),
      [],
      [c.url],
      [c],
    ),
    null,
  );
});
