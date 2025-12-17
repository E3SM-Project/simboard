import { useMemo, useState } from 'react';

import { createSimulation } from '@/api/simulation';
import FormSection from '@/pages/Upload/FormSection';
import StickyActionsBar from '@/pages/Upload/StickyActionsBar';
import { Machine, SimulationCreate, SimulationCreateForm } from '@/types';
import { ArtifactIn } from '@/types/artifact';
import { ExternalLinkIn } from '@/types/link';

// -------------------- Types & Interfaces --------------------
interface UploadProps {
  machines: Machine[];
}

type OpenKey =
  | 'configuration'
  | 'modelSetup'
  | 'versionControl'
  | 'timeline'
  | 'paths'
  | 'docs'
  | 'review'
  | null;

// -------------------- Pure Helpers --------------------
const countValidfields = (fields: (string | null | undefined)[]) =>
  fields.reduce((count, field) => (field ? count + 1 : count), 0);

// -------------------- Initial Form State --------------------
const initialState: SimulationCreateForm = {
  // --- Configuration ---
  name: '', // required
  caseName: '', // required
  description: null,
  compset: '', // required
  compsetAlias: '', // required
  gridName: '', // required
  gridResolution: '', // required
  initializationType: '',
  compiler: null,
  parentSimulationId: null,

  // --- Model Setup ---
  simulationType: '', // required
  status: 'created', // required
  campaignId: null,
  experimentTypeId: null,
  machineId: '', // required

  // --- Version Control ---
  gitRepositoryUrl: null,
  gitBranch: null,
  gitTag: null,
  gitCommitHash: null,

  // --- Timeline ---
  simulationStartDate: '', // required
  simulationEndDate: null,
  runStartDate: null,
  runEndDate: null,

  // --- Documentation ---
  keyFeatures: null,
  knownIssues: null,
  notesMarkdown: null,

  // --- Metadata ---
  extra: {},

  // --- Artifacts & Links ---
  artifacts: [],
  links: [],

  // --- UI-only fields ---
  outputPath: '',
  archivePaths: [],
  runScriptPaths: [],
  postprocessingScriptPaths: [],
};

