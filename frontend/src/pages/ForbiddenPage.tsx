import React from 'react';
import { ShieldX, ArrowLeft, ShieldAlert } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common/Button';
import { useAuth } from '../hooks/useAuth';
import { Badge } from '../components/common/Badge';

export interface ForbiddenPageProps {
  requiredRole?: string;
  minClearance?: number;
}

export const ForbiddenPage: React.FC<ForbiddenPageProps> = ({
  requiredRole = 'Admin',
  minClearance = 4,
}) => {
  const navigate = useNavigate();
  const { user, clearanceLevel, roles } = useAuth();

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center p-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-rose-100 dark:bg-rose-950/80 border border-rose-200 dark:border-rose-800 flex items-center justify-center text-rose-600 dark:text-rose-400 mb-6 shadow-lg shadow-rose-500/10">
        <ShieldX className="w-8 h-8" />
      </div>

      <Badge variant="rose" size="md" className="mb-3">
        403 HTTP FORBIDDEN
      </Badge>

      <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
        Access Denied — Insufficient Security Clearance
      </h1>

      <p className="mt-2 text-sm text-slate-500 dark:text-slate-400 max-w-md">
        This resource is strictly protected by server-side RBAC and clearance controls. Your authenticated principal does not hold the required authorization tier.
      </p>

      {user && (
        <div className="mt-6 p-4 rounded-xl bg-slate-100/70 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs text-left max-w-md w-full space-y-2">
          <div className="flex justify-between">
            <span className="text-slate-500">Your Identity:</span>
            <span className="font-mono text-slate-700 dark:text-slate-300">{user.email}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Your Effective Roles:</span>
            <span className="font-mono text-slate-700 dark:text-slate-300">{roles.join(', ') || 'None'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Your Clearance Level:</span>
            <span className="font-mono text-slate-700 dark:text-slate-300">Level {clearanceLevel}</span>
          </div>
          <div className="pt-2 border-t border-slate-200 dark:border-slate-800 flex justify-between font-semibold text-rose-600 dark:text-rose-400">
            <span>Required Authorization:</span>
            <span>{requiredRole} (Clearance L{minClearance})</span>
          </div>
        </div>
      )}

      <div className="mt-8 flex space-x-3">
        <Button variant="secondary" onClick={() => navigate('/dashboard')} leftIcon={<ArrowLeft className="w-4 h-4" />}>
          Return to Dashboard
        </Button>
        <Button variant="outline" onClick={() => navigate('/profile')} leftIcon={<ShieldAlert className="w-4 h-4" />}>
          View My Clearance
        </Button>
      </div>
    </div>
  );
};
