import { useContext } from 'react';

import type { AuthContextType } from '@/auth/context';
import { AuthContext } from '@/auth/context';

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);

  if (!context) throw new Error('useAuth must be used within an AuthProvider');

  return context;
};