// -------------------- Component --------------------
const Upload = ({ machines }: UploadProps) => {
  const [open, setOpen] = useState<OpenKey>('configuration');
  const [form, setForm] = useState<SimulationCreateForm>(initialState);

  const [variables, setVariables] = useState<string[]>([]);
  const [diagLinks, setDiagLinks] = useState<{ label: string; url: string }[]>([]);
  const [paceLinks, setPaceLinks] = useState<{ label: string; url: string }[]>([]);

  // -------------------- Derived Data --------------------
  const formWithVars = useMemo(() => ({ ...form, variables }), [form, variables]);
  // --- Configuration fields (matches initialState order)
  const configFields = useMemo(
    () => [
      {
        label: 'Simulation Name',
        name: 'name',
        required: true,
        type: 'text',
        placeholder: 'e.g., E3SM v3 LR Control 20190815',
      },
      {
        label: 'Simulation Case Name',
        name: 'caseName',
        required: true,
        type: 'text',
        placeholder: 'e.g., 20190815.ne30_oECv3_ICG.A_WCYCL1850S_CMIP6.piControl',
      },
      {
        label: 'Description',
        name: 'description',
        required: false,
        type: 'textarea',
        placeholder: 'Short description (optional)',
      },
      {
        label: 'Compset',
        name: 'compset',
        required: true,
        type: 'text',
        placeholder: 'e.g., A_WCYCL1850S_CMIP6',
      },
      {
        label: 'Compset Alias',
        name: 'compsetAlias',
        required: true,
        type: 'text',
        placeholder: 'e.g., WCYCL1850S',
      },
      {
        label: 'Grid Name',
        name: 'gridName',
        required: true,
        type: 'text',
        placeholder: 'e.g., ne30_oECv3_ICG',
      },
      {
        label: 'Grid Resolution',
        name: 'gridResolution',
        required: true,
        type: 'text',
        placeholder: 'e.g., 1deg',
      },
      {
        label: 'Initialization Type',
        name: 'initializationType',
        required: false,
        type: 'text',
        placeholder: 'e.g., hybrid, branch, startup',
      },
      {
        label: 'Compiler',
        name: 'compiler',
        required: false,
        type: 'text',
        placeholder: 'e.g., intel/2021.4',
      },
      {
        label: 'Parent Simulation ID',
        name: 'parentSimulationId',
        required: false,
        type: 'text',
        placeholder: 'Parent simulation ID (optional)',
      },
    ],
    [],
  );

  // --- Model Setup fields (matches initialState order)
  const modelFields = useMemo(
    () => [
      {
        label: 'Simulation Type',
        name: 'simulationType',
        required: true,
        type: 'select',
        options: [
          { value: 'production', label: 'Production' },
          { value: 'test', label: 'Test' },
          { value: 'spinup', label: 'Spinup' },
        ],
      },
      {
        label: 'Status',
        name: 'status',
        required: true,
        type: 'select',
        options: [
          { value: 'created', label: 'Created' },
          { value: 'queued', label: 'Queued' },
          { value: 'running', label: 'Running' },
          { value: 'failed', label: 'Failed' },
          { value: 'completed', label: 'Completed' },
        ],
      },
      {
        label: 'Campaign',
        name: 'campaignId',
        required: false,
        type: 'text',
        placeholder: 'e.g., v3.LR',
      },
      {
        label: 'Experiment Type',
        name: 'experimentTypeId',
        required: false,
        type: 'text',
        placeholder: 'e.g., piControl',
      },
      {
        label: 'Machine',
        name: 'machineId',
        required: true,
        type: 'select',
        options: machines.map((m) => ({ value: m.id, label: m.name })),
      },
    ],
    [machines],
  );

  // --- Version Control fields (matches initialState order)
  const versionFields = useMemo(
    () => [
      {
        label: 'Repository URL',
        name: 'gitRepositoryUrl',
        required: false,
        type: 'text',
        placeholder: 'https://github.com/org/repo',
      },
      {
        label: 'Branch',
        name: 'gitBranch',
        required: false,
        type: 'text',
        placeholder: 'e.g., e3sm-v3',
      },
      { label: 'Tag', name: 'gitTag', required: false, type: 'text', placeholder: 'e.g., v1.0.0' },
      {
        label: 'Commit Hash',
        name: 'gitCommitHash',
        required: false,
        type: 'text',
        placeholder: 'e.g., a1b2c3d',
      },
    ],
    [],
  );

  // --- Timeline fields (matches initialState order)
  const timelineFields = useMemo(
    () => [
      {
        label: 'Simulation Start Date',
        name: 'simulationStartDate',
        required: true,
        type: 'date',
        placeholder: '',
      },
      {
        label: 'Simulation End Date',
        name: 'simulationEndDate',
        required: false,
        type: 'date',
        placeholder: '',
      },
      {
        label: 'Run Start Date',
        name: 'runStartDate',
        required: false,
        type: 'date',
        placeholder: '',
      },
      { label: 'Run End Date', name: 'runEndDate', required: false, type: 'date', placeholder: '' },
    ],
    [],
  );

  // --- Documentation fields (matches initialState order)
  const docFields = useMemo(
    () => [
      {
        label: 'Key Features',
        name: 'keyFeatures',
        required: false,
        type: 'textarea',
        placeholder: 'Key features (optional)',
      },
      {
        label: 'Known Issues',
        name: 'knownIssues',
        required: false,
        type: 'textarea',
        placeholder: 'Known issues (optional)',
      },
      {
        label: 'Notes (Markdown)',
        name: 'notesMarkdown',
        required: false,
        type: 'textarea',
        placeholder: 'Notes (optional)',
      },
    ],
    [],
  );

  // --- Metadata fields (matches initialState order)
  const metaFields = useMemo(
    () => [
      {
        label: 'Extra Metadata (JSON)',
        name: 'extra',
        required: false,
        type: 'textarea',
        placeholder: '{"foo": "bar"}',
      },
    ],
    [],
  );

  // --- Data Paths & Scripts fields (matches initialState order)
  const pathFields = useMemo(
    () => [
      {
        label: 'Output Path',
        name: 'outputPath',
        required: true,
        type: 'text',
        placeholder: '/global/archive/sim-output/...',
      },
      {
        label: 'Archive Paths (comma-separated)',
        name: 'archivePaths',
        required: false,
        type: 'text',
        placeholder: '/global/archive/sim-state/..., /other/path/...',
      },
      {
        label: 'Run Script Paths (comma-separated)',
        name: 'runScriptPaths',
        required: false,
        type: 'text',
        placeholder: '/home/user/run.sh, /home/user/run2.sh',
      },
      {
        label: 'Postprocessing Script Paths (comma-separated)',
        name: 'postprocessingScriptPaths',
        required: false,
        type: 'text',
        placeholder: '/home/user/post.sh',
      },
    ],
    [],
  );

  // Calculate required fields based on field definitions
  const required_fields = useMemo(
    () => ({
      configuration: configFields.filter((f) => f.required).length,
      modelSetup: modelFields.filter((f) => f.required).length,
      versionControl: versionFields.filter((f) => f.required).length,
      timeline: timelineFields.filter((f) => f.required).length,
      paths: pathFields.filter((f) => f.required).length,
      docs: docFields.filter((f) => f.required).length,
      meta: metaFields.filter((f) => f.required).length,
      review: 0,
    }),
    [configFields, modelFields, versionFields, timelineFields, pathFields, docFields, metaFields],
  );
  // -------------------- Derived Data for Required Counts --------------------
  const configSat = useMemo(() => {
    const fields = [
      form.name,
      form.caseName,
      form.compset,
      form.compsetAlias,
      form.gridName,
      form.gridResolution,
    ];
    return countValidfields(fields);
  }, [
    form.name,
    form.caseName,
    form.compset,
    form.compsetAlias,
    form.gridName,
    form.gridResolution,
  ]);

  const modelSat = useMemo(() => {
    const fields = [form.simulationType, form.status, form.machineId];

    return countValidfields(fields);
  }, [form.simulationType, form.status, form.machineId]);

  const pathsSat = useMemo(() => {
    const fields = [form.outputPath];

    return countValidfields(fields);
  }, [form.outputPath]);

  const timelineSat = useMemo(() => {
    const fields = [form.simulationStartDate];

    return countValidfields(fields);
  }, [form.simulationStartDate]);

  const allValid = useMemo(() => {
    return (
      configSat >= required_fields.configuration &&
      modelSat >= required_fields.modelSetup &&
      timelineSat >= required_fields.timeline &&
      pathsSat >= required_fields.paths
    );
  }, [required_fields, configSat, modelSat, timelineSat, pathsSat]);

  // -------------------- Builders --------------------
  const buildArtifacts = (form: SimulationCreateForm): ArtifactIn[] => {
    const artifacts: ArtifactIn[] = [];

    if (form.outputPath) artifacts.push({ kind: 'output', uri: form.outputPath });

    if (form.archivePaths?.length)
      form.archivePaths.forEach((p: string) => artifacts.push({ kind: 'archive', uri: p }));

    if (form.runScriptPaths?.length)
      form.runScriptPaths.forEach((p: string) => artifacts.push({ kind: 'runScript', uri: p }));

    if (form.postprocessingScriptPaths?.length)
      form.postprocessingScriptPaths.forEach((p: string) =>
        artifacts.push({ kind: 'postprocessingScript', uri: p }),
      );

    return artifacts;
  };

  const buildLinks = (
    diagLinks: { label: string; url: string }[],
    paceLinks: { label: string; url: string }[],
  ): ExternalLinkIn[] => {
    const links: ExternalLinkIn[] = [];
    diagLinks.forEach((l) =>
      links.push({ kind: 'diagnostic', url: l.url, label: l.label || null }),
    );
    paceLinks.forEach((l) =>
      links.push({ kind: 'performance', url: l.url, label: l.label || null }),
    );
    return links;
  };

  // -------------------- Handlers --------------------
  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target;
    // Handle array fields for comma-separated values
    if (
      name === 'archivePaths' ||
      name === 'runScriptPaths' ||
      name === 'postprocessingScriptPaths'
    ) {
      setForm((prev) => ({
        ...prev,
        [name]: value
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      }));
    } else if (name === 'simulationEndDate' || name === 'runStartDate' || name === 'runEndDate') {
      setForm((prev) => ({
        ...prev,
        [name]: value || null,
      }));
    } else if (name === 'extra') {
      // Parse JSON for extra metadata
      let parsed = {};
      try {
        parsed = value ? JSON.parse(value) : {};
      } catch {
        parsed = {};
      }
      setForm((prev) => ({
        ...prev,
        extra: parsed,
      }));
    } else {
      setForm((prev) => ({
        ...prev,
        [name]: value,
      }));
    }
  };

  const toggle = (k: OpenKey) => setOpen((prev) => (prev === k ? null : k));

  const addDiag = () => setDiagLinks([...diagLinks, { label: '', url: '' }]);
  const setDiag = (i: number, field: 'label' | 'url', v: string) => {
    const next = diagLinks.slice();
    next[i][field] = v;
    setDiagLinks(next);
  };

  const addPace = () => setPaceLinks([...paceLinks, { label: '', url: '' }]);
  const setPace = (i: number, field: 'label' | 'url', v: string) => {
    const next = paceLinks.slice();
    next[i][field] = v;
    setPaceLinks(next);
  };

  // -------------------- Handlers --------------------
  const handleSubmit = async () => {
    const artifacts = buildArtifacts(form);
    const links = buildLinks(diagLinks, paceLinks);

    const payload: SimulationCreate = {
      ...form,
      artifacts,
      links,
    };

    console.log('Submitting simulation:', payload);
    createSimulation(payload);
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

        {/* Configuration Section */}
        <FormSection
          title="Configuration"
          isOpen={open === 'configuration'}
          onToggle={() => toggle('configuration')}
          requiredCount={required_fields.configuration}
          satisfiedCount={configSat}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {configFields.map((field) => (
              <div key={field.name}>
                <label className="text-sm font-medium">
                  {field.label}
                  {field.required && <span className="text-red-500">*</span>}
                </label>
                {field.type === 'textarea' ? (
                  <textarea
                    className="mt-1 w-full rounded-md border px-3 py-2"
                    name={field.name}
                    value={form[field.name as keyof SimulationCreateForm] ?? ''}
                    onChange={handleChange}
                    placeholder={field.placeholder}
                    rows={field.name === 'description' ? 2 : 4}
                  />
                ) : (
                  <input
                    className="mt-1 w-full h-10 rounded-md border px-3"
                    name={field.name}
                    value={form[field.name as keyof SimulationCreateForm] ?? ''}
                    onChange={handleChange}
                    placeholder={field.placeholder}
                  />
                )}
              </div>
            ))}
          </div>
        </FormSection>

        {/* Timeline Section */}
        <FormSection
          title="Timeline"
          isOpen={open === 'timeline'}
          onToggle={() => toggle('timeline')}
          requiredCount={required_fields.timeline}
          satisfiedCount={timelineSat}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {timelineFields.map((field) => (
              <div key={field.name}>
                <label className="text-sm font-medium">
                  {field.label}
                  {field.required && <span className="text-red-500">*</span>}
                  {!field.required && (
                    <span className="text-xs text-muted-foreground ml-1">(optional)</span>
                  )}
                </label>
                <input
                  className="mt-1 w-full h-10 rounded-md border px-3"
                  type={field.type}
                  name={field.name}
                  value={form[field.name as keyof SimulationCreateForm] ?? ''}
                  onChange={handleChange}
                  placeholder={field.placeholder}
                />
              </div>
            ))}
          </div>
        </FormSection>

        {/* Model Setup Section */}
        <FormSection
          title="Model Setup"
          isOpen={open === 'modelSetup'}
          onToggle={() => toggle('modelSetup')}
          requiredCount={required_fields.modelSetup}
          satisfiedCount={modelSat}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {modelFields.map((field) => (
              <div key={field.name}>
                <label className="text-sm font-medium">
                  {field.label}
                  {field.required && <span className="text-red-500">*</span>}
                  {!field.required && (
                    <span className="text-xs text-muted-foreground ml-1">(optional)</span>
                  )}
                </label>
                {field.type === 'select' ? (
                  // $SELECT_PLACEHOLDER$
                  <select
                    className="mt-1 w-full h-10 rounded-md border px-3"
                    name={field.name}
                    value={form[field.name as keyof SimulationCreateForm] ?? ''}
                    onChange={handleChange}
                  >
                    <option value="">Select...</option>
                    {field.options?.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="mt-1 w-full h-10 rounded-md border px-3"
                    name={field.name}
                    value={form[field.name as keyof SimulationCreateForm] ?? ''}
                    onChange={handleChange}
                    placeholder={field.placeholder}
                  />
                )}
              </div>
            ))}
          </div>
        </FormSection>

        {/* Version Control Section */}
        <FormSection
          title="Version Control"
          isOpen={open === 'versionControl'}
          onToggle={() => toggle('versionControl')}
          requiredCount={required_fields.versionControl}
          satisfiedCount={0}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {versionFields.map((field) => (
              <div key={field.name}>
                <label className="text-sm font-medium">
                  {field.label}
                  {field.required && <span className="text-red-500">*</span>}
                  {!field.required && (
                    <span className="text-xs text-muted-foreground ml-1">(optional)</span>
                  )}
                </label>
                <input
                  className="mt-1 w-full h-10 rounded-md border px-3"
                  name={field.name}
                  value={form[field.name as keyof SimulationCreateForm] ?? ''}
                  onChange={handleChange}
                  placeholder={field.placeholder}
                />
              </div>
            ))}
          </div>
        </FormSection>

        {/* Data Paths & Scripts Section */}
        <FormSection
          title="Data Paths & Scripts"
          isOpen={open === 'paths'}
          onToggle={() => toggle('paths')}
          requiredCount={required_fields.paths}
          satisfiedCount={pathsSat}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {pathFields.map((field) => (
              <div key={field.name}>
                <label className="text-sm font-medium">
                  {field.label}
                  {field.required && <span className="text-red-500">*</span>}
                  {!field.required && (
                    <span className="text-xs text-muted-foreground ml-1">(optional)</span>
                  )}
                </label>
                <input
                  className="mt-1 w-full h-10 rounded-md border px-3"
                  name={field.name}
                  value={
                    Array.isArray(form[field.name as keyof SimulationCreateForm])
                      ? (form[field.name as keyof SimulationCreateForm] as string[]).join(', ')
                      : (form[field.name as keyof SimulationCreateForm] ?? '')
                  }
                  onChange={handleChange}
                  placeholder={field.placeholder}
                />
              </div>
            ))}
          </div>
        </FormSection>

        {/* Documentation & Notes Section */}
        <FormSection
          title="Documentation & Notes"
          isOpen={open === 'docs'}
          onToggle={() => toggle('docs')}
        >
          <div className="space-y-6">
            {/* Diagnostic Links */}
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

            {/* PACE Links */}
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

            {/* Documentation Fields */}
            {docFields.map((field) => (
              <div key={field.name}>
                <label className="text-sm font-medium">
                  {field.label}
                  {!field.required && (
                    <span className="text-xs text-muted-foreground ml-1">(optional)</span>
                  )}
                </label>
                <textarea
                  className="mt-1 w-full rounded-md border px-3 py-2"
                  name={field.name}
                  value={form[field.name as keyof SimulationCreateForm] ?? ''}
                  onChange={handleChange}
                  placeholder={field.placeholder}
                  rows={field.name === 'notesMarkdown' ? 4 : 2}
                />
              </div>
            ))}
          </div>
        </FormSection>

        <FormSection title="Metadata" isOpen={open === 'meta'} onToggle={() => toggle('meta')}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {metaFields.map((field) => (
              <div key={field.name}>
                <label className="text-sm font-medium">
                  {field.label}
                  {!field.required && (
                    <span className="text-xs text-muted-foreground ml-1">(optional)</span>
                  )}
                </label>
                <textarea
                  className="mt-1 w-full rounded-md border px-3 py-2"
                  name={field.name}
                  value={
                    field.name === 'extra'
                      ? JSON.stringify(form.extra ?? {}, null, 2)
                      : (form[field.name as keyof SimulationCreateForm] ?? '')
                  }
                  onChange={handleChange}
                  placeholder={field.placeholder}
                  rows={4}
                />
              </div>
            ))}
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
                  <strong>Case Name:</strong> {form.caseName || '—'}
                </div>
                <div>
                  <strong>Compset:</strong> {form.compset || '—'}
                </div>
                <div>
                  <strong>Compset Alias:</strong> {form.compsetAlias || '—'}
                </div>
                <div>
                  <strong>Grid Name:</strong> {form.gridName || '—'}
                </div>
                <div>
                  <strong>Grid Resolution:</strong> {form.gridResolution || '—'}
                </div>
                <div>
                  <strong>Initialization Type:</strong> {form.initializationType || '—'}
                </div>
                <div>
                  <strong>Parent Simulation ID:</strong> {form.parentSimulationId || '—'}
                </div>
              </div>
              <div className="space-y-1">
                <div>
                  <strong>Simulation Type:</strong> {form.simulationType || '—'}
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
                  <strong>Machine ID:</strong> {form.machineId || '—'}
                </div>
                <div>
                  <strong>Compiler:</strong> {form.compiler || '—'}
                </div>
              </div>
            </div>

            <div className="text-sm">
              <strong>Repository URL:</strong> {form.gitRepositoryUrl || '—'}
              <br />
              <strong>Branch:</strong> {form.gitBranch || '—'}
              <br />
              <strong>Tag:</strong> {form.gitTag || '—'}
              <br />
              <strong>Commit Hash:</strong> {form.gitCommitHash || '—'}
            </div>

            <div className="text-sm">
              <strong>Simulation Start Date:</strong> {form.simulationStartDate || '—'}
              <br />
              <strong>Simulation End Date:</strong> {form.simulationEndDate || '—'}
              <br />
              <strong>Run Start Date:</strong> {form.runStartDate || '—'}
              <br />
              <strong>Run End Date:</strong> {form.runEndDate || '—'}
            </div>

            <div className="text-sm">
              <strong>Output Path:</strong> {form.outputPath || '—'}
              <br />
              <strong>Archive Paths:</strong> {(form.archivePaths || []).join(', ') || '—'}
              <br />
              <strong>Run Scripts:</strong> {(form.runScriptPaths || []).join(', ') || '—'}
              <br />
              <strong>Postprocessing Scripts:</strong>{' '}
              {(form.postprocessingScriptPaths || []).join(', ') || '—'}
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
              onClick={handleSubmit}
            >
              Submit Simulation
            </button>
          </div>
        </FormSection>

        <StickyActionsBar
          disabled={!allValid}
          onSaveDraft={() => console.log('Save draft', formWithVars)}
          onNext={() => {
            if (!allValid) {
              window.scrollTo({ top: 0, behavior: 'smooth' });
              return;
            }
            setOpen('review');
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
          }}
        />
      </div>
    </div>
  );
};

export default Upload;
