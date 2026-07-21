/**
 * Represents an HPC machine on which simulations are run.
 */
export interface Machine {
  id: string;
  name: string;
  siteId?: string;
  site?: string;
  architecture?: string;
  scheduler?: string;
  gpu?: boolean;
  notes?: string;
  createdAt?: string;
}
