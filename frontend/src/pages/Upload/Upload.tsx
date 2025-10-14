import { useMemo, useState } from 'react';

import FormSection from '@/pages/Upload/FormSection';
import FormTokenInput from '@/pages/Upload/FormTokenInput';
import StickyActionsBar from '@/pages/Upload/StickyActionsBar';
import { SimulationCreate } from '@/types';

// -------------------- Types & Interfaces --------------------
type OpenKey =
  | 'configuration'
  | 'modelSetup'
  | 'versionControl'
  | 'paths'
  | 'docs'
  | 'review'
  | null;

// -------------------- Pure Helpers --------------------
/**
 * Counts the number of valid (non-null and non-undefined) fields in an array.
 *
 * @param fields - An array of fields that can be strings, null, or undefined.
 * @returns The count of valid fields in the array.
 */
const countValidfields = (fields: (string | null | undefined)[]) =>
  fields.reduce((count, field) => (field ? count + 1 : count), 0);

// The number of required fields per section to track progress.
const REQUIRED_FIELDS = {
  config: 4,
  model: 2,
  version: 2,
  paths: 2,
};

const initialState: SimulationCreate = {
  // Required fields
  name: '',
  caseName: '',
  compset: '',
  compsetAlias: '',
  gridName: '',
  gridResolution: '',
  initializationType: '',
  simulationType: 'production',
  status: 'not-started',
  machineId: '',
  simulationStartDate: '',

  // Optional fields
  gitTag: null,
  gitCommitHash: null,
  parentSimulationId: null,
  campaignId: null,
  experimentTypeId: null,
  groupName: null,
  simulationEndDate: null,
  totalYears: null,
  runStartDate: null,
  runEndDate: null,
  compiler: null,
  notesMarkdown: null,
  knownIssues: null,
  gitBranch: null,
  gitRepoUrl: null,
  createdBy: null,
  createdAt: null,
  lastModified: null,
  lastEditedBy: null,
  lastEditedAt: null,
  extra: {},

  // Relationships
  artifacts: null,
  links: null,
};

