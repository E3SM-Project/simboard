export interface User {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
  full_name?: string | null;
}
