import { Outlet } from 'react-router-dom';

import { LoginCard } from '@/auth/components/LoginCard';
import { useAuth } from '@/auth/hooks/useAuth';
import { LoadingState } from '@/components/ui/loading-state';

export const ProtectedRoute = () => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return <LoadingState className="min-h-64" label="Checking authentication" />;
  }

  if (!isAuthenticated) {
    return <LoginCard />;
  }

  return <Outlet />;
};
