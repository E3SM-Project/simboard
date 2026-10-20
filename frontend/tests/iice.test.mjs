import assert from 'node:assert/strict';
import test from 'node:test';
import { URL } from 'node:url';

import {
  buildIiceLink,
  formatIiceLabel,
  normalizeIiceViewerUrl,
  suggestIiceLabel,
  validateIiceLink,
} from '../src/lib/iice.ts';

const V2_HIST =
  'https://web.lcrc.anl.gov/public/e3sm/diagnostic_output/ac.forsyth2/E3SMv2/v2.LR.historical_0101/e3sm_diags/180x360_aave/model_vs_obs_1985-2014/viewer/';
const V1_HIST =
  'https://portal.nersc.gov/project/m2136/E3SMv1/e3sm_diags/20180215.DECKv1b_H1.ne30_oEC.edison/e3sm_diags/180x360_aave/model_vs_obs_1985-2014/viewer/';

const query = (link) => Object.fromEntries(new URL(link).searchParams.entries());

test('builds the e3sm_diags CGI link IICE itself would produce', () => {
  const link = buildIiceLink({
    tool: 'e3sm_diags',
    entries: [
      { url: V2_HIST, label: 'v2 hist' },
      { url: V1_HIST, label: 'v1 hist' },
    ],
  });

  assert.ok(link.startsWith('https://portal.nersc.gov/project/m2136/bin/iice/iice.cgi?'));
  assert.deepEqual(query(link), {
    url1: V2_HIST.replace(/\/$/, ''),
    label1: 'v2 hist',
    url2: V1_HIST.replace(/\/$/, ''),
    label2: 'v1 hist',
    dconfig: 'vsObs',
  });
  // Spaces are %20, nothing else is escaped, matching copycmplink().
  assert.match(link, /label1=v2%20hist&/);
  assert.doesNotMatch(link, /%3A|%2F/);
});

test('mpas-analysis entries go to the mpas-a CGI with the coupled template', () => {
  const link = buildIiceLink({
    tool: 'mpas_analysis',
    entries: [
      { url: 'https://x.test/a/mpas_analysis/ts_1850-2014_climo_1985-2014/', label: 'a' },
      { url: 'https://x.test/b/mpas_analysis/ts_1850-2014_climo_1985-2014/', label: 'b' },
    ],
  });
  assert.ok(link.startsWith('https://portal.nersc.gov/project/m2136/bin/iice/mpas-a.cgi?'));
  assert.equal(query(link).dconfig, 'wcycl');
  assert.equal(
    buildIiceLink({
      tool: 'mpas_analysis',
      entries: [{ url: 'https://x.test/', label: 'a' }],
      dconfig: 'cryo',
    }).endsWith('dconfig=cryo'),
    true,
  );
});

test('a reference case switches to the vsModel template and tags the label', () => {
  const link = buildIiceLink({
    tool: 'e3sm_diags',
    entries: [
      {
        url: 'https://x.test/hist/viewer/',
        label: 'hist 1995-2024',
        referenceCase: 'v3.LR.piControl',
      },
      { url: 'https://x.test/amip/viewer/', label: 'amip 1995-2024' },
    ],
  });
  const q = query(link);
  assert.equal(q.dconfig, 'vsModel');
  assert.equal(q.label1, '!v3.LR.piControl hist 1995-2024');
  assert.equal(q.label2, 'amip 1995-2024');
});

test('explicit dconfig wins over inference', () => {
  const link = buildIiceLink({
    tool: 'e3sm_diags',
    entries: [{ url: 'https://x.test/a/viewer/', label: 'a', referenceCase: 'ref' }],
    dconfig: 'vsObs',
  });
  assert.equal(query(link).dconfig, 'vsObs');
});

