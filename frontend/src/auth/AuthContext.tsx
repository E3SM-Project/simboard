import { LogOut } from 'lucide-react';
import React, { ReactNode, useCallback, useEffect, useRef, useState } from 'react';

import { api, registerLogoutHandler } from '@/api/api';
import { setAuthenticated } from '@/api/authState';
import { AuthContext, AuthContextType } from '@/auth/context';
import { toast } from '@/hooks/use-toast';
import type { User } from '@/types/user';

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const refreshUser = useCallback(async (): Promise<void> => {
    try {
      const { data } = await api.get<User>('/users/me');
      setUser(data);
      setAuthenticated(true);
    } catch {
      setUser(null);
      setAuthenticated(false);
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

  const logout = useCallback(async ({ silent = false }: { silent?: boolean } = {}) => {
    try {
      await api.post('/auth/logout');
    } catch {
      /* ignore */
    } finally {
      setUser(null);
      setAuthenticated(false);

      if (!silent) {
        toast({
          title: 'Signed Out',
          description: (
            <div className="flex items-center gap-2">
              <LogOut className="h-5 w-5 text-gray-600" />
              You’ve been logged out.
            </div>
          ),
          duration: 2000,
        });
      }
    }
  }, []);

  const logoutRef = useRef(logout);

  // Keep ref updated but don’t re-register
  useEffect(() => {
    logoutRef.current = logout;
  }, [logout]);

  // Register once with a stable wrapper
  useEffect(() => {
    registerLogoutHandler(() => logoutRef.current({ silent: true }));
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
