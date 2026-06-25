export type ExternalLinkKind = 'diagnostic' | 'performance' | 'docs' | 'other';
export type ExternalLinkOwnerType = 'simulation' | 'case';

/**
 * Represents a link to an external diagnostic, documentation, or related resource.
 */
export interface ExternalLinkIn {
  kind: ExternalLinkKind;
  url: string;
  label?: string | null;
}

export interface ExternalLinkOut extends ExternalLinkIn {
  id: string; // UUID
  ownerType: ExternalLinkOwnerType;
  createdAt: string; // ISO datetime
  updatedAt: string; // ISO datetime
}
