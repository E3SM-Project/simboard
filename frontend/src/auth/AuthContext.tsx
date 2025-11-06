import React, {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';

import api, { registerLogoutHandler } from '@/api/axios';
import type { User } from '@/types/user';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  loginWithGithub: () => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const refreshUser = useCallback(async (): Promise<void> => {
    try {
      const { data } = await api.get<User>('/users/me');
      setUser(data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loginWithGithub = async () => {
    const res = await fetch('https://localhost:8000/auth/github/authorize');
    const { authorization_url } = await res.json();

    // Redirect browser to GitHub
    window.location.href = authorization_url;
  };

  const logout = useCallback(async (): Promise<void> => {
    try {
      await api.post('/auth/logout');
    } catch {
      // ignore errors
    } finally {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    registerLogoutHandler(logout);
  }, [logout]);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const value: AuthContextType = {
    user,
    loading,
    isAuthenticated: !!user,
    loginWithGithub,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
};
