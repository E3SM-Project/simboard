import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '@/auth/AuthContext';

const AuthCallback: React.FC = () => {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();

  useEffect(() => {
    const completeLogin = async () => {
      try {
        // ✅ Ask backend who we are; cookie already set by FastAPI
        await refreshUser();

        // ✅ Redirect wherever you want after login
        navigate('/dashboard', { replace: true });
      } catch (err) {
        console.error('Failed to refresh user:', err);
        navigate('/login', { replace: true });
      }
    };

    completeLogin();
  }, [navigate, refreshUser]);

  return (
    <div className="flex items-center justify-center h-screen">
      <h1 className="text-xl font-semibold">Signing you in...</h1>
    </div>
  );
};

export default AuthCallback;
