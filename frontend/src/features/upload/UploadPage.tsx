import axios from 'axios';
import { AlertTriangle, CheckCircle } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { createSimulation } from '@/features/simulations/api/api';
import { ConfirmResetDialog } from '@/features/upload/components/ConfirmResetDialog';
import { FormSection } from '@/features/upload/components/FormSection';
import { LinkField } from '@/features/upload/components/LinkField';
import { ReviewFieldList } from '@/features/upload/components/Review/ReviewFieldList';
import { ReviewLinkList } from '@/features/upload/components/Review/ReviewLinkList';
import { ReviewSection } from '@/features/upload/components/Review/ReviewSection';
import type { RenderableField } from '@/features/upload/types/field';
import { toast } from '@/hooks/use-toast';
import { Machine, SimulationCreate, SimulationCreateForm } from '@/types';
import { ARTIFACT_KIND_MAP, ArtifactIn } from '@/types/artifact';
import { ExternalLinkIn } from '@/types/link';

// -------------------- Types & Interfaces --------------------
interface UploadPageProps {
  machines: Machine[];
}

type OpenKey =
  | 'configuration'
  | 'modelSetup'
  | 'versionControl'
  | 'timeline'
  | 'paths'
  | 'docs'
  | null;

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
export const UploadPage = ({ machines }: UploadPageProps) => {
  const navigate = useNavigate();

  const [form, setForm] = useState<SimulationCreateForm>(initialState);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [diagLinks, setDiagLinks] = useState<{ label: string; url: string }[]>([]);
  const [paceLinks, setPaceLinks] = useState<{ label: string; url: string }[]>([]);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [openSection, setOpenSection] = useState<OpenKey>('configuration');
  const [reviewOpen, setReviewOpen] = useState(false);

  // -------------------- Derived Data --------------------
  // --- Configuration fields (matches initialState order)
  const configFields = useMemo(
    (): RenderableField[] => [
      {
        name: 'name',
        label: 'Simulation Name',
        type: 'text',
        required: true,
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
        required: true,
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
    (): RenderableField[] => [
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
        renderValue: (value: string) => {
          const machine = machines.find((m) => m.id === value);

          return machine ? machine.name : value;
        },
      },
    ],
    [machines],
  );

  // --- Version Control fields (matches initialState order)
  const versionFields = useMemo(
    (): RenderableField[] => [
      {
        label: 'Repository URL',
        name: 'gitRepositoryUrl',
        required: false,
        type: 'url',
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
    (): RenderableField[] => [
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
    (): RenderableField[] => [
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
    (): RenderableField[] => [
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
    (): RenderableField[] => [
      {
        label: 'Output Path',
        name: 'outputPath',
        required: true,
        type: 'text',
        placeholder: '/global/archive/sim-output/...',
      },
      {
        label: 'Archive Paths',
        name: 'archivePaths',
        required: false,
        type: 'text',
        placeholder: '/global/archive/sim-state/..., /other/path/...',
      },
      {
        label: 'Run Script Paths',
        name: 'runScriptPaths',
        required: false,
        type: 'text',
        placeholder: '/home/user/run.sh, /home/user/run2.sh',
      },
      {
        label: 'Postprocessing Script Paths',
        name: 'postprocessingScriptPaths',
        required: false,
        type: 'text',
        placeholder: '/home/user/post.sh',
      },
    ],
    [],
  );

  // Calculate required fields based on field definitions.
  const requiredFields = useMemo(
    () => ({
      configuration: configFields.filter((field) => field.required).length,
      modelSetup: modelFields.filter((field) => field.required).length,
      timeline: timelineFields.filter((field) => field.required).length,
      versionControl: versionFields.filter((field) => field.required).length,
      paths: pathFields.filter((field) => field.required).length,
      docs: docFields.filter((field) => field.required).length,
      meta: metaFields.filter((field) => field.required).length,
      review: 0,
    }),
    [configFields, modelFields, timelineFields, versionFields, pathFields, docFields, metaFields],
  );

  const validateField = (name: string, value: unknown) => {
    let error: string | null = null;

    // 1. Required fields
    const ALL_FIELDS = [
      ...configFields,
      ...modelFields,
      ...timelineFields,
      ...versionFields,
      ...pathFields,
      ...docFields,
      ...metaFields,
    ];

    const fieldDef = ALL_FIELDS.find((f) => f.name === name);

    if (fieldDef?.required) {
      if (
        value === undefined ||
        value === null ||
        value === '' ||
        (Array.isArray(value) && value.length === 0)
      ) {
        error = `${fieldDef.label} is required`;
      }
    }

    // 2. Special-case validation by name.
    // NOTE: These fields are empty on the initial form state but require user input.
    if (!error) {
      if (name === 'machineId') {
        if (value === undefined || value === null || value === '') {
          error = 'Machine ID is required';
        } else {
          const isUuid = /^[0-9a-fA-F-]{36}$/.test(String(value));
          if (!isUuid) error = 'Machine ID must be a valid UUID';
        }
      }

      if (name === 'simulationStartDate' && value !== undefined && value !== null && value !== '') {
        const date = Date.parse(String(value));

        if (isNaN(date)) error = 'Invalid start date';
      }
    }

    setErrors((prev) => ({ ...prev, [name]: error ?? '' }));
  };

  // -------------------- Derived Data for Required Counts --------------------
  // Count non-empty values
  const isFilled = (v: unknown) => v !== null && v !== undefined && v !== '';

  // Generic satisfied count calculator for required fields
  const getSatisfiedCount = useCallback(
    (fields: RenderableField[]) =>
      fields.reduce((count, f) => {
        if (!f.required) return count;

        const v = form[f.name as keyof SimulationCreateForm];

        return isFilled(v) ? count + 1 : count;
      }, 0),
    [form],
  );

  // Memoized section counts
  const fieldsSatisfied = useMemo(
    () => ({
      configuration: getSatisfiedCount(configFields),
      modelSetup: getSatisfiedCount(modelFields),
      timeline: getSatisfiedCount(timelineFields),
      paths: getSatisfiedCount(pathFields),
    }),
    [getSatisfiedCount, configFields, modelFields, timelineFields, pathFields],
  );

  const allFieldsValid = useMemo(
    () =>
      fieldsSatisfied.configuration >= requiredFields.configuration &&
      fieldsSatisfied.modelSetup >= requiredFields.modelSetup &&
      fieldsSatisfied.timeline >= requiredFields.timeline &&
      fieldsSatisfied.paths >= requiredFields.paths,
    [requiredFields, fieldsSatisfied],
  );

  // -------------------- Builders --------------------
  const buildArtifacts = (form: SimulationCreateForm): ArtifactIn[] => {
    const artifacts: ArtifactIn[] = [];

    if (form.outputPath) {
      artifacts.push({
        kind: ARTIFACT_KIND_MAP.outputPath,
        uri: form.outputPath,
      });
    }

    form.archivePaths?.forEach((path) => {
      artifacts.push({
        kind: ARTIFACT_KIND_MAP.archivePaths,
        uri: path,
      });
    });

    form.runScriptPaths?.forEach((path) => {
      artifacts.push({
        kind: ARTIFACT_KIND_MAP.runScriptPaths,
        uri: path,
      });
    });

    form.postprocessingScriptPaths?.forEach((path) => {
      artifacts.push({
        kind: ARTIFACT_KIND_MAP.postprocessingScriptPaths,
        uri: path,
      });
    });

    return artifacts;
  };

  const buildLinks = (
    diagLinks: { label: string; url: string }[],
    paceLinks: { label: string; url: string }[],
  ): ExternalLinkIn[] => {
    const links: ExternalLinkIn[] = [];
    diagLinks.forEach((l) => {
      if (l.label?.trim() && l.url?.trim()) {
        links.push({ kind: 'diagnostic', url: l.url, label: l.label || null });
      }
    });
    paceLinks.forEach((l) => {
      if (l.label?.trim() && l.url?.trim()) {
        links.push({ kind: 'performance', url: l.url, label: l.label || null });
      }
    });

    return links;
  };

  // -------------------- Handlers --------------------

  const ARRAY_FIELDS = new Set(['archivePaths', 'runScriptPaths', 'postprocessingScriptPaths']);
  const handleBlur = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;

    if (!ARRAY_FIELDS.has(name)) return;

    setForm((prev) => ({
      ...prev,
      [name]: value
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
    }));
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target;

    let normalizedValue: unknown = value;

    // Dates → empty string becomes null
    if (name === 'simulationEndDate' || name === 'runStartDate' || name === 'runEndDate') {
      normalizedValue = value || null;
    }

    // JSON field
    else if (name === 'extra') {
      try {
        normalizedValue = value ? JSON.parse(value) : {};

        setErrors((prev) => ({ ...prev, [name]: '' }));
      } catch {
        normalizedValue = {};

        setErrors((prev) => ({
          ...prev,
          [name]: 'Invalid JSON format',
        }));
      }
    }

    setForm((prev) => ({
      ...prev,
      [name]: normalizedValue,
    }));

    if (name !== 'extra') {
      validateField(name, normalizedValue);
    }
  };

  const toggle = (k: OpenKey) => setOpenSection((prev) => (prev === k ? null : k));

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
    setIsSubmitting(true);

    const artifacts = buildArtifacts(form);
    const links = buildLinks(diagLinks, paceLinks);
    const normalizedForm = normalizeOptionalFields(form);

    const payload: SimulationCreate = {
      ...normalizedForm,
      artifacts,
      links,
    };

    try {
      const simulation = await createSimulation(payload);

      toast({
        title: 'Simulation Created',
        description: (
          <div className="flex items-center gap-2">
            <CheckCircle className="h-5 w-5 text-green-600" />
            Your simulation has been successfully created.
          </div>
        ),
      });

      navigate(`/simulations/${simulation.id}`, {
        state: { justCreated: true },
      });
    } catch (error) {
      console.error('Failed to create simulation:', error);

      if (axios.isAxiosError(error)) {
        const status = error.response?.status;
        const data = error.response?.data;

        // TODO: Handle errors more gracefully by having the form detect them first.
        if (status === 422 && Array.isArray(data?.detail)) {
          toast({
            title: 'Invalid form data',
            description: 'Some fields are missing or invalid. Please review the form and try again',
            variant: 'destructive',
          });

          return;
        }

        if (status === 400) {
          toast({
            title: 'Cannot create simulation',
            description:
              typeof data?.detail === 'string'
                ? data.detail
                : 'The simulation request is valid but cannot be accepted.',
            variant: 'destructive',
          });

          return;
        }

        if (status === 409) {
          toast({
            title: 'Simulation already exists',
            description:
              typeof data?.detail === 'string'
                ? data.detail
                : 'A simulation with the same name or case already exists.',
            variant: 'destructive',
          });

          return;
        }
      }

      toast({
        title: 'Upload failed',
        description: 'We could not create the simulation. Please review the form and try again.',
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const normalizeOptionalFields = (form: SimulationCreateForm): SimulationCreateForm => {
    return {
      ...form,

      // nullable strings / IDs
      description: form.description?.trim() || null,
      compiler: form.compiler?.trim() || null,
      parentSimulationId: form.parentSimulationId || null,
      campaignId: form.campaignId || null,
      experimentTypeId: form.experimentTypeId || null,
      gitRepositoryUrl: form.gitRepositoryUrl?.trim() || null,
      gitBranch: form.gitBranch?.trim() || null,
      gitTag: form.gitTag?.trim() || null,
      gitCommitHash: form.gitCommitHash?.trim() || null,
      simulationEndDate: form.simulationEndDate || null,
      runStartDate: form.runStartDate || null,
      runEndDate: form.runEndDate || null,
      keyFeatures: form.keyFeatures?.trim() || null,
      knownIssues: form.knownIssues?.trim() || null,
      notesMarkdown: form.notesMarkdown?.trim() || null,

      // arrays
      archivePaths: form.archivePaths ?? [],
      runScriptPaths: form.runScriptPaths ?? [],
      postprocessingScriptPaths: form.postprocessingScriptPaths ?? [],

      // object
      extra: form.extra ?? {},
    };
  };

  // -------------------- Development Checks --------------------
  useEffect(() => {
    if (!import.meta.env.DEV) return;

    const ignore = new Set(['artifacts', 'links']);

    const uiFieldSet = new Set(
      [
        ...configFields,
        ...modelFields,
        ...versionFields,
        ...timelineFields,
        ...docFields,
        ...metaFields,
        ...pathFields,
      ].map((f) => f.name),
    );

    const stateKeys = Object.keys(initialState).filter(
      (k) => !ignore.has(k),
    ) as (keyof SimulationCreateForm)[];

    const missingInUI = stateKeys.filter((k) => !uiFieldSet.has(k));
    const missingInState = [...uiFieldSet].filter((k) => !stateKeys.includes(k));

    if (missingInUI.length || missingInState.length) {
      console.group('⚠️ Field mismatch detected');

      if (missingInUI.length) console.warn('State fields missing UI:', missingInUI);
      if (missingInState.length) console.warn('UI fields missing state:', missingInState);

      console.groupEnd();
    }
  }, [configFields, modelFields, versionFields, timelineFields, docFields, metaFields, pathFields]);

  // -------------------- Render --------------------
  const renderErrorList = (
    errors: Record<string, string>,
    fields: { name: string; label: string }[],
  ): React.ReactNode => {
    return Object.entries(errors)
      .filter(([, msg]) => !!msg)
      .map(([field, msg]) => {
        const fieldDef = fields.find((f) => f.name === field);
        const label = fieldDef ? fieldDef.label : field;

        return (
          <li key={field}>
            <span className="font-semibold">{label}:</span> {String(msg)}
          </li>
        );
      });
  };

  const completed =
    fieldsSatisfied.configuration +
    fieldsSatisfied.modelSetup +
    fieldsSatisfied.timeline +
    fieldsSatisfied.paths;

  const required =
    requiredFields.configuration +
    requiredFields.modelSetup +
    requiredFields.timeline +
    requiredFields.paths;

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
          isOpen={openSection === 'configuration'}
          onToggle={() => toggle('configuration')}
          requiredCount={requiredFields.configuration}
          satisfiedCount={fieldsSatisfied.configuration}
        >
          {configFields.map((field) => (
            <div key={field.name}>
              <label className="text-sm font-medium">
                {field.label}
                {field.required && <span className="text-red-500">*</span>}
              </label>

              {field.type === 'textarea' ? (
                <textarea
                  className={`mt-1 w-full rounded-md border px-3 py-2 ${
                    errors[field.name] ? 'border-red-500' : 'border-gray-300'
                  }`}
                  name={field.name}
                  value={(form[field.name] as string | null) ?? ''}
                  onChange={handleChange}
                  placeholder={field.placeholder}
                  rows={field.name === 'description' ? 2 : 4}
                />
              ) : (
                <input
                  className={`mt-1 w-full rounded-md border px-3 h-10 ${
                    errors[field.name] ? 'border-red-500' : 'border-gray-300'
                  }`}
                  name={field.name}
                  value={(form[field.name] as string | null) ?? ''}
                  onChange={handleChange}
                  placeholder={field.placeholder}
                />
              )}

              {/* 🔥 Inline validation message */}
              {errors[field.name] && (
                <p className="text-red-500 text-xs mt-1">{errors[field.name]}</p>
              )}
            </div>
          ))}
        </FormSection>

        <FormSection
          title="Timeline"
          isOpen={openSection === 'timeline'}
          onToggle={() => toggle('timeline')}
          requiredCount={requiredFields.timeline}
          satisfiedCount={fieldsSatisfied.timeline}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {timelineFields.map((field) => (
              <div key={field.name}>
                <label className="text-sm font-medium">
                  {field.label}
                  {field.required && <span className="text-red-500">*</span>}
                </label>

                <input
                  className={`mt-1 w-full h-10 rounded-md border px-3 ${
                    errors[field.name] ? 'border-red-500' : 'border-gray-300'
                  }`}
                  type={field.type}
                  name={field.name}
                  value={(form[field.name] as string | null) ?? ''}
                  onChange={handleChange}
                  placeholder={field.placeholder}
                />

                {errors[field.name] && (
                  <p className="text-red-500 text-xs mt-1">{errors[field.name]}</p>
                )}
              </div>
            ))}
          </div>
        </FormSection>
        <FormSection
          title="Model Setup"
          isOpen={openSection === 'modelSetup'}
          onToggle={() => toggle('modelSetup')}
          requiredCount={requiredFields.modelSetup}
          satisfiedCount={fieldsSatisfied.modelSetup}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {modelFields.map((field) => (
              <div key={field.name}>
                <label className="text-sm font-medium">
                  {field.label}
                  {field.required && <span className="text-red-500">*</span>}
                </label>

                {field.type === 'select' ? (
                  <select
                    className={`mt-1 w-full h-10 rounded-md border px-3 ${
                      errors[field.name] ? 'border-red-500' : 'border-gray-300'
                    }`}
                    name={field.name}
                    value={(form[field.name] as string | null) ?? ''}
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
                    className={`mt-1 w-full h-10 rounded-md border px-3 ${
                      errors[field.name] ? 'border-red-500' : 'border-gray-300'
                    }`}
                    name={field.name}
                    value={(form[field.name] as string | null) ?? ''}
                    onChange={handleChange}
                    placeholder={field.placeholder}
                  />
                )}

                {errors[field.name] && (
                  <p className="text-red-500 text-xs mt-1">{errors[field.name]}</p>
                )}
              </div>
            ))}
          </div>
        </FormSection>
        <FormSection
          title="Version Control"
          isOpen={openSection === 'versionControl'}
          onToggle={() => toggle('versionControl')}
          requiredCount={requiredFields.versionControl}
          satisfiedCount={getSatisfiedCount(versionFields)}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {versionFields.map((field) => (
              <div key={field.name}>
                <label className="text-sm font-medium">{field.label}</label>

                <input
                  className={`mt-1 w-full h-10 rounded-md border px-3 ${
                    errors[field.name] ? 'border-red-500' : 'border-gray-300'
                  }`}
                  name={field.name}
                  value={(form[field.name] as string | null) ?? ''}
                  onChange={handleChange}
                  placeholder={field.placeholder}
                />

                {errors[field.name] && (
                  <p className="text-red-500 text-xs mt-1">{errors[field.name]}</p>
                )}
              </div>
            ))}
          </div>
        </FormSection>

        <FormSection
          title="Data Paths & Scripts"
          isOpen={openSection === 'paths'}
          onToggle={() => toggle('paths')}
          requiredCount={requiredFields.paths}
          satisfiedCount={fieldsSatisfied.paths}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {pathFields.map((field) => {
              const rawValue = form[field.name] as string | string[] | null | undefined;

              return (
                <div key={field.name}>
                  <label className="text-sm font-medium">
                    {field.label}
                    {field.required && <span className="text-red-500">*</span>}
                  </label>

                  <input
                    className={`mt-1 w-full h-10 rounded-md border px-3 ${
                      errors[field.name] ? 'border-red-500' : 'border-gray-300'
                    }`}
                    name={field.name}
                    value={Array.isArray(rawValue) ? rawValue.join(', ') : (rawValue ?? '')}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    placeholder={field.placeholder}
                  />

                  {field.name === 'outputPath' ? (
                    <p className="text-xs text-gray-500 mt-1">
                      Enter a single path (for example: <code>/path</code>)
                    </p>
                  ) : (
                    <p className="text-xs text-gray-500 mt-1">
                      Enter a comma-separated list of paths (for example: <code>/path1,/path2</code>{' '}
                      or <code>/path1, /path2</code>).
                    </p>
                  )}

                  {errors[field.name] && (
                    <p className="text-red-500 text-xs mt-1">{errors[field.name]}</p>
                  )}
                </div>
              );
            })}

            <LinkField
              title="Diagnostic Links"
              links={diagLinks}
              onAdd={addDiag}
              onChange={setDiag}
            />

            <LinkField title="PACE Links" links={paceLinks} onAdd={addPace} onChange={setPace} />
          </div>
        </FormSection>

        {/* Documentation & Notes Section */}
        <FormSection
          title="Documentation & Notes"
          isOpen={openSection === 'docs'}
          onToggle={() => toggle('docs')}
        >
          <div className="space-y-6">
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
                  value={(form[field.name] as string | null) ?? ''}
                  onChange={handleChange}
                  placeholder={field.placeholder}
                  rows={field.name === 'notesMarkdown' ? 4 : 2}
                />
              </div>
            ))}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {metaFields.map((field) => {
                const rawValue = form[field.name] as string | null | undefined;

                return (
                  <div key={field.name}>
                    <label className="text-sm font-medium">{field.label}</label>

                    <textarea
                      className={`mt-1 w-full rounded-md border px-3 py-2 ${
                        errors[field.name] ? 'border-red-500' : 'border-gray-300'
                      }`}
                      name={field.name}
                      value={
                        field.name === 'extra'
                          ? JSON.stringify(form.extra ?? {}, null, 2)
                          : (rawValue ?? '')
                      }
                      onChange={handleChange}
                      placeholder={field.placeholder}
                      rows={4}
                    />

                    {errors[field.name] && (
                      <p className="text-red-500 text-xs mt-1">{errors[field.name]}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </FormSection>

        <FormSection
          title="Review & Submit"
          isOpen={reviewOpen}
          onToggle={() => setReviewOpen((v) => !v)}
        >
          <div
            className="mb-4 max-h-[60vh] md:max-h-[600px] overflow-y-auto pr-2"
            style={{ scrollbarGutter: 'stable' }}
            tabIndex={0}
          >
            <div className="sticky top-0 z-10 mb-3">
              <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-200 rounded">
                <svg
                  className="w-5 h-5 text-blue-500 flex-shrink-0"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  viewBox="0 0 24 24"
                >
                  <circle cx="12" cy="12" r="10" fill="white" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01" />
                </svg>

                <span className="text-sm text-slate-700">
                  <span className="font-medium">Review your entries below.</span> Required fields
                  are marked with <span className="text-red-500">*</span> and must be filled before
                  submitting.
                </span>

                <span
                  className={`ml-auto inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-semibold ${
                    allFieldsValid ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                  }`}
                >
                  {allFieldsValid ? (
                    <CheckCircle className="h-3.5 w-3.5" />
                  ) : (
                    <AlertTriangle className="h-3.5 w-3.5" />
                  )}
                  {completed} / {required} required
                </span>
              </div>
            </div>

            {Object.values(errors).some(Boolean) && (
              <div className="mt-2 text-red-600 text-sm">
                Please fix the errors above before submitting.
                <ul className="list-disc ml-6 mt-1">
                  {renderErrorList(errors, [
                    ...configFields,
                    ...modelFields,
                    ...versionFields,
                    ...timelineFields,
                    ...docFields,
                    ...metaFields,
                    ...pathFields,
                  ])}
                </ul>
              </div>
            )}
            <div className="space-y-4">
              <ReviewSection title="Configuration">
                <ReviewFieldList form={form} fields={configFields} />
              </ReviewSection>

              <ReviewSection title="Model Setup">
                <ReviewFieldList form={form} fields={modelFields} />
              </ReviewSection>

              <ReviewSection title="Version Control">
                <ReviewFieldList form={form} fields={versionFields} />
              </ReviewSection>

              <ReviewSection title="Timeline">
                <ReviewFieldList form={form} fields={timelineFields} />
              </ReviewSection>

              <ReviewSection title="Data Paths & Scripts">
                <ReviewFieldList form={form} fields={pathFields} />
              </ReviewSection>
              <ReviewSection title="Diagnostic Links">
                <ReviewLinkList links={diagLinks} />
              </ReviewSection>
              <ReviewSection title="PACE Links">
                <ReviewLinkList links={paceLinks} />
              </ReviewSection>
              <ReviewSection title="Documentation & Notes">
                <ReviewFieldList form={form} fields={[...docFields, ...metaFields]} />
              </ReviewSection>
            </div>
          </div>
        </FormSection>

        <div className="sticky bottom-0 inset-x-0 border-t bg-white/80 backdrop-blur supports-[backdrop-filter]:bg-white/60">
          <div className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Tip: You can collapse completed sections to stay focused.
            </p>
            <div className="flex gap-2">
              <div className="mt-4 flex gap-2">
                <ConfirmResetDialog
                  onConfirm={() => {
                    setForm(initialState);
                    setDiagLinks([]);
                    setPaceLinks([]);
                    setErrors({});
                  }}
                />

                <button
                  type="button"
                  className="bg-gray-900 text-white px-5 py-2 rounded-md disabled:opacity-50"
                  disabled={
                    Object.values(errors).filter((msg) => msg !== '').length > 0 ||
                    !allFieldsValid ||
                    isSubmitting
                  }
                  onClick={handleSubmit}
                >
                  Submit simulation
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
