import React from 'react';
import { Shield, Building2, Lock, Key, LogOut } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { Card, CardHeader, CardTitle } from '../components/common/Card';
import { useNavigate } from 'react-router-dom';

export const ProfilePage: React.FC = () => {
  const { user, isAdmin, clearanceLevel, roles, departmentName, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const clearanceTiers = [
    { level: 1, role: 'Employee', desc: 'Read access to public and general departmental documents.' },
    { level: 2, role: 'Analyst', desc: 'Full access to department RAG, comparison, and analysis tools.' },
    { level: 3, role: 'Auditor', desc: 'Cross-department inspection and compliance analysis.' },
    { level: 4, role: 'Admin', desc: 'Authoritative administrative controls and immutable audit log inspection.' },
  ];

  return (
    <div className="space-y-6 text-left max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          User Identity & Clearance Profile
        </h1>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Server-authenticated principal identity, effective RBAC roles, and security authorization matrix.
        </p>
      </div>

      {/* Profile Card */}
      <Card className="p-6 bg-white dark:bg-slate-900 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center space-x-4">
            <div className="w-14 h-14 rounded-2xl bg-indigo-600 flex items-center justify-center text-white text-xl font-bold shadow-md shadow-indigo-500/20">
              {user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">{user?.email}</h2>
              <div className="flex items-center space-x-2 mt-1">
                <Badge variant={user?.is_active ? 'emerald' : 'rose'} size="sm" dot>
                  {user?.is_active ? 'ACCOUNT ACTIVE' : 'SUSPENDED'}
                </Badge>
                {isAdmin && (
                  <Badge variant="rose" size="sm">
                    ADMINISTRATOR
                  </Badge>
                )}
              </div>
            </div>
          </div>

          <Button variant="danger" size="sm" onClick={handleLogout} leftIcon={<LogOut className="w-4 h-4" />}>
            Sign Out
          </Button>
        </div>

        {/* Identity Details Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 space-y-1">
            <div className="flex items-center space-x-1.5 text-slate-500 font-semibold">
              <Key className="w-3.5 h-3.5" />
              <span>Principal UUID</span>
            </div>
            <p className="font-mono text-slate-800 dark:text-slate-200">{user?.id || 'N/A'}</p>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 space-y-1">
            <div className="flex items-center space-x-1.5 text-slate-500 font-semibold">
              <Building2 className="w-3.5 h-3.5" />
              <span>Assigned Department</span>
            </div>
            <p className="font-semibold text-slate-800 dark:text-slate-200">
              {departmentName} {user?.department_id && `(${user.department_id})`}
            </p>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 space-y-1">
            <div className="flex items-center space-x-1.5 text-slate-500 font-semibold">
              <Shield className="w-3.5 h-3.5" />
              <span>Effective RBAC Roles</span>
            </div>
            <div className="flex flex-wrap gap-1 mt-1">
              {roles.map((r) => (
                <Badge key={r} variant="indigo" size="sm">
                  {r}
                </Badge>
              ))}
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 space-y-1">
            <div className="flex items-center space-x-1.5 text-slate-500 font-semibold">
              <Lock className="w-3.5 h-3.5" />
              <span>Security Clearance Level</span>
            </div>
            <p className="font-bold text-slate-800 dark:text-slate-200 text-sm">
              Level {clearanceLevel} of 4
            </p>
          </div>
        </div>
      </Card>

      {/* Security Clearance Matrix Explanation */}
      <Card className="p-6 bg-white dark:bg-slate-900 space-y-4">
        <CardHeader className="px-0 pt-0">
          <CardTitle>Enterprise Clearance Hierarchy Matrix</CardTitle>
        </CardHeader>
        <div className="space-y-3">
          {clearanceTiers.map((tier) => {
            const isUserTier = clearanceLevel >= tier.level;
            return (
              <div
                key={tier.level}
                className={`p-3.5 rounded-xl border flex items-center justify-between text-xs transition-all ${
                  clearanceLevel === tier.level
                    ? 'bg-indigo-50/70 dark:bg-indigo-950/40 border-indigo-300 dark:border-indigo-800'
                    : isUserTier
                    ? 'bg-slate-50/50 dark:bg-slate-800/30 border-slate-200 dark:border-slate-800'
                    : 'opacity-50 bg-slate-100/30 dark:bg-slate-900 border-slate-200 dark:border-slate-800'
                }`}
              >
                <div className="space-y-0.5">
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-slate-900 dark:text-slate-100">
                      Tier {tier.level} — {tier.role}
                    </span>
                    {clearanceLevel === tier.level && (
                      <Badge variant="indigo" size="sm">
                        CURRENT TIER
                      </Badge>
                    )}
                  </div>
                  <p className="text-slate-500">{tier.desc}</p>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
};
