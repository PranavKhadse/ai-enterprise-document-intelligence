import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  FileText,
  Search,
  BotMessageSquare,
  GitCompare,
  Upload,
  Activity,
  Shield,
  Lock,
  ArrowUpRight,
  ShieldAlert,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { documentsApi } from '../api/documents';
import { healthApi } from '../api/health';
import { auditApi } from '../api/audit';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { Table, Column } from '../components/common/Table';
import { DocumentItemResponse } from '../types/document';
import { formatDate, truncateHash } from '../utils/formatters';

export const DashboardPage: React.FC = () => {
  const { user, isAdmin, clearanceLevel, roles, departmentName } = useAuth();
  const navigate = useNavigate();

  // Fetch recent documents
  const {
    data: docsData,
    isLoading: isDocsLoading,
  } = useQuery({
    queryKey: ['documents', 'recent'],
    queryFn: () => documentsApi.list({ limit: 5, offset: 0 }),
  });

  // Fetch live system health
  const {
    data: healthData,
    isLoading: isHealthLoading,
  } = useQuery({
    queryKey: ['system-health'],
    queryFn: () => healthApi.getHealth(),
    refetchInterval: 30000,
  });

  // Fetch admin security stats if admin
  const {
    data: auditStats,
    isLoading: isStatsLoading,
  } = useQuery({
    queryKey: ['audit-stats', 'dashboard'],
    queryFn: () => auditApi.getStatistics(),
    enabled: isAdmin,
  });

  const getClearanceVariant = (level: number) => {
    switch (level) {
      case 4:
        return 'rose';
      case 3:
        return 'purple';
      case 2:
        return 'indigo';
      default:
        return 'slate';
    }
  };

  const columns: Column<DocumentItemResponse>[] = [
    {
      key: 'title',
      header: 'Document Title',
      render: (doc) => (
        <div>
          <span className="font-semibold text-slate-900 dark:text-slate-100">{doc.title}</span>
          <p className="text-[11px] font-mono text-slate-400 mt-0.5">{truncateHash(doc.file_hash)}</p>
        </div>
      ),
    },
    {
      key: 'file_type',
      header: 'Format',
      render: (doc) => (
        <Badge variant="indigo" size="sm">
          {doc.file_type.toUpperCase()}
        </Badge>
      ),
    },
    {
      key: 'created_at',
      header: 'Uploaded',
      render: (doc) => <span className="text-xs text-slate-500">{formatDate(doc.created_at)}</span>,
    },
    {
      key: 'version',
      header: 'Version',
      render: (doc) => (
        <span className="text-xs font-mono bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
          v{doc.current_version}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (doc) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/documents?selected=${doc.id}`);
          }}
          rightIcon={<ArrowUpRight className="w-3.5 h-3.5" />}
        >
          View
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-8 text-left">
      {/* Welcome Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 border border-slate-800 p-8 text-white shadow-xl">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="flex items-center space-x-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400 font-mono">
                Authoritative Workspace
              </span>
              <span className="text-slate-600">·</span>
              <Badge variant={getClearanceVariant(clearanceLevel)} size="sm">
                <Shield className="w-3 h-3" />
                <span>Security Clearance Level {clearanceLevel}</span>
              </Badge>
            </div>
            <h1 className="text-2xl lg:text-3xl font-bold tracking-tight text-white">
              Welcome back, {user?.email || 'Corporate User'}
            </h1>
            <p className="text-xs text-slate-300">
              Your session is active with roles <span className="font-semibold text-white">[{roles.join(', ')}]</span> and assigned department <span className="font-semibold text-white">{departmentName}</span>.
            </p>
          </div>

          <div className="flex flex-wrap gap-3 shrink-0">
            <Button
              variant="primary"
              size="md"
              onClick={() => navigate('/documents?action=upload')}
              leftIcon={<Upload className="w-4 h-4" />}
            >
              Upload PDF
            </Button>
            <Button
              variant="secondary"
              size="md"
              onClick={() => navigate('/rag')}
              leftIcon={<BotMessageSquare className="w-4 h-4" />}
            >
              Ask AI Assistant
            </Button>
          </div>
        </div>

        {/* Decorative Grid Lines */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#1e1b4b10_1px,transparent_1px),linear-gradient(to_bottom,#1e1b4b10_1px,transparent_1px)] bg-[size:24px_24px] pointer-events-none" />
      </div>

      {/* Quick Action Tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card hoverEffect onClick={() => navigate('/documents')} className="cursor-pointer">
          <CardContent className="p-5 flex items-start space-x-4">
            <div className="p-3 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 shrink-0">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Document Hub</h3>
              <p className="text-xs text-slate-500 mt-1">Manage & explore ingested enterprise documents</p>
            </div>
          </CardContent>
        </Card>

        <Card hoverEffect onClick={() => navigate('/search')} className="cursor-pointer">
          <CardContent className="p-5 flex items-start space-x-4">
            <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 shrink-0">
              <Search className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Hybrid Search</h3>
              <p className="text-xs text-slate-500 mt-1">BM25 + Qdrant vectors with Reciprocal Rank Fusion</p>
            </div>
          </CardContent>
        </Card>

        <Card hoverEffect onClick={() => navigate('/rag')} className="cursor-pointer">
          <CardContent className="p-5 flex items-start space-x-4">
            <div className="p-3 rounded-xl bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 shrink-0">
              <BotMessageSquare className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Grounded RAG</h3>
              <p className="text-xs text-slate-500 mt-1">Deterministic citation & claim verification</p>
            </div>
          </CardContent>
        </Card>

        <Card hoverEffect onClick={() => navigate('/compare')} className="cursor-pointer">
          <CardContent className="p-5 flex items-start space-x-4">
            <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 shrink-0">
              <GitCompare className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Compare & Diff</h3>
              <p className="text-xs text-slate-500 mt-1">Detect semantic policy contradictions & metric diffs</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Admin Observability Widget (If Admin) */}
      {isAdmin && (
        <Card className="border-rose-200 dark:border-rose-900/40 bg-gradient-to-br from-white via-rose-50/20 to-white dark:from-slate-900 dark:via-rose-950/10 dark:to-slate-900">
          <CardHeader>
            <div className="flex items-center space-x-2">
              <ShieldAlert className="w-5 h-5 text-rose-600 dark:text-rose-400" />
              <div>
                <CardTitle>Security Observability & Compliance Overview</CardTitle>
                <CardDescription>Server-authoritative audit telemetry for Level 4 Administrators</CardDescription>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/audit')}
              rightIcon={<ArrowUpRight className="w-3.5 h-3.5" />}
            >
              Open Audit Console
            </Button>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                <span className="text-xs text-slate-500 font-medium">Total Audit Events</span>
                <p className="text-2xl font-bold font-mono text-slate-900 dark:text-white mt-1">
                  {isStatsLoading ? '...' : auditStats?.total_events ?? 0}
                </p>
              </div>
              <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                <span className="text-xs text-rose-600 dark:text-rose-400 font-medium">Authorization Denials</span>
                <p className="text-2xl font-bold font-mono text-rose-600 dark:text-rose-400 mt-1">
                  {isStatsLoading ? '...' : auditStats?.authorization_denials ?? 0}
                </p>
              </div>
              <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">Auth Failures</span>
                <p className="text-2xl font-bold font-mono text-amber-600 dark:text-amber-400 mt-1">
                  {isStatsLoading ? '...' : auditStats?.authentication_failures ?? 0}
                </p>
              </div>
              <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
                <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">Active Principals</span>
                <p className="text-2xl font-bold font-mono text-indigo-600 dark:text-indigo-400 mt-1">
                  {isStatsLoading ? '...' : auditStats?.active_users_with_events ?? 0}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main Grid: Recent Documents & System Diagnostics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Recent Ingested Documents */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
              Recently Ingested Documents
            </h2>
            <Button variant="ghost" size="sm" onClick={() => navigate('/documents')}>
              View All ({docsData?.total ?? 0})
            </Button>
          </div>

          <Table
            columns={columns}
            data={docsData?.items || []}
            keyExtractor={(doc) => doc.id}
            isLoading={isDocsLoading}
            emptyText="No documents ingested yet. Upload a PDF document to begin."
            onRowClick={(doc) => navigate(`/documents?selected=${doc.id}`)}
          />
        </div>

        {/* Right 1 Col: System & Environment Status */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center space-x-2">
                <Activity className="w-4 h-4 text-emerald-500" />
                <CardTitle>System Health & Telemetry</CardTitle>
              </div>
              <Badge variant={healthData?.status === 'healthy' ? 'emerald' : 'amber'} size="sm" dot>
                {isHealthLoading ? 'CHECKING...' : healthData?.status.toUpperCase() || 'OFFLINE'}
              </Badge>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
                <span className="text-slate-500">Service Name:</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">
                  {healthData?.project_name || 'Enterprise Document Intelligence'}
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
                <span className="text-slate-500">API Version:</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">
                  v{healthData?.version || '0.1.0'}
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
                <span className="text-slate-500">Environment:</span>
                <span className="font-mono text-slate-800 dark:text-slate-200">
                  {healthData?.environment || 'development'}
                </span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-500">Retrieval Pipeline:</span>
                <span className="font-semibold text-indigo-600 dark:text-indigo-400">
                  FastEmbed + BM25 + Cross-Encoder
                </span>
              </div>
            </CardContent>
          </Card>

          {/* User Clearance Matrix Card */}
          <Card>
            <CardHeader>
              <div className="flex items-center space-x-2">
                <Lock className="w-4 h-4 text-indigo-500" />
                <CardTitle>Access & Clearance Overview</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-2.5 text-xs">
              <div className="flex items-center justify-between p-2 rounded-lg bg-slate-50 dark:bg-slate-800/50">
                <span className="font-medium text-slate-700 dark:text-slate-300">Department</span>
                <span className="font-semibold text-slate-900 dark:text-slate-100">{departmentName}</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-slate-50 dark:bg-slate-800/50">
                <span className="font-medium text-slate-700 dark:text-slate-300">Assigned Roles</span>
                <div className="flex gap-1">
                  {roles.map((r) => (
                    <Badge key={r} variant="indigo" size="sm">
                      {r}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="flex items-center justify-between p-2 rounded-lg bg-slate-50 dark:bg-slate-800/50">
                <span className="font-medium text-slate-700 dark:text-slate-300">Clearance Level</span>
                <Badge variant={getClearanceVariant(clearanceLevel)} size="sm">
                  Tier {clearanceLevel}
                </Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};
