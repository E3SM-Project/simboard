export type ArtifactKind =
  | "output"
  | "archive"
  | "runScript"
  | "postprocessingScript";

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
