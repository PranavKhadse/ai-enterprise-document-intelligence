import React from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';

export interface ErrorPageProps {
  error?: Error | null;
  requestId?: string | null;
  resetErrorBoundary?: () => void;
}

export const ErrorPage: React.FC<ErrorPageProps> = ({
  error,
  requestId,
  resetErrorBoundary,
}) => {
  const navigate = useNavigate();

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center p-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-amber-100 dark:bg-amber-950/80 border border-amber-200 dark:border-amber-800 flex items-center justify-center text-amber-600 dark:text-amber-400 mb-6 shadow-lg shadow-amber-500/10">
        <AlertTriangle className="w-8 h-8" />
      </div>

      <Badge variant="amber" size="md" className="mb-3">
        SYSTEM FAULT
      </Badge>

      <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
        An Unexpected Platform Error Occurred
      </h1>

      <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 max-w-md">
        {error?.message || 'An unhandled application exception occurred during execution.'}
      </p>

      {requestId && (
        <div className="mt-4 p-2.5 rounded-lg bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs font-mono text-slate-600 dark:text-slate-400">
          Support Correlation Request ID: {requestId}
        </div>
      )}

      <div className="mt-8 flex space-x-3">
        {resetErrorBoundary ? (
          <Button variant="primary" onClick={resetErrorBoundary} leftIcon={<RefreshCw className="w-4 h-4" />}>
            Try Again
          </Button>
        ) : (
          <Button variant="primary" onClick={() => window.location.reload()} leftIcon={<RefreshCw className="w-4 h-4" />}>
            Reload Page
          </Button>
        )}
        <Button variant="secondary" onClick={() => navigate('/dashboard')} leftIcon={<Home className="w-4 h-4" />}>
          Dashboard
        </Button>
      </div>
    </div>
  );
};
