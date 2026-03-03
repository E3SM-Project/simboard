import type { ArtifactIn, ArtifactOut } from '@/types/artifact';
import type { ExternalLinkIn, ExternalLinkOut } from '@/types/link';
import type { Machine } from '@/types/machine';

/**
 * API response model for a Case.
 */
export interface CaseOut {
  id: string;
  name: string;
  canonicalSimulationId: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * Request payload for creating a new simulation.
 * Equivalent to FastAPI SimulationCreate schema.
 */
export interface SimulationCreate {
  // Configuration
  // ~~~~~~~~~~~~~~
  name: string;
  caseId: string; // UUID
  executionId: string;
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
  campaign?: string | null;
  experimentType?: string | null;
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
  runConfigDeltas?: Record<string, { canonical: unknown; current: unknown }> | null;

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
  isCanonical: boolean;
  changeCount: number;

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