const Upload = () => {
  // -------------------- Local State --------------------
  const [open, setOpen] = useState<OpenKey>('configuration');
  const [form, setForm] = useState<SimulationCreate>(initialState);

  const [variables, setVariables] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [diagLinks, setDiagLinks] = useState<{ label: string; url: string }[]>([]);
  const [paceLinks, setPaceLinks] = useState<{ label: string; url: string }[]>([]);

  // -------------------- Derived Data --------------------
  const formWithVars = useMemo(() => ({ ...form, variables }), [form, variables]);

  const configSat = useMemo(() => {
    const fields = [
      form.name,
      form.status && form.status !== 'not-started' ? form.status : null,
      form.campaignId,
      form.experimentTypeId,
    ];
    return countValidfields(fields);
  }, [form.name, form.status, form.campaignId, form.experimentTypeId]);

  const modelSat = useMemo(() => {
    const fields = [form.machineId, form.compiler];
    return countValidfields(fields);
  }, [form.machineId, form.compiler]);

  const versionSat = useMemo(() => {
    const fields = [form.gitBranch, form.gitCommitHash];
    return countValidfields(fields);
  }, [form.gitBranch, form.gitCommitHash]);

  const pathsSat = useMemo(() => {
    const fields = [
      form.outputPath,
      Array.isArray(form.runScriptPaths) && form.runScriptPaths.length ? 'valid' : null,
    ];
    return countValidfields(fields);
  }, [form.outputPath, form.runScriptPaths]);

  const allValid = useMemo(() => {
    return (
      configSat >= REQUIRED_FIELDS.config &&
      modelSat >= REQUIRED_FIELDS.model &&
      versionSat >= REQUIRED_FIELDS.version
    );
  }, [configSat, modelSat, versionSat]);

  // -------------------- Handlers --------------------
  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const toggle = (k: OpenKey) => setOpen((prev) => (prev === k ? null : k));

  const addDiag = () => setDiagLinks([...diagLinks, { label: '', url: '' }]);
  const setDiag = (i: number, field: 'label' | 'url', v: string) => {
    const next = diagLinks.slice();
    next[i][field] = v;
    setDiagLinks(next);
    setForm((p) => ({ ...p, diagnosticLinks: next }));
  };

  const addPace = () => setPaceLinks([...paceLinks, { label: '', url: '' }]);
  const setPace = (i: number, field: 'label' | 'url', v: string) => {
    const next = paceLinks.slice();
    next[i][field] = v;
    setPaceLinks(next);
    setForm((p) => ({ ...p, paceLinks: next }));
  };

  const handleBatchLogPathsChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setForm((p) => ({
      ...p,
      batchLogPaths: e.target.value
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
    }));
  };

  // -------------------- Render --------------------
  return (
    <div className="w-full min-h-[calc(100vh-64px)] bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 md:px-6 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-bold">Upload a New Simulation</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Provide configuration and context. You can save a draft at any time.
          </p>
        </header>

        <FormSection
          title="Configuration"
          isOpen={open === 'configuration'}
          onToggle={() => toggle('configuration')}
          requiredCount={REQUIRED_FIELDS.config}
          satisfiedCount={configSat}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="text-sm font-medium">
                Simulation Name <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="name"
                value={form.name}
                onChange={handleChange}
                placeholder="e.g., 20190815.ne30_oECv3_ICG.A_WCYCL1850S_CMIP6.piControl"
              />
            </div>
            <div>
              <label className="text-sm font-medium">
                Status <span className="text-red-500">*</span>
              </label>
              <select
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="status"
                value={form.status}
                onChange={handleChange}
              >
                <option value="not-started">Not started</option>
                <option value="running">Running</option>
                <option value="complete">Complete</option>
                <option value="failed">Failed</option>
              </select>
            </div>

            <div>
              <label className="text-sm font-medium">
                Campaign <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="campaignId"
                value={form.campaignId}
                onChange={handleChange}
                placeholder="e.g., v3.LR"
              />
            </div>
            <div>
              <label className="text-sm font-medium">
                Experiment Type <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="experimentTypeId"
                value={form.experimentTypeId}
                onChange={handleChange}
                placeholder="e.g., piControl"
              />
            </div>

            <div className="md:col-span-2">
              <label className="text-sm font-medium">
                Target Variables{' '}
                <span className="text-xs text-muted-foreground ml-1">(optional)</span>
              </label>
              <div className="mt-1">
                <FormTokenInput
                  values={variables}
                  setValues={setVariables}
                  placeholder="ts, pr, huss…"
                />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Add model variables relevant to this simulation (comma or Enter to add).
              </p>
            </div>

            <div className="md:col-span-2">
              <label className="text-sm font-medium">
                Tags <span className="text-xs text-muted-foreground ml-1">(optional)</span>
              </label>
              <div className="mt-1">
                <FormTokenInput
                  values={tags}
                  setValues={setTags}
                  placeholder="ocean, ne30, q1-2024…"
                />
              </div>
            </div>
          </div>
        </FormSection>
        <FormSection
          title="Model Setup"
          isOpen={open === 'modelSetup'}
          onToggle={() => toggle('modelSetup')}
          requiredCount={REQUIRED_FIELDS.model}
          satisfiedCount={modelSat}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="text-sm font-medium">
                Machine ID <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="machineId"
                value={form.machineId}
                onChange={handleChange}
                placeholder="e.g., cori, perlmutter, lassen"
              />
            </div>
            <div>
              <label className="text-sm font-medium">
                Compiler <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="compiler"
                value={form.compiler ?? ''}
                onChange={handleChange}
                placeholder="e.g., intel/2021.4"
              />
            </div>
            <div>
              <label className="text-sm font-medium">
                Grid Name <span className="text-xs text-muted-foreground ml-1">(optional)</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="gridName"
                value={form.gridName ?? ''}
                onChange={handleChange}
                placeholder="e.g., ne30_oECv3_ICG"
              />
            </div>
            <div>
              <label className="text-sm font-medium">
                Compset <span className="text-xs text-muted-foreground ml-1">(optional)</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="compset"
                value={form.compset ?? ''}
                onChange={handleChange}
                placeholder="e.g., A_WCYCL1850S_CMIP6"
              />
            </div>
          </div>
        </FormSection>
        <FormSection
          title="Version Control"
          isOpen={open === 'versionControl'}
          onToggle={() => toggle('versionControl')}
          requiredCount={REQUIRED_FIELDS.version}
          satisfiedCount={versionSat}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="text-sm font-medium">
                Branch <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="branch"
                value={form.gitBranch ?? ''}
                onChange={handleChange}
                placeholder="e.g., e3sm-v3"
              />
            </div>
            <div>
              <label className="text-sm font-medium">
                Git Hash <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="gitCommitHash"
                value={form.gitCommitHash ?? ''}
                onChange={handleChange}
                placeholder="e.g., a1b2c3d"
              />
            </div>
            <div>
              <label className="text-sm font-medium">Branch Time</label>
              <input
                type="datetime-local"
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="branchTime"
                value={(form.branchTime as string) ?? ''}
                onChange={handleChange}
              />
            </div>
            <div className="md:col-span-2">
              <label className="text-sm font-medium">
                External Repo URL{' '}
                <span className="text-xs text-muted-foreground ml-1">(optional)</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="gitRepositoryUrl"
                value={form.gitRepoUrl ?? ''}
                onChange={handleChange}
                placeholder="https://github.com/org/repo"
              />
            </div>
          </div>
        </FormSection>
        <FormSection
          title="Data Paths & Scripts"
          isOpen={open === 'paths'}
          onToggle={() => toggle('paths')}
          requiredCount={REQUIRED_FIELDS.paths}
          satisfiedCount={pathsSat}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="text-sm font-medium">
                Output Path <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="outputPath"
                value={form.outputPath ?? ''}
                onChange={handleChange}
                placeholder="/global/archive/sim-output/..."
              />
            </div>
            <div>
              <label className="text-sm font-medium">
                Archive Paths (comma-separated) <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="archivePaths"
                value={form.archivePaths?.join?.(', ') ?? ''}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    archivePaths: e.target.value
                      .split(',')
                      .map((s) => s.trim())
                      .filter(Boolean),
                  }))
                }
                placeholder="/global/archive/sim-state/..., /other/path/..."
              />
            </div>
            <div>
              <label className="text-sm font-medium">
                Run Script Paths (comma-separated) <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="runScriptPaths"
                value={form.runScriptPaths?.join?.(', ') ?? ''}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    runScriptPaths: e.target.value
                      .split(',')
                      .map((s) => s.trim())
                      .filter(Boolean),
                  }))
                }
                placeholder="/home/user/run.sh, /home/user/run2.sh"
              />
            </div>
            <div>
              <label className="text-sm font-medium">
                Postprocessing Script Path
                <span className="text-xs text-muted-foreground ml-1">(optional)</span>
              </label>
              <input
                className="mt-1 w-full h-10 rounded-md border px-3"
                name="postprocessingScriptPath"
                value={form.postprocessingScriptPath?.join?.(', ') ?? ''}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    postprocessingScriptPath: e.target.value
                      .split(',')
                      .map((s) => s.trim())
                      .filter(Boolean),
                  }))
                }
                placeholder="/home/user/post.sh"
              />
            </div>
            <div className="md:col-span-2">
              <label className="text-sm font-medium">
                Batch Log Paths
                <span className="text-xs text-muted-foreground ml-1">(optional, one per line)</span>
              </label>
              <textarea
                className="mt-1 w-full rounded-md border px-3 py-2"
                name="batchLogPaths"
                value={form.batchLogPaths?.join('\n') ?? ''}
                onChange={handleBatchLogPathsChange}
                rows={2}
                placeholder="/autolog/sim/run-19345.log"
              />
            </div>
          </div>
        </FormSection>
        <FormSection
          title="Documentation & Notes"
          isOpen={open === 'docs'}
          onToggle={() => toggle('docs')}
        >
          <div className="space-y-6">
            <div>
              <div className="font-medium mb-2">
                Diagnostic Links <span className="text-xs text-muted-foreground">(optional)</span>
              </div>
              {diagLinks.map((lnk, i) => (
                <div key={i} className="flex gap-2 mb-2">
                  <input
                    className="w-1/3 h-10 rounded-md border px-3"
                    placeholder="Label"
                    value={lnk.label}
                    onChange={(e) => setDiag(i, 'label', e.target.value)}
                  />
                  <input
                    className="w-2/3 h-10 rounded-md border px-3"
                    placeholder="URL"
                    value={lnk.url}
                    onChange={(e) => setDiag(i, 'url', e.target.value)}
                  />
                </div>
              ))}
              <button type="button" className="text-sm text-blue-600 underline" onClick={addDiag}>
                + Add Link
              </button>
            </div>

            <div>
              <div className="font-medium mb-2">
                PACE Links <span className="text-xs text-muted-foreground">(optional)</span>
              </div>
              {paceLinks.map((lnk, i) => (
                <div key={i} className="flex gap-2 mb-2">
                  <input
                    className="w-1/3 h-10 rounded-md border px-3"
                    placeholder="Label"
                    value={lnk.label}
                    onChange={(e) => setPace(i, 'label', e.target.value)}
                  />
                  <input
                    className="w-2/3 h-10 rounded-md border px-3"
                    placeholder="URL"
                    value={lnk.url}
                    onChange={(e) => setPace(i, 'url', e.target.value)}
                  />
                </div>
              ))}
              <button type="button" className="text-sm text-blue-600 underline" onClick={addPace}>
                + Add Link
              </button>
            </div>

            <div>
              <label className="text-sm font-medium">
                Notes (Markdown){' '}
                <span className="text-xs text-muted-foreground ml-1">(optional)</span>
              </label>
              <textarea
                className="mt-1 w-full rounded-md border px-3 py-2"
                name="notesMarkdown"
                value={form.notesMarkdown ?? ''}
                onChange={handleChange}
                rows={4}
              />
            </div>

            <div>
              <label className="text-sm font-medium">
                Known Issues <span className="text-xs text-muted-foreground ml-1">(optional)</span>
              </label>
              <textarea
                className="mt-1 w-full rounded-md border px-3 py-2"
                name="knownIssues"
                value={form.knownIssues ?? ''}
                onChange={handleChange}
                rows={2}
              />
            </div>

            <div>
              <label className="text-sm font-medium">
                Annotations (JSON/text){' '}
                <span className="text-xs text-muted-foreground ml-1">(optional)</span>
              </label>
              <textarea
                className="mt-1 w-full rounded-md border px-3 py-2"
                name="annotations"
                value={form.annotations ?? ''}
                onChange={handleChange}
                rows={2}
              />
            </div>
          </div>
        </FormSection>
        <FormSection
          title="Review & Submit"
          isOpen={open === 'review'}
          onToggle={() => toggle('review')}
        >
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div className="space-y-1">
                <div>
                  <strong>Name:</strong> {form.name || '—'}
                </div>
                <div>
                  <strong>Status:</strong> {form.status || '—'}
                </div>
                <div>
                  <strong>Campaign:</strong> {form.campaignId || '—'}
                </div>
                <div>
                  <strong>Experiment Type:</strong> {form.experimentTypeId || '—'}
                </div>
                <div>
                  <strong>Variables:</strong> {variables.join(', ') || '—'}
                </div>
                <div>
                  <strong>Tags:</strong> {tags.join(', ') || '—'}
                </div>
              </div>
              <div className="space-y-1">
                <div>
                  <strong>Machine ID:</strong> {form.machineId || '—'}
                </div>
                <div>
                  <strong>Compiler:</strong> {form.compiler || '—'}
                </div>
                <div>
                  <strong>Grid:</strong> {form.gridName || '—'}
                </div>
                <div>
                  <strong>Branch:</strong> {form.gitBranch || '—'}
                </div>
                <div>
                  <strong>Git Hash:</strong> {form.gitCommitHash || '—'}
                </div>
                <div>
                  <strong>External Repo:</strong> {form.gitRepoUrl || '—'}
                </div>
              </div>
            </div>

            <div className="text-sm">
              <strong>Output Path:</strong> {form.outputPath || '—'}
              <br />
              <strong>Archive Paths:</strong> {(form.archivePaths || []).join(', ') || '—'}
              <br />
              <strong>Run Scripts:</strong> {(form.runScriptPaths || []).join(', ') || '—'}
            </div>

            <div className="text-sm">
              <strong>Diagnostic Links:</strong>
              <ul className="list-disc ml-6">
                {diagLinks.map((l, i) => (
                  <li key={i}>
                    {l.label ? `${l.label}: ` : ''}
                    <a href={l.url} className="text-blue-600 underline">
                      {l.url}
                    </a>
                  </li>
                ))}
                {diagLinks.length === 0 ? (
                  <li className="list-none text-muted-foreground">—</li>
                ) : null}
              </ul>
            </div>
          </div>

          <div className="mt-4 flex gap-2">
            <button
              type="button"
              className="border px-5 py-2 rounded-md"
              onClick={() => {
                setForm(initialState);
                setVariables([]);
                setTags([]);
                setDiagLinks([]);
                setPaceLinks([]);
              }}
            >
              Reset Form
            </button>
            <button
              type="button"
              className="bg-gray-900 text-white px-5 py-2 rounded-md disabled:opacity-50"
              disabled={!allValid}
              onClick={() => {
                // In your app, submit formWithVars + tags to backend
                alert('Submitted!');
              }}
            >
              Submit Simulation
            </button>
          </div>
        </FormSection>

        <StickyActionsBar
          disabled={!allValid}
          onSaveDraft={() => console.log('Save draft', formWithVars, { tags })}
          onNext={() => {
            if (!allValid) return window.scrollTo({ top: 0, behavior: 'smooth' });
            setOpen('review');
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
          }}
        />
      </div>
    </div>
  );
};

export default Upload;
