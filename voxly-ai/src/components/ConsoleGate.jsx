import React from 'react';
import { useAuth } from '../context/AuthContext';
import { ConsoleSignInRequired } from './ConsoleSignInRequired';

export function ConsoleGate({ children, onSignIn, onBackToMarketing }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#FAF9FD] text-sm text-[#524E5E]">
        Checking session…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <ConsoleSignInRequired onSignIn={onSignIn} onBackToMarketing={onBackToMarketing} />;
  }

  return children;
}
