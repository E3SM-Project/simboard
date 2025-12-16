import { LogOut } from 'lucide-react';
import React, {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';

import api, { registerLogoutHandler } from '@/api/api';
import { toast } from '@/hooks/use-toast';
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
    try {
      const { data } = await api.get<{ authorization_url: string }>('/auth/github/authorize');
      const { authorization_url } = data;

      // Redirect browser to GitHub authorization URL to initiate OAuth flow.
      window.location.href = authorization_url;
    } catch {
      toast({
        title: 'Failed to initiate GitHub login',
        description: "We couldn't start the login process. Please try again.",
        variant: 'destructive',
      });
    }
  };

  const logout = useCallback(async (): Promise<void> => {
    try {
      await api.post('/auth/logout');
    } catch {
      // ignore errors — local logout still succeeds
    } finally {
      setUser(null);

      toast({
        title: (
          <div className="flex items-center gap-2">
            <LogOut className="h-5 w-5 text-gray-600" />
            Signed out
          </div>
        ),
        description: 'You’ve been logged out.',
        duration: 2000,
      });
    }
  }, []);

  const logoutRef = useRef(logout);

  // Keep ref updated but don’t re-register
  useEffect(() => {
    logoutRef.current = logout;
  }, [logout]);

  // Register once with a stable wrapper
  useEffect(() => {
    registerLogoutHandler(() => logoutRef.current());
  }, []);

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
