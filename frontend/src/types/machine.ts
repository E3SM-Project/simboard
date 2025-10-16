/**
 * Represents an HPC machine on which simulations are run.
 */
export interface Machine {
  id: string;
  name: string;
  site?: string;
  architecture?: string;
  scheduler?: string;
  gpu?: boolean;
  notes?: string;
  createdAt?: string;
}
