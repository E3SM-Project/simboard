// simulationFields.ts
import type { SimulationCreate, SimulationOut } from '@/types';

/**
 * Fields that exist both:
 * - at creation time (SimulationCreate / SimulationCreateForm)
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
   * Whether this field can be edited after creation (PATCH semantics).
   */
  editableAfterCreate: boolean;

  /**
   * Who may edit the field (if editableAfterCreate = true).
   */
  editableByOwner?: boolean;
  editableByAdmin?: boolean;

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
    editableAfterCreate: true,
    editableByOwner: true,
    inputType: 'text',
  },

  caseName: {
    name: 'caseName',
    label: 'Case Name',
    editableAfterCreate: false,
  },

  description: {
    name: 'description',
    label: 'Description',
    editableAfterCreate: true,
    editableByOwner: true,
    inputType: 'textarea',
  },

  compset: {
    name: 'compset',
    label: 'Compset',
    editableAfterCreate: false,
  },

  compsetAlias: {
    name: 'compsetAlias',
    label: 'Compset Alias',
    editableAfterCreate: false,
  },

  gridName: {
    name: 'gridName',
    label: 'Grid Name',
    editableAfterCreate: false,
  },

  gridResolution: {
    name: 'gridResolution',
    label: 'Grid Resolution',
    editableAfterCreate: false,
  },

  parentSimulationId: {
    name: 'parentSimulationId',
    label: 'Parent Simulation ID',
    editableAfterCreate: true,
    editableByOwner: true,
  },

  // -------------------- Model Setup / Context --------------------
  simulationType: {
    name: 'simulationType',
    label: 'Simulation Type',
    editableAfterCreate: false,
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
    editableAfterCreate: true,
    editableByAdmin: true,
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
    editableAfterCreate: true,
    editableByOwner: true,
  },

  experimentTypeId: {
    name: 'experimentTypeId',
    label: 'Experiment Type ID',
    editableAfterCreate: true,
    editableByOwner: true,
  },

  initializationType: {
    name: 'initializationType',
    label: 'Initialization Type',
    editableAfterCreate: false,
  },

  groupName: {
    name: 'groupName',
    label: 'Group Name',
    editableAfterCreate: true,
    editableByOwner: true,
  },

  // -------------------- Timeline --------------------
  machineId: {
    name: 'machineId',
    label: 'Machine',
    editableAfterCreate: false,
    inputType: 'select',
  },

  simulationStartDate: {
    name: 'simulationStartDate',
    label: 'Simulation Start Date',
    editableAfterCreate: false,
    inputType: 'date',
  },

  simulationEndDate: {
    name: 'simulationEndDate',
    label: 'Simulation End Date',
    editableAfterCreate: true,
    editableByOwner: true,
    inputType: 'date',
  },

  runStartDate: {
    name: 'runStartDate',
    label: 'Run Start Date',
    editableAfterCreate: false,
    inputType: 'date',
  },

  runEndDate: {
    name: 'runEndDate',
    label: 'Run End Date',
    editableAfterCreate: false,
    inputType: 'date',
  },

  compiler: {
    name: 'compiler',
    label: 'Compiler',
    editableAfterCreate: true,
    editableByOwner: true,
  },

  // -------------------- Metadata --------------------
  keyFeatures: {
    name: 'keyFeatures',
    label: 'Key Features',
    editableAfterCreate: true,
    editableByOwner: true,
    inputType: 'textarea',
  },

  knownIssues: {
    name: 'knownIssues',
    label: 'Known Issues',
    editableAfterCreate: true,
    editableByOwner: true,
    inputType: 'textarea',
  },

  notesMarkdown: {
    name: 'notesMarkdown',
    label: 'Notes',
    editableAfterCreate: true,
    editableByOwner: true,
    inputType: 'textarea',
  },

  // -------------------- Version Control --------------------
  gitRepositoryUrl: {
    name: 'gitRepositoryUrl',
    label: 'Git Repository URL',
    editableAfterCreate: true,
    editableByOwner: true,
    inputType: 'url',
  },

  gitBranch: {
    name: 'gitBranch',
    label: 'Git Branch',
    editableAfterCreate: true,
    editableByOwner: true,
  },

  gitTag: {
    name: 'gitTag',
    label: 'Git Tag',
    editableAfterCreate: true,
    editableByOwner: true,
  },

  gitCommitHash: {
    name: 'gitCommitHash',
    label: 'Git Commit Hash',
    editableAfterCreate: true,
    editableByOwner: true,
  },

  // -------------------- Misc --------------------
  extra: {
    name: 'extra',
    label: 'Extra Metadata',
    editableAfterCreate: true,
    editableByOwner: true,
    inputType: 'textarea',
  },

  // -------------------- Audit / System --------------------
  id: {
    name: 'id',
    label: 'Simulation ID',
    editableAfterCreate: false,
    system: true,
  },

  createdAt: {
    name: 'createdAt',
    label: 'Created At',
    editableAfterCreate: false,
    system: true,
  },

  updatedAt: {
    name: 'updatedAt',
    label: 'Last Updated At',
    editableAfterCreate: false,
    system: true,
  },

  createdBy: {
    name: 'createdBy',
    label: 'Created By',
    editableAfterCreate: false,
    system: true,
  },

  lastUpdatedBy: {
    name: 'lastUpdatedBy',
    label: 'Last Updated By',
    editableAfterCreate: false,
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
  if (field.system) return false;
  if (!field.editableAfterCreate) return false;
  if (field.editableByAdmin && ctx.isAdmin) return true;
  if (field.editableByOwner && ctx.isOwner) return true;

  return false;
}
