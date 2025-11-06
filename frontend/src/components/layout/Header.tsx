import React from 'react';

import { useAuth } from '@/auth/AuthContext';

const Header: React.FC = () => {
  const { user, isAuthenticated, loginWithGithub, logout, loading } = useAuth();

  return (
    <header
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '1rem',
        borderBottom: '1px solid #ddd',
      }}
    >
      <h2>My App</h2>
      {loading ? (
        <span>Loading...</span>
      ) : isAuthenticated ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span>{user?.email}</span>
          <button onClick={logout}>Logout</button>
        </div>
      ) : (
        <button onClick={loginWithGithub}>Login with GitHub</button>
      )}
    </header>
  );
};

export default Header;
