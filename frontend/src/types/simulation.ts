import type { ArtifactIn, ArtifactOut } from '@/types/artifact';
import type { ExternalLinkIn, ExternalLinkOut } from '@/types/link';
import type { Machine } from '@/types/machine';

export interface SimulationUserPreview {
  id: string;
  email: string;
  role: string;
  full_name?: string | null;
}

/**
 * API response model for a Case with nested simulation summaries.
 */
export interface CaseOut {
  id: string;
  name: string;
  caseGroup: string | null;
  referenceSimulationId: string | null;
  simulations: SimulationSummaryOut[];
  machineNames: string[];
  hpcUsernames: string[];
  createdAt: string;
  updatedAt: string;
}

/**
 * Lightweight simulation summary for case-level nesting.
 * Does NOT include heavy relationships (machine, artifacts, links).
 */
export interface SimulationSummaryOut {
  id: string;
  executionId: string;
  status: string;
  isReference: boolean;
  changeCount: number;
  simulationStartDate: string;
  simulationEndDate: string | null;
}

/**
 * Request payload for creating a new simulation.
 * Equivalent to FastAPI SimulationCreate schema.
 */
export interface SimulationCreate {
  // Configuration
  // ~~~~~~~~~~~~~~
  caseId: string; // UUID
  executionId: string;
  description: string | null;
  compset: string;
  compsetAlias: string;
  gridName: string;
  gridResolution: string;

  // Model setup/context
  // ~~~~~~~~~~~~~~~~~~~
  simulationType: string;
  status: string;
  campaign?: string | null;
  experimentType?: string | null;
  initializationType: string;

  // Model timeline
  // ~~~~~~~~~~~~~~
  machineId: string; // UUID
  simulationStartDate: string; // ISO datetime
  simulationEndDate?: string | null;
  runStartDate?: string | null;
  runEndDate?: string | null;
  compiler?: string | null;

  // Metadata & audit
  // ~~~~~~~~~~~~~~~~~
  keyFeatures?: string | null;
  knownIssues?: string | null;
  notesMarkdown?: string | null;

  // Version control
  // ~~~~~~~~~~~~~~~
  gitRepositoryUrl?: string | null;
  gitBranch?: string | null;
  gitTag?: string | null;
  gitCommitHash?: string | null;

  // Provenance & submission
  // ~~~~~~~~~~~~~~~~~~~~~~~
  createdBy?: string | null;
  lastUpdatedBy?: string | null;
  hpcUsername?: string | null;

  // Miscellaneous
  // ~~~~~~~~~~~~~~~~~
  extra?: Record<string, unknown>;
  runConfigDeltas?: Record<string, { reference: unknown; current: unknown }> | null;

  // Relationships
  // ~~~~~~~~~~~~~~
  artifacts: ArtifactIn[];
  links: ExternalLinkIn[];
}
// Extends SimulationCreate with optional fields for file paths.
export interface SimulationCreateForm extends SimulationCreate {
  outputPath?: string | null;
  archivePaths?: string[] | null;
  runScriptPaths?: string[] | null;
  postprocessingScriptPaths?: string[] | null;
}

/**
 * API response model for a simulation (from FastAPI / DB).
 * Equivalent to FastAPI SimulationOut schema.
 */
export interface SimulationOut extends SimulationCreate {
  // Configuration
  // ~~~~~~~~~~~~~~
  id: string;
  caseName: string;
  caseGroup: string | null;
  isReference: boolean;
  changeCount: number;

  // Provenance & submission
  // ~~~~~~~~~~~~~~~~~~~~~~~
  createdAt: string; // Server-managed field
  updatedAt: string; // Server-managed field
  createdByUser?: SimulationUserPreview | null;
  lastUpdatedByUser?: SimulationUserPreview | null;

  // Relationships
  // ~~~~~~~~~~~~~~
  machine: Machine;

  // Computed fields
  // ~~~~~~~~~~~~~~~
  groupedArtifacts: Record<string, ArtifactOut[]>;
  groupedLinks: Record<string, ExternalLinkOut[]>;
}
