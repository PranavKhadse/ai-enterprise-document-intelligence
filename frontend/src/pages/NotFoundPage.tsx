import React from 'react';
import { FileQuestion, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';

export const NotFoundPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center p-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-indigo-50 dark:bg-indigo-950/80 border border-indigo-200 dark:border-indigo-800 flex items-center justify-center text-indigo-600 dark:text-indigo-400 mb-6 shadow-lg shadow-indigo-500/10">
        <FileQuestion className="w-8 h-8" />
      </div>

      <Badge variant="indigo" size="md" className="mb-3">
        404 NOT FOUND
      </Badge>

      <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
        Document or Page Not Found
      </h1>

      <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 max-w-md">
        The requested resource path does not exist in the enterprise document intelligence platform.
      </p>

      <div className="mt-8">
        <Button variant="primary" onClick={() => navigate('/dashboard')} leftIcon={<ArrowLeft className="w-4 h-4" />}>
          Return to Dashboard
        </Button>
      </div>
    </div>
  );
};
