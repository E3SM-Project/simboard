import { Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  comparePath,
  type CompareRun,
  isRunUrl,
  MAX_COMPARED_RUNS,
} from '@/features/diagnostics/compareState';

const LCRC = 'https://web.lcrc.anl.gov/public/e3sm/diagnostic_output';
const NERSC = 'https://portal.nersc.gov/project/m2136';
const CLIMO = 'e3sm_diags/180x360_aave/model_vs_obs_1985-2014/viewer/';
const v2Viewer = (run: string) => `${LCRC}/ac.forsyth2/E3SMv2/${run}/${CLIMO}`;
const v1Viewer = (run: string) => `${NERSC}/E3SMv1/e3sm_diags/${run}/${CLIMO}`;
const CRYO_DIAGS = `${LCRC}/wlin/E3SMv2/cryo/20210713.CRYO1850.ne30pg2_SOwISC12to60E2r4.IB_bugfixes.chrysalis/e3sm_diags/180x360_aave`;

/** The comparisons IICE shipped as examples, kept as one-click starting points. */
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

const EMPTY_RUN: CompareRun = { url: '', label: '' };

/**
 * Compare runs by address: the way to compare output someone sent a link to,
 * or runs not yet linked to a SimBoard case.
 */
export const StartPage = () => {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<CompareRun[]>([EMPTY_RUN, EMPTY_RUN]);
  const [problem, setProblem] = useState('');

  const edit = (index: number, patch: Partial<CompareRun>) =>
    setRuns(runs.map((run, i) => (i === index ? { ...run, ...patch } : run)));

  const compare = () => {
    const filled = runs.filter((run) => run.url.trim());
    if (filled.length < 2) return setProblem('Add at least two runs.');
    if (filled.length > MAX_COMPARED_RUNS) {
      return setProblem(`Compare at most ${MAX_COMPARED_RUNS} runs at a time.`);
    }
    const bad = filled.find((run) => !isRunUrl(run.url));
    if (bad) {
      return setProblem(
        `Not a diagnostics run address: ${bad.url}. Use an E3SM Diags …/viewer/ page or an MPAS-Analysis run directory.`,
      );
    }
    navigate(comparePath(filled.map((run) => ({ url: run.url.trim(), label: run.label.trim() }))));
  };

  return (
    <div className="mx-auto w-full max-w-[960px] space-y-6 px-6 py-8">
      <header>
        <h1 className="text-2xl font-semibold text-slate-950">Compare diagnostics</h1>
        <p className="mt-1 text-sm text-slate-600">
          Paste the addresses of public E3SM Diags or MPAS-Analysis runs, or add runs from case
          pages. Only plots every run published are shown.
        </p>
      </header>

      <Card>
        <CardContent className="space-y-3 p-5">
          {runs.map((run, index) => (
            <div key={index} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_220px_auto]">
              <Input
                value={run.url}
                placeholder="https://…/viewer/  or  https://…/mpas_analysis/ts_…/"
                aria-label={`Run ${index + 1} address`}
                onChange={(event) => edit(index, { url: event.target.value })}
              />
              <Input
                value={run.label}
                placeholder="Label (optional)"
                aria-label={`Run ${index + 1} label`}
                onChange={(event) => edit(index, { label: event.target.value })}
              />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setRuns(runs.filter((_, i) => i !== index))}
                disabled={runs.length <= 2}
                aria-label={`Remove run ${index + 1}`}
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          ))}
          {problem ? <p className="text-sm text-red-600">{problem}</p> : null}
          <div className="flex gap-2">
            <Button onClick={compare}>Compare</Button>
            <Button
              variant="outline"
              onClick={() => setRuns([...runs, EMPTY_RUN])}
              disabled={runs.length >= MAX_COMPARED_RUNS}
            >
              <Plus className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
              Add run
            </Button>
          </div>
        </CardContent>
      </Card>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-950">Examples</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {EXAMPLES.map((example) => (
            <Card key={example.name}>
              <CardContent className="flex items-center justify-between gap-3 p-4">
                <h3 className="text-sm font-medium text-slate-900">{example.name}</h3>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(comparePath(example.runs))}
                >
                  Open
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
};
