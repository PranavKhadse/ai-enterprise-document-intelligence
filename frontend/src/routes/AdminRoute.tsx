import React from 'react';
import { useAuth } from '../hooks/useAuth';
import { LoadingState } from '../components/common/LoadingState';
import { ForbiddenPage } from '../pages/ForbiddenPage';

export const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAdmin, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <LoadingState message="Verifying administrative clearance..." />
      </div>
    );
  }

  if (!isAdmin) {
    return <ForbiddenPage requiredRole="Admin" minClearance={4} />;
  }

  return <>{children}</>;
};
