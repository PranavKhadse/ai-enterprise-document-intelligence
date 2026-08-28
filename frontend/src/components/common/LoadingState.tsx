import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '../../utils/cn';

export interface LoadingStateProps {
  message?: string;
  className?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = 'Loading data...',
  className,
}) => {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center p-12 text-center text-slate-500 dark:text-slate-400 space-y-3',
        className
      )}
    >
      <Loader2 className="w-8 h-8 animate-spin text-indigo-600 dark:text-indigo-400" />
      <p className="text-xs font-medium">{message}</p>
    </div>
  );
};
