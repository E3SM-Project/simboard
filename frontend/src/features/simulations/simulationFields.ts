import type { SimulationCreate, SimulationOut } from '@/types';

/**
 * Fields that exist both:
 * - at creation time (SimulationCreate)
 * - after creation (SimulationOut)
 *
 * NOTE:
 * - Form-only fields (outputPath, archivePaths, etc.) are intentionally excluded
 * - Relationships (artifacts, links) are excluded (handled separately)
 */
export type SimulationFieldName =
  | Exclude<keyof SimulationCreate, 'artifacts' | 'links'>
  | keyof Pick<SimulationOut, 'id' | 'createdAt' | 'updatedAt' | 'createdBy' | 'lastUpdatedBy'>;

export type SimulationFieldDef = {
  name: SimulationFieldName;
  label: string;

  /**
   * Who may edit this field on the details page.
   * If omitted, the field is immutable after creation.
   */
  editable?: {
    owner?: boolean;
    admin?: boolean;
  };

  /**
   * UI hint only (UploadPage and Details page render differently).
   */
  inputType?: 'text' | 'textarea' | 'select' | 'date' | 'url';

  /**
   * Select options, where applicable.
   */
  options?: { value: string; label: string }[];

  /**
   * Server-managed / audit fields.
   */
  system?: boolean;
};

/**
 * ------------------------------------------------------------------
 * SIMULATION FIELD REGISTRY (SOURCE OF TRUTH)
 * ------------------------------------------------------------------
 */
export const SIMULATION_FIELDS: Record<SimulationFieldName, SimulationFieldDef> = {
  // -------------------- Configuration --------------------
  name: {
    name: 'name',
    label: 'Simulation Name',
    editable: { owner: true },
    inputType: 'text',
  },

  caseName: {
    name: 'caseName',
    label: 'Case Name',
  },

  description: {
    name: 'description',
    label: 'Description',
    editable: { owner: true },
    inputType: 'textarea',
  },

  compset: {
    name: 'compset',
    label: 'Compset',
    editable: { owner: true },
  },

  compsetAlias: {
    name: 'compsetAlias',
    label: 'Compset Alias',
    editable: { owner: true },
  },

  gridName: {
    name: 'gridName',
    label: 'Grid Name',
    editable: { owner: true },
  },

  gridResolution: {
    name: 'gridResolution',
    label: 'Grid Resolution',
    editable: { owner: true },
  },

  parentSimulationId: {
    name: 'parentSimulationId',
    label: 'Parent Simulation ID',
    editable: { owner: true },
  },

  // -------------------- Model Setup / Context --------------------
  simulationType: {
    name: 'simulationType',
    label: 'Simulation Type',
    inputType: 'select',
    options: [
      { value: 'production', label: 'Production' },
      { value: 'test', label: 'Test' },
      { value: 'spinup', label: 'Spinup' },
    ],
  },

  status: {
    name: 'status',
    label: 'Status',
    editable: { owner: true }, // owner-as-admin policy
    inputType: 'select',
    options: [
      { value: 'created', label: 'Created' },
      { value: 'queued', label: 'Queued' },
      { value: 'running', label: 'Running' },
      { value: 'failed', label: 'Failed' },
      { value: 'completed', label: 'Completed' },
    ],
  },

  campaignId: {
    name: 'campaignId',
    label: 'Campaign ID',
    editable: { owner: true },
  },

  experimentTypeId: {
    name: 'experimentTypeId',
    label: 'Experiment Type ID',
    editable: { owner: true },
  },

  initializationType: {
    name: 'initializationType',
    label: 'Initialization Type',
    editable: { owner: true },
  },

  groupName: {
    name: 'groupName',
    label: 'Group Name',
    editable: { owner: true },
  },

  // -------------------- Timeline --------------------
  machineId: {
    name: 'machineId',
    label: 'Machine',
    inputType: 'select',
    // intentionally immutable for provenance
  },

  simulationStartDate: {
    name: 'simulationStartDate',
    label: 'Simulation Start Date',
    inputType: 'date',
  },

  simulationEndDate: {
    name: 'simulationEndDate',
    label: 'Simulation End Date',
    editable: { owner: true },
    inputType: 'date',
  },

  runStartDate: {
    name: 'runStartDate',
    label: 'Run Start Date',
    inputType: 'date',
  },

  runEndDate: {
    name: 'runEndDate',
    label: 'Run End Date',
    inputType: 'date',
  },

  compiler: {
    name: 'compiler',
    label: 'Compiler',
    editable: { owner: true },
  },

  // -------------------- Metadata --------------------
  keyFeatures: {
    name: 'keyFeatures',
    label: 'Key Features',
    editable: { owner: true },
    inputType: 'textarea',
  },

  knownIssues: {
    name: 'knownIssues',
    label: 'Known Issues',
    editable: { owner: true },
    inputType: 'textarea',
  },

  notesMarkdown: {
    name: 'notesMarkdown',
    label: 'Notes',
    editable: { owner: true },
    inputType: 'textarea',
  },

  // -------------------- Version Control --------------------
  gitRepositoryUrl: {
    name: 'gitRepositoryUrl',
    label: 'Git Repository URL',
    editable: { owner: true },
    inputType: 'url',
  },

  gitBranch: {
    name: 'gitBranch',
    label: 'Git Branch',
    editable: { owner: true },
  },

  gitTag: {
    name: 'gitTag',
    label: 'Git Tag',
    editable: { owner: true },
  },

  gitCommitHash: {
    name: 'gitCommitHash',
    label: 'Git Commit Hash',
    editable: { owner: true },
  },

  // -------------------- Misc --------------------
  extra: {
    name: 'extra',
    label: 'Extra Metadata',
    editable: { owner: true },
    inputType: 'textarea',
  },

  // -------------------- Audit / System --------------------
  id: {
    name: 'id',
    label: 'Simulation ID',
    system: true,
  },

  createdAt: {
    name: 'createdAt',
    label: 'Created At',
    system: true,
  },

  updatedAt: {
    name: 'updatedAt',
    label: 'Last Updated At',
    system: true,
  },

  createdBy: {
    name: 'createdBy',
    label: 'Created By',
    system: true,
  },

  lastUpdatedBy: {
    name: 'lastUpdatedBy',
    label: 'Last Updated By',
    system: true,
  },
};

/**
 * ------------------------------------------------------------------
 * PERMISSION HELPER
 * ------------------------------------------------------------------
 */
export function canEditSimulationField(
  field: SimulationFieldDef,
  ctx: { isOwner: boolean; isAdmin: boolean },
): boolean {
  if (!field.editable) return false;
  if (field.editable.admin && ctx.isAdmin) return true;
  if (field.editable.owner && ctx.isOwner) return true;

  return false;
}
