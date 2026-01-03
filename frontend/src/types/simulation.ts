import type { ArtifactIn, ArtifactOut } from '@/types/artifact';
import type { ExternalLinkIn, ExternalLinkOut } from '@/types/link';
import type { Machine } from '@/types/machine';

/**
 * Request payload for creating a new simulation.
 * Equivalent to FastAPI SimulationCreate schema.
 */
export interface SimulationCreate {
  // Configuration
  // ~~~~~~~~~~~~~~
  name: string;
  caseName: string;
  description: string | null;
  compset: string;
  compsetAlias: string;
  gridName: string;
  gridResolution: string;
  parentSimulationId?: string | null;

  // Model setup/context
  // ~~~~~~~~~~~~~~~~~~~
  simulationType: string;
  status: string;
  campaignId?: string | null;
  experimentTypeId?: string | null;
  initializationType: string;
  groupName?: string | null;

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

  // Miscellaneous
  // ~~~~~~~~~~~~~~~~~
  extra?: Record<string, unknown>;

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

  // Provenance & submission
  // ~~~~~~~~~~~~~~~~~~~~~~~
  createdAt: string; // Server-managed field
  updatedAt: string; // Server-managed field

  // Relationships
  // ~~~~~~~~~~~~~~
  machine: Machine;

  // Computed fields
  // ~~~~~~~~~~~~~~~
  groupedArtifacts: Record<string, ArtifactOut[]>;
  groupedLinks: Record<string, ExternalLinkOut[]>;
}
