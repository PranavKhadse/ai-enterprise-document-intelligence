import React from 'react';
import { AlertOctagon, RefreshCw, Copy, Check } from 'lucide-react';
import { Button } from './Button';
import { cn } from '../../utils/cn';

export interface ErrorStateProps {
  title?: string;
  message: string;
  requestId?: string | null;
  onRetry?: () => void;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Something went wrong',
  message,
  requestId,
  onRetry,
  className,
}) => {
  const [copied, setCopied] = React.useState(false);

  const copyRequestId = () => {
    if (requestId) {
      navigator.clipboard.writeText(requestId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center p-8 text-center rounded-2xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/50 dark:bg-rose-950/20 my-4',
        className
      )}
    >
      <div className="w-12 h-12 rounded-full bg-rose-100 dark:bg-rose-900/50 flex items-center justify-center text-rose-600 dark:text-rose-400 mb-3">
        <AlertOctagon className="w-6 h-6" />
      </div>
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
      <p className="mt-1 text-xs text-rose-700 dark:text-rose-300 max-w-md break-words">{message}</p>

      {requestId && (
        <div className="mt-3 flex items-center space-x-1.5 text-xs font-mono bg-rose-100/70 dark:bg-rose-900/40 text-rose-800 dark:text-rose-200 px-3 py-1 rounded-md border border-rose-200 dark:border-rose-800">
          <span>Request ID: {requestId}</span>
          <button
            onClick={copyRequestId}
            className="hover:text-rose-950 dark:hover:text-white p-0.5"
            title="Copy Request ID"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      )}

      {onRetry && (
        <div className="mt-4">
          <Button variant="secondary" size="sm" onClick={onRetry} leftIcon={<RefreshCw className="w-3.5 h-3.5" />}>
            Retry Request
          </Button>
        </div>
      )}
    </div>
  );
};
