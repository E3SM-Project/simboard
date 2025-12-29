// Mapping from form field names to artifact enums.
export const ARTIFACT_KIND_MAP: Record<
  'outputPath' | 'archivePaths' | 'runScriptPaths' | 'postprocessingScriptPaths',
  ArtifactKind
> = {
  outputPath: 'output',
  archivePaths: 'archive',
  runScriptPaths: 'run_script',
  postprocessingScriptPaths: 'postprocessing_script',
};

export type ArtifactKind = 'output' | 'archive' | 'run_script' | 'postprocessing_script';

/**
 * Represents an artifact uploaded or linked to a simulation.
 */
export interface ArtifactIn {
  kind: ArtifactKind;
  uri: string;
  label?: string | null;
}

export interface ArtifactOut extends ArtifactIn {
  id: string; // UUID
  createdAt: string; // ISO datetime
  updatedAt: string; // ISO datetime
}
