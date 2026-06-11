export interface User {
  id: string;
  email: string;
  role: string;
  has_verified_e3sm_membership?: boolean;
  can_edit_managed_content?: boolean;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
  full_name?: string | null;
}