test('deep-link parameters are appended in IICE order', () => {
  const link = buildIiceLink({
    tool: 'e3sm_diags',
    entries: [{ url: 'https://x.test/a/viewer', label: 'a' }],
    category: 'display',
    plot: 'lat_lon/GPCP_v2.3/GPCP_v2.3-PRECT-ANN-global.png',
    diff: 1,
  });
  assert.equal(
    link,
    'https://portal.nersc.gov/project/m2136/bin/iice/iice.cgi?url1=https://x.test/a/viewer&label1=a&category=display&plot=lat_lon/GPCP_v2.3/GPCP_v2.3-PRECT-ANN-global.png&diff=1&dconfig=vsObs',
  );
});

test('returns null with nothing to compare and skips blank urls', () => {
  assert.equal(buildIiceLink({ tool: 'e3sm_diags', entries: [] }), null);
  assert.equal(buildIiceLink({ tool: 'e3sm_diags', entries: [{ url: '  ', label: 'x' }] }), null);
  const link = buildIiceLink({
    tool: 'e3sm_diags',
    entries: [
      { url: '', label: 'skipped' },
      { url: 'https://x.test/a/viewer/', label: 'kept' },
    ],
  });
  assert.equal(query(link).url1, 'https://x.test/a/viewer');
  assert.equal(query(link).label1, 'kept');
  assert.equal(query(link).url2, undefined);
});

test('labels are flattened to one line and stripped of ampersands', () => {
  assert.equal(formatIiceLabel({ url: 'u', label: ' a\nb & c ' }), 'a b c');
  assert.equal(formatIiceLabel({ url: 'u', label: 'x', referenceCase: '  ref  ' }), '!ref x');
  assert.equal(formatIiceLabel({ url: 'u', label: 'x', referenceCase: '' }), 'x');
});

test('viewer urls lose trailing slashes, as the CGI re-emits them', () => {
  assert.equal(normalizeIiceViewerUrl('https://x.test/viewer///'), 'https://x.test/viewer');
  assert.equal(normalizeIiceViewerUrl('  https://x.test/viewer  '), 'https://x.test/viewer');
});

test('validation rejects mixing model-vs-obs and model-vs-model runs', () => {
  // IICE drives one comparison from one template, so these cannot share a link.
  const mixed = validateIiceLink({
    tool: 'e3sm_diags',
    entries: [
      { url: 'a', label: 'obs run' },
      { url: 'b', label: 'mvm run', referenceCase: 'v3.LR.piControl' },
    ],
  });
  assert.deepEqual(
    mixed.map((p) => p.code),
    ['mixed_comparison_modes'],
  );

  const allModel = validateIiceLink({
    tool: 'e3sm_diags',
    entries: [
      { url: 'a', label: 'x', referenceCase: 'v3.LR.piControl' },
      { url: 'b', label: 'y', referenceCase: 'v3.LR.piControl' },
    ],
  });
  assert.deepEqual(allModel, []);
});

test('validation asks for at least two entries', () => {
  assert.deepEqual(
    validateIiceLink({ tool: 'e3sm_diags', entries: [{ url: 'u', label: 'l' }] }).map(
      (p) => p.code,
    ),
    ['too_few_entries'],
  );
  assert.deepEqual(
    validateIiceLink({
      tool: 'e3sm_diags',
      entries: [
        { url: 'u', label: 'l' },
        { url: 'v', label: 'm' },
      ],
    }),
    [],
  );
});

test('suggested labels pair the case with a zero-padded period', () => {
  assert.equal(
    suggestIiceLabel('v3.LR.piControl', { startYear: 1, endYear: 50 }),
    'v3.LR.piControl 0001-0050',
  );
  assert.equal(
    suggestIiceLabel('v3.LR.historical_0101', { startYear: 1985, endYear: 2014 }),
    'v3.LR.historical_0101 1985-2014',
  );
  assert.equal(suggestIiceLabel('v3.LR.amip_0101'), 'v3.LR.amip_0101');
  assert.equal(suggestIiceLabel('x', { startYear: null, endYear: 2014 }), 'x');
});
