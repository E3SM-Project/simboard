import { Outlet } from 'react-router-dom';

import { useAuth } from '@/auth/AuthContext';
import { LoginCard } from '@/auth/components/LoginCard';

export const ProtectedRoute = () => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500" aria-live="polite">
        Checking authentication…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginCard />;
  }

  return <Outlet />;
};
