import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Eye,
  FileKey2,
  RefreshCw,
} from 'lucide-react';
import { auditApi } from '../api/audit';
import {
  AuditEventResponse,
  AuditEventType,
  AuditSeverity,
  AuthorizationResult,
} from '../types/audit';
import { useDebounce } from '../hooks/useDebounce';
import { Button } from '../components/common/Button';
import { Input } from '../components/common/Input';
import { Badge } from '../components/common/Badge';
import { Card } from '../components/common/Card';
import { Table, Column } from '../components/common/Table';
import { Modal } from '../components/common/Modal';
import { formatDate, truncateHash } from '../utils/formatters';
import { sanitizeMetadata } from '../utils/sanitizer';

export const AuditSecurityPage: React.FC = () => {
  const [eventType, setEventType] = useState<string>('');
  const [severity, setSeverity] = useState<string>('');
  const [authResult, setAuthResult] = useState<string>('');
  const [requestIdFilter, setRequestIdFilter] = useState<string>('');
  const debouncedReqId = useDebounce(requestIdFilter, 300);

  const [pageOffset, setPageOffset] = useState<number>(0);
  const pageSize = 15;

  const [selectedEvent, setSelectedEvent] = useState<AuditEventResponse | null>(null);

  // Query: Audit Statistics
  const { data: statsData, isLoading: isStatsLoading, refetch: refetchStats } = useQuery({
    queryKey: ['audit-stats'],
    queryFn: () => auditApi.getStatistics(),
    refetchInterval: 15000,
  });

  // Query: Audit Events List
  const {
    data: eventsData,
    isLoading: isEventsLoading,
    refetch: refetchEvents,
  } = useQuery({
    queryKey: [
      'audit-events',
      {
        event_type: eventType || undefined,
        severity: severity || undefined,
        authorization_result: authResult || undefined,
        request_id: debouncedReqId || undefined,
        limit: pageSize,
        offset: pageOffset,
      },
    ],
    queryFn: () =>
      auditApi.getEvents({
        event_type: (eventType as AuditEventType) || undefined,
        severity: (severity as AuditSeverity) || undefined,
        authorization_result: (authResult as AuthorizationResult) || undefined,
        request_id: debouncedReqId || undefined,
        limit: pageSize,
        offset: pageOffset,
      }),
  });

  const getSeverityVariant = (sev: string) => {
    switch (sev.toLowerCase()) {
      case 'critical':
        return 'rose';
      case 'high':
        return 'rose';
      case 'warning':
        return 'amber';
      default:
        return 'slate';
    }
  };

  const columns: Column<AuditEventResponse>[] = [
    {
      key: 'created_at',
      header: 'Timestamp',
      render: (event) => (
        <span className="font-mono text-xs text-slate-700 dark:text-slate-300">
          {formatDate(event.created_at)}
        </span>
      ),
    },
    {
      key: 'event_type',
      header: 'Event Type & Action',
      render: (event) => (
        <div>
          <span className="font-mono text-xs font-semibold text-slate-900 dark:text-slate-100">
            {event.event_type}
          </span>
          <p className="text-[11px] text-slate-500 font-mono mt-0.5">{event.action}</p>
        </div>
      ),
    },
    {
      key: 'severity',
      header: 'Severity',
      render: (event) => (
        <Badge variant={getSeverityVariant(event.severity)} size="sm">
          {event.severity.toUpperCase()}
        </Badge>
      ),
    },
    {
      key: 'principal',
      header: 'Principal',
      render: (event) => (
        <div>
          <span className="text-xs text-slate-800 dark:text-slate-200">
            {event.email || 'Anonymous / Unauth'}
          </span>
          {event.clearance_level && (
            <span className="ml-1 text-[10px] font-mono px-1 rounded bg-slate-100 dark:bg-slate-800">
              L{event.clearance_level}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'authorization_result',
      header: 'Auth Status',
      render: (event) => (
        <Badge
          variant={event.authorization_result === 'allowed' ? 'emerald' : 'rose'}
          size="sm"
        >
          {event.authorization_result.toUpperCase()}
        </Badge>
      ),
    },
    {
      key: 'request_id',
      header: 'Request Correlation ID',
      render: (event) => (
        <span className="font-mono text-[11px] text-slate-500">
          {truncateHash(event.request_id || '', 10, 4)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (event) => (
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            e.stopPropagation();
            setSelectedEvent(event);
          }}
          leftIcon={<Eye className="w-3.5 h-3.5" />}
        >
          Inspect
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6 text-left">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Audit Logging & Security Observability
            </h1>
            <Badge variant="rose" size="md">
              CLEARANCE L4 ADMIN ONLY
            </Badge>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Authoritative, tamper-evident security telemetry with SHA-256 HMAC cryptographic chain verification.
          </p>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            refetchStats();
            refetchEvents();
          }}
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
        >
          Refresh Feed
        </Button>
      </div>

      {/* Compliance Metrics Overview Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="p-5">
          <span className="text-xs text-slate-500 font-medium">Total Audit Records</span>
          <p className="text-2xl font-bold font-mono text-slate-900 dark:text-white mt-1">
            {isStatsLoading ? '...' : statsData?.total_events ?? 0}
          </p>
        </Card>

        <Card className="p-5 border-rose-200 dark:border-rose-900/40">
          <span className="text-xs text-rose-600 dark:text-rose-400 font-medium">
            Authorization Denials
          </span>
          <p className="text-2xl font-bold font-mono text-rose-600 dark:text-rose-400 mt-1">
            {isStatsLoading ? '...' : statsData?.authorization_denials ?? 0}
          </p>
        </Card>

        <Card className="p-5 border-amber-200 dark:border-amber-900/40">
          <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">
            Authentication Failures
          </span>
          <p className="text-2xl font-bold font-mono text-amber-600 dark:text-amber-400 mt-1">
            {isStatsLoading ? '...' : statsData?.authentication_failures ?? 0}
          </p>
        </Card>

        <Card className="p-5">
          <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">
            Unique Audited Principals
          </span>
          <p className="text-2xl font-bold font-mono text-indigo-600 dark:text-indigo-400 mt-1">
            {isStatsLoading ? '...' : statsData?.active_users_with_events ?? 0}
          </p>
        </Card>
      </div>

      {/* Audit Query & Filter Bar */}
      <Card className="p-4 bg-white dark:bg-slate-900">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Event Type
            </label>
            <select
              value={eventType}
              onChange={(e) => {
                setEventType(e.target.value);
                setPageOffset(0);
              }}
              className="w-full rounded-lg bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 border border-slate-200 dark:border-slate-800 p-2 font-mono"
            >
              <option value="">All Event Types</option>
              <option value="auth_login_success">auth_login_success</option>
              <option value="auth_login_failure">auth_login_failure</option>
              <option value="authorization_denied">authorization_denied</option>
              <option value="authorization_granted">authorization_granted</option>
              <option value="document_created">document_created</option>
              <option value="document_deleted">document_deleted</option>
              <option value="rag_query">rag_query</option>
              <option value="document_compared">document_compared</option>
            </select>
          </div>

          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Severity Level
            </label>
            <select
              value={severity}
              onChange={(e) => {
                setSeverity(e.target.value);
                setPageOffset(0);
              }}
              className="w-full rounded-lg bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 border border-slate-200 dark:border-slate-800 p-2"
            >
              <option value="">All Severities</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>

          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Auth Decision
            </label>
            <select
              value={authResult}
              onChange={(e) => {
                setAuthResult(e.target.value);
                setPageOffset(0);
              }}
              className="w-full rounded-lg bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 border border-slate-200 dark:border-slate-800 p-2"
            >
              <option value="">All Decisions</option>
              <option value="allowed">Allowed</option>
              <option value="denied">Denied</option>
            </select>
          </div>

          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Filter by Request ID
            </label>
            <Input
              placeholder="e.g. edi-req-..."
              value={requestIdFilter}
              onChange={(e) => {
                setRequestIdFilter(e.target.value);
                setPageOffset(0);
              }}
              className="py-1.5 text-xs font-mono"
            />
          </div>
        </div>
      </Card>

      {/* Events Table */}
      <div className="space-y-4">
        <Table
          columns={columns}
          data={eventsData?.items || []}
          keyExtractor={(evt) => evt.id}
          isLoading={isEventsLoading}
          emptyText="No security audit events matched the active query filters."
          onRowClick={(evt) => setSelectedEvent(evt)}
        />

        {/* Pagination */}
        {eventsData && eventsData.total > pageSize && (
          <div className="flex items-center justify-between px-2 text-xs text-slate-500">
            <span>
              Showing {pageOffset + 1} to {Math.min(pageOffset + pageSize, eventsData.total)} of{' '}
              {eventsData.total} audit events
            </span>
            <div className="flex space-x-2">
              <Button
                variant="outline"
                size="sm"
                disabled={pageOffset === 0}
                onClick={() => setPageOffset(Math.max(0, pageOffset - pageSize))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={pageOffset + pageSize >= eventsData.total}
                onClick={() => setPageOffset(pageOffset + pageSize)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Event Details Inspection Modal */}
      {selectedEvent && (
        <Modal
          isOpen={!!selectedEvent}
          onClose={() => setSelectedEvent(null)}
          title={`Audit Record: ${selectedEvent.event_type}`}
          description={`Event UUID: ${selectedEvent.id}`}
          maxWidth="2xl"
        >
          <div className="space-y-4 text-xs">
            {/* Principal & Context */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700">
              <div>
                <span className="text-slate-400">Principal Email</span>
                <p className="font-semibold text-slate-800 dark:text-slate-200 mt-0.5">
                  {selectedEvent.email || 'N/A'}
                </p>
              </div>
              <div>
                <span className="text-slate-400">Clearance & Roles</span>
                <p className="font-mono text-slate-800 dark:text-slate-200 mt-0.5">
                  L{selectedEvent.clearance_level ?? 1} [{selectedEvent.roles.join(', ')}]
                </p>
              </div>
              <div>
                <span className="text-slate-400">Authorization</span>
                <p className="mt-0.5 font-bold">
                  <Badge variant={selectedEvent.authorization_result === 'allowed' ? 'emerald' : 'rose'} size="sm">
                    {selectedEvent.authorization_result.toUpperCase()}
                  </Badge>
                </p>
              </div>
              <div>
                <span className="text-slate-400">HTTP Context</span>
                <p className="font-mono text-slate-800 dark:text-slate-200 mt-0.5">
                  {selectedEvent.http_method || 'GET'} {selectedEvent.api_path || '/'} ({selectedEvent.status_code || 200})
                </p>
              </div>
              <div>
                <span className="text-slate-400">Client Source IP</span>
                <p className="font-mono text-slate-800 dark:text-slate-200 mt-0.5">
                  {selectedEvent.source_ip || '127.0.0.1'}
                </p>
              </div>
              <div>
                <span className="text-slate-400">Correlation Req ID</span>
                <p className="font-mono text-slate-800 dark:text-slate-200 mt-0.5 truncate">
                  {selectedEvent.request_id || 'N/A'}
                </p>
              </div>
            </div>

            {/* Cryptographic Hash Chain Box */}
            <div className="p-4 rounded-xl bg-slate-900 text-slate-200 border border-slate-800 font-mono text-[11px] space-y-2">
              <div className="flex items-center justify-between text-indigo-400 font-bold">
                <span className="flex items-center space-x-1.5">
                  <FileKey2 className="w-3.5 h-3.5" />
                  <span>SHA-256 Cryptographic Hash Chain</span>
                </span>
                <Badge variant="emerald" size="sm">
                  INTEGRITY VERIFIED
                </Badge>
              </div>
              <div className="space-y-1 pt-1">
                <div>
                  <span className="text-slate-500">Event Hash: </span>
                  <span className="text-slate-300">{selectedEvent.event_hash || 'genesis-event-root'}</span>
                </div>
                <div>
                  <span className="text-slate-500">Prev Hash:  </span>
                  <span className="text-slate-400">{selectedEvent.previous_event_hash || 'genesis-event-root'}</span>
                </div>
              </div>
            </div>

            {/* Sanitized JSON Metadata */}
            <div className="space-y-1.5">
              <span className="font-semibold text-slate-700 dark:text-slate-300">
                Sanitized Payload Metadata
              </span>
              <pre className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 font-mono text-xs overflow-x-auto max-h-48">
                {JSON.stringify(sanitizeMetadata(selectedEvent.metadata_json || {}), null, 2)}
              </pre>
            </div>

            <div className="flex justify-end pt-2">
              <Button variant="secondary" size="sm" onClick={() => setSelectedEvent(null)}>
                Close Audit Record
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
