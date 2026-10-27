import assert from 'node:assert/strict';
import test from 'node:test';

import { iiceGroupKey, toBasketEntry } from '../src/lib/iiceBasket.ts';

const viewer = (overrides = {}) => ({
  tool: 'e3sm_diags',
  url: 'https://x.test/a/viewer/',
  subsection: 'atm_monthly_180x360_aave',
  comparison: 'model_vs_obs',
  startYear: 1985,
  endYear: 2014,
  tsStartYear: null,
  tsEndYear: null,
  referenceHint: null,
  ...overrides,
});

test('entries share a group only when tool and comparison mode both match', () => {
  // IICE drives one comparison from one template, so these cannot share a link.
  const obs = { tool: 'e3sm_diags', comparison: 'model_vs_obs' };
  const mvm = { tool: 'e3sm_diags', comparison: 'model_vs_model' };
  const mpas = { tool: 'mpas_analysis', comparison: null };

  assert.notEqual(iiceGroupKey(obs), iiceGroupKey(mvm));
  assert.notEqual(iiceGroupKey(obs), iiceGroupKey(mpas));
  assert.equal(iiceGroupKey(obs), iiceGroupKey({ ...obs, startYear: 1 }));
});

test('a null comparison groups with model-vs-observations', () => {
  // MPAS-Analysis runs carry no comparison; they must still land in one group.
  assert.equal(
    iiceGroupKey({ tool: 'mpas_analysis', comparison: null }),
    iiceGroupKey({ tool: 'mpas_analysis', comparison: 'model_vs_obs' }),
  );
});

test('a staged entry always carries a string reference case', () => {
  // The bar trims this field; undefined would throw and blank the whole app.
  const obs = toBasketEntry(viewer(), 'case-1', 'v3.LR.historical_0101', 'label');
  assert.equal(obs.referenceCase, '');

  const hinted = toBasketEntry(
    viewer({ comparison: 'model_vs_model', referenceHint: 'PI100' }),
    'case-1',
    'v3.LR.historical_0101',
    'label',
  );
  assert.equal(hinted.referenceCase, 'PI100');

  const unhinted = toBasketEntry(
    viewer({ comparison: 'model_vs_model', referenceHint: null }),
    'case-1',
    'v3.LR.historical_0101',
    'label',
  );
  assert.equal(unhinted.referenceCase, '');
});

test('a staged entry keeps the fields the bar renders', () => {
  const entry = toBasketEntry(viewer(), 'case-1', 'v3.LR.historical_0101', 'hist 1985-2014');

  assert.equal(entry.url, 'https://x.test/a/viewer/');
  assert.equal(entry.caseId, 'case-1');
  assert.equal(entry.caseName, 'v3.LR.historical_0101');
  assert.equal(entry.tool, 'e3sm_diags');
  assert.equal(entry.comparison, 'model_vs_obs');
  assert.equal(entry.subsection, 'atm_monthly_180x360_aave');
  assert.deepEqual([entry.startYear, entry.endYear], [1985, 2014]);
  assert.equal(entry.label, 'hist 1985-2014');
});
