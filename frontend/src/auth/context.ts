import { createContext } from 'react';

import type { User } from '@/types/user';

export interface AuthContextType {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  loginWithGithub: () => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);
