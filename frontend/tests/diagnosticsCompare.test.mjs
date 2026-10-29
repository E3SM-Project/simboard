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
  toEntry,
} from '../src/features/diagnostics/compareState.ts';

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

test('labels hide the MPAS override mark and fall back to the URL', () => {
  assert.equal(displayLabel({ url: VIEWER, label: '!my.case yrs 1-10' }), 'my.case yrs 1-10');
  assert.equal(displayLabel({ url: VIEWER, label: 'a!b' }), 'a!b');
  assert.equal(displayLabel({ url: VIEWER, label: '' }), VIEWER);
});

test('run periods are zero-padded model years', () => {
  assert.equal(runPeriod({ startYear: 1, endYear: 50 }), '0001-0050');
  assert.equal(runPeriod({ startYear: null, endYear: 50 }), '');
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
