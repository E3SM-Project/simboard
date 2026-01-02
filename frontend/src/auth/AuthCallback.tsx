import { CheckCircle, XCircle } from 'lucide-react';
import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '@/auth/hooks/useAuth';
import { Spinner } from '@/components/ui/spinner';
import { toast } from '@/hooks/use-toast';

export const AuthCallback: React.FC = () => {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();

  useEffect(() => {
    const completeLogin = async () => {
      try {
        // NOTE: FastAPI Users exchanges the OAuth code and sets the cookie.
        // Here we just need to refresh the user data to confirm login.
        await refreshUser();

        toast({
          title: 'Logged In',
          description: (
            <div className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-600" />
              Welcome back!
            </div>
          ),
          duration: 2000,
        });

        navigate('/', { replace: true });
      } catch (err) {
        console.error('OAuth post-login failed:', err);

        toast({
          title: 'Login Failed',
          description: (
            <div className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-red-600" />
              <span>We couldn’t sign you in. Please try again.</span>
            </div>
          ),
          duration: 3000,
        });

        navigate('/', { replace: true });
      }
    };

    completeLogin();
  }, [navigate, refreshUser]);

  return (
    <div className="flex items-center justify-center h-screen gap-2">
      <Spinner className="w-5 h-5" />
      <p className="text-lg font-medium">Signing you in…</p>
    </div>
  );
};
