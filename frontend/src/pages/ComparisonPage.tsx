import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  PlusCircle,
  MinusCircle,
  Edit3,
  CheckCircle2,
  AlertOctagon,
  ArrowRight,
} from 'lucide-react';
import { comparisonApi } from '../api/comparison';
import { documentsApi } from '../api/documents';
import {
  DocumentComparisonResponse,
  AlignedClause,
  DiffType,
  ConflictSeverity,
} from '../types/comparison';
import { useToast } from '../hooks/useToast';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { Card, CardHeader, CardTitle, CardContent } from '../components/common/Card';
import { Tabs } from '../components/common/Tabs';
import { Skeleton } from '../components/common/Skeleton';
import { ErrorState } from '../components/common/ErrorState';
import { formatPercentage, formatLatency } from '../utils/formatters';
import { ApiError } from '../types/api';

export const ComparisonPage: React.FC = () => {
  const { success, error: toastError } = useToast();

  const [inputMode, setInputMode] = useState<'select' | 'text'>('select');

  // Selected Documents
  const [docAId, setDocAId] = useState<string>('');
  const [docBId, setDocBId] = useState<string>('');

  // Ad-hoc text
  const [textA, setTextA] = useState<string>('');
  const [textB, setTextB] = useState<string>('');
  const [titleA, setTitleA] = useState<string>('Document A');
  const [titleB, setTitleB] = useState<string>('Document B');

  // Parameters
  const [similarityThreshold, setSimilarityThreshold] = useState<number>(0.65);
  const [detectConflictsOnly, setDetectConflictsOnly] = useState<boolean>(false);

  // Active diff filter tab
  const [diffFilter, setDiffFilter] = useState<string>('ALL');

  // Query: Documents list for selectors
  const { data: docsList } = useQuery({
    queryKey: ['documents', 'comparison-select'],
    queryFn: () => documentsApi.list({ limit: 100 }),
  });

  // Mutation: Execute Comparison
  const [comparisonResult, setComparisonResult] = useState<DocumentComparisonResponse | null>(null);

  const compareMutation = useMutation({
    mutationFn: async () => {
      if (inputMode === 'select') {
        if (!docAId || !docBId) throw new Error('Please select both Document A and Document B.');
        return comparisonApi.compare({
          document_a_id: docAId,
          document_b_id: docBId,
          similarity_threshold: similarityThreshold,
          detect_conflicts_only: detectConflictsOnly,
        });
      } else {
        if (!textA.trim() || !textB.trim()) {
          throw new Error('Please enter text for both Document A and Document B.');
        }
        return comparisonApi.compare({
          text_a: textA,
          text_b: textB,
          title_a: titleA.trim() || 'Document A',
          title_b: titleB.trim() || 'Document B',
          similarity_threshold: similarityThreshold,
          detect_conflicts_only: detectConflictsOnly,
        });
      }
    },
    onSuccess: (data) => {
      setComparisonResult(data);
      success('Comparison Complete', `Successfully aligned clauses and detected policy differences.`);
    },
    onError: (err: unknown) => {
      const apiErr = err as ApiError;
      toastError('Comparison Failed', apiErr.message, apiErr.requestId);
    },
  });

  const getDiffBadge = (diffType: DiffType) => {
    switch (diffType) {
      case 'added':
        return (
          <Badge variant="emerald" size="sm">
            <PlusCircle className="w-3 h-3" />
            <span>ADDED</span>
          </Badge>
        );
      case 'removed':
        return (
          <Badge variant="rose" size="sm">
            <MinusCircle className="w-3 h-3" />
            <span>REMOVED</span>
          </Badge>
        );
      case 'modified':
        return (
          <Badge variant="indigo" size="sm">
            <Edit3 className="w-3 h-3" />
            <span>MODIFIED</span>
          </Badge>
        );
      case 'conflict':
        return (
          <Badge variant="rose" size="sm">
            <AlertOctagon className="w-3 h-3" />
            <span>CONFLICT</span>
          </Badge>
        );
      case 'unchanged':
        return (
          <Badge variant="slate" size="sm">
            <CheckCircle2 className="w-3 h-3" />
            <span>UNCHANGED</span>
          </Badge>
        );
    }
  };

  const getSeverityBadge = (severity?: ConflictSeverity | null) => {
    if (!severity) return null;
    switch (severity) {
      case 'high':
        return <Badge variant="rose" size="sm">HIGH SEVERITY</Badge>;
      case 'medium':
        return <Badge variant="amber" size="sm">MEDIUM SEVERITY</Badge>;
      case 'low':
        return <Badge variant="slate" size="sm">LOW SEVERITY</Badge>;
    }
  };

  const filteredClauses = comparisonResult?.aligned_clauses.filter((clause: AlignedClause) => {
    if (diffFilter === 'ALL') return true;
    if (diffFilter === 'CONFLICT') return clause.diff_type === 'conflict';
    if (diffFilter === 'MODIFIED') return clause.diff_type === 'modified';
    if (diffFilter === 'ADDED') return clause.diff_type === 'added';
    if (diffFilter === 'REMOVED') return clause.diff_type === 'removed';
    if (diffFilter === 'UNCHANGED') return clause.diff_type === 'unchanged';
    return true;
  });

  return (
    <div className="space-y-6 text-left">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Document Version Diffing & Policy Conflict Intelligence
        </h1>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Extract, align, and compare clauses across corporate policies, version updates, and contracts with deterministic metric diffing.
        </p>
      </div>

      {/* Comparison Setup Card */}
      <Card className="p-6 bg-white dark:bg-slate-900 space-y-5">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Source Selection & Parameters
          </span>
          <div className="flex rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5 text-xs">
            <button
              onClick={() => setInputMode('select')}
              className={`px-3 py-1 rounded-md font-medium transition-colors ${
                inputMode === 'select'
                  ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-sm'
                  : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-100'
              }`}
            >
              Select Ingested Docs
            </button>
            <button
              onClick={() => setInputMode('text')}
              className={`px-3 py-1 rounded-md font-medium transition-colors ${
                inputMode === 'text'
                  ? 'bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-sm'
                  : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-100'
              }`}
            >
              Ad-Hoc Text Input
            </button>
          </div>
        </div>

        {inputMode === 'select' ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                Baseline Document (Document A)
              </label>
              <select
                value={docAId}
                onChange={(e) => setDocAId(e.target.value)}
                className="w-full rounded-xl text-sm bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 border border-slate-200 dark:border-slate-800 p-2.5 focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select Document A...</option>
                {docsList?.items.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title} (v{d.current_version})
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                Updated Document (Document B)
              </label>
              <select
                value={docBId}
                onChange={(e) => setDocBId(e.target.value)}
                className="w-full rounded-xl text-sm bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 border border-slate-200 dark:border-slate-800 p-2.5 focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select Document B...</option>
                {docsList?.items.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title} (v{d.current_version})
                  </option>
                ))}
              </select>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <input
                type="text"
                placeholder="Title A (e.g. Policy 2025)"
                value={titleA}
                onChange={(e) => setTitleA(e.target.value)}
                className="w-full rounded-lg text-xs bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 px-3 py-1.5"
              />
              <textarea
                rows={5}
                placeholder="Paste Document A clause text or markdown here..."
                value={textA}
                onChange={(e) => setTextA(e.target.value)}
                className="w-full rounded-xl text-xs font-mono bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-3 focus:ring-2 focus:ring-indigo-500 resize-none"
              />
            </div>

            <div className="space-y-2">
              <input
                type="text"
                placeholder="Title B (e.g. Policy 2026)"
                value={titleB}
                onChange={(e) => setTitleB(e.target.value)}
                className="w-full rounded-lg text-xs bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 px-3 py-1.5"
              />
              <textarea
                rows={5}
                placeholder="Paste Document B clause text or markdown here..."
                value={textB}
                onChange={(e) => setTextB(e.target.value)}
                className="w-full rounded-xl text-xs font-mono bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 p-3 focus:ring-2 focus:ring-indigo-500 resize-none"
              />
            </div>
          </div>
        )}

        {/* Sliders & Triggers */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-2">
          <div className="flex items-center space-x-6 text-xs text-slate-600 dark:text-slate-400">
            <div className="flex items-center space-x-2">
              <span>Similarity Threshold: {similarityThreshold}</span>
              <input
                type="range"
                min={0.3}
                max={0.95}
                step={0.05}
                value={similarityThreshold}
                onChange={(e) => setSimilarityThreshold(parseFloat(e.target.value))}
                className="accent-indigo-600"
              />
            </div>

            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="conflicts-only-chk"
                checked={detectConflictsOnly}
                onChange={(e) => setDetectConflictsOnly(e.target.checked)}
                className="rounded text-indigo-600 focus:ring-indigo-500"
              />
              <label htmlFor="conflicts-only-chk" className="cursor-pointer">
                Conflicts Only
              </label>
            </div>
          </div>

          <Button
            variant="primary"
            size="md"
            onClick={() => compareMutation.mutate()}
            isLoading={compareMutation.isPending}
            rightIcon={<ArrowRight className="w-4 h-4" />}
          >
            Execute Comparison
          </Button>
        </div>
      </Card>

      {/* Loading Skeleton */}
      {compareMutation.isPending && (
        <Card className="p-6 space-y-4">
          <Skeleton className="h-6 w-1/3" />
          <div className="grid grid-cols-6 gap-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
          <Skeleton className="h-32 w-full" />
        </Card>
      )}

      {/* Error Message */}
      {compareMutation.isError && (
        <ErrorState
          title="Comparison Failed"
          message={(compareMutation.error as ApiError)?.message || 'Failed to compare documents.'}
          requestId={(compareMutation.error as ApiError)?.requestId}
        />
      )}

      {/* Comparison Results */}
      {comparisonResult && (
        <div className="space-y-6">
          {/* Executive Overview Card */}
          <Card className="p-6 bg-gradient-to-br from-white via-indigo-50/20 to-white dark:from-slate-900 dark:via-indigo-950/20 dark:to-slate-900 border-indigo-200 dark:border-indigo-900/60 shadow-md">
            <CardHeader className="px-0 pt-0">
              <div className="space-y-1">
                <Badge variant="indigo" size="md">
                  EXECUTIVE SUMMARY
                </Badge>
                <CardTitle className="text-lg">
                  {comparisonResult.title_a} vs {comparisonResult.title_b}
                </CardTitle>
              </div>
              <div className="text-right">
                <span className="text-xs text-slate-400 block font-mono">Divergence Index</span>
                <span className="text-2xl font-bold font-mono text-indigo-600 dark:text-indigo-400">
                  {(comparisonResult.statistics.divergence_index * 100).toFixed(1)}%
                </span>
              </div>
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <p className="text-sm text-slate-800 dark:text-slate-200 leading-relaxed">
                {comparisonResult.executive_summary}
              </p>
            </CardContent>
          </Card>

          {/* Numerical Diff Statistics Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-center">
              <span className="text-xs text-slate-400 font-medium">Total Clauses</span>
              <p className="text-xl font-bold font-mono text-slate-900 dark:text-white mt-1">
                {comparisonResult.statistics.total_clauses_a} / {comparisonResult.statistics.total_clauses_b}
              </p>
            </div>

            <div className="p-4 rounded-xl bg-emerald-50/70 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-center">
              <span className="text-xs text-emerald-700 dark:text-emerald-300 font-medium">+ Added</span>
              <p className="text-xl font-bold font-mono text-emerald-700 dark:text-emerald-300 mt-1">
                {comparisonResult.statistics.added_clauses_count}
              </p>
            </div>

            <div className="p-4 rounded-xl bg-rose-50/70 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-center">
              <span className="text-xs text-rose-700 dark:text-rose-300 font-medium">- Removed</span>
              <p className="text-xl font-bold font-mono text-rose-700 dark:text-rose-300 mt-1">
                {comparisonResult.statistics.removed_clauses_count}
              </p>
            </div>

            <div className="p-4 rounded-xl bg-indigo-50/70 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800 text-center">
              <span className="text-xs text-indigo-700 dark:text-indigo-300 font-medium">~ Modified</span>
              <p className="text-xl font-bold font-mono text-indigo-700 dark:text-indigo-300 mt-1">
                {comparisonResult.statistics.modified_clauses_count}
              </p>
            </div>

            <div className="p-4 rounded-xl bg-rose-100/70 dark:bg-rose-950/80 border border-rose-300 dark:border-rose-800 text-center">
              <span className="text-xs text-rose-800 dark:text-rose-200 font-bold">! Conflicts</span>
              <p className="text-xl font-bold font-mono text-rose-800 dark:text-rose-200 mt-1">
                {comparisonResult.statistics.conflicting_clauses_count}
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-100/70 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700 text-center">
              <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">= Unchanged</span>
              <p className="text-xl font-bold font-mono text-slate-700 dark:text-slate-300 mt-1">
                {comparisonResult.statistics.unchanged_clauses_count}
              </p>
            </div>
          </div>

          {/* Filter Tabs */}
          <Tabs
            activeTab={diffFilter}
            onChange={setDiffFilter}
            tabs={[
              { id: 'ALL', label: 'All Aligned', count: comparisonResult.aligned_clauses.length },
              { id: 'CONFLICT', label: 'Conflicts', count: comparisonResult.statistics.conflicting_clauses_count },
              { id: 'MODIFIED', label: 'Modified', count: comparisonResult.statistics.modified_clauses_count },
              { id: 'ADDED', label: 'Added', count: comparisonResult.statistics.added_clauses_count },
              { id: 'REMOVED', label: 'Removed', count: comparisonResult.statistics.removed_clauses_count },
              { id: 'UNCHANGED', label: 'Unchanged', count: comparisonResult.statistics.unchanged_clauses_count },
            ]}
          />

          {/* Aligned Clauses Cards List */}
          <div className="space-y-4">
            {filteredClauses?.map((clause: AlignedClause) => (
              <Card key={clause.clause_id} className="p-6 space-y-4 shadow-sm">
                {/* Clause Header */}
                <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-100 dark:border-slate-800 text-xs">
                  <div className="flex items-center space-x-2">
                    {getDiffBadge(clause.diff_type)}
                    {getSeverityBadge(clause.conflict_severity)}
                    <span className="font-mono text-slate-400 text-[11px]">ID: {clause.clause_id}</span>
                  </div>

                  <div className="flex items-center space-x-3 text-slate-500 font-mono text-[11px]">
                    <span>Similarity: {formatPercentage(clause.similarity_score)}</span>
                    {clause.alignment_method && <span>({clause.alignment_method})</span>}
                  </div>
                </div>

                {/* Semantic Change Explanation */}
                {clause.change_summary && (
                  <p className="text-xs text-indigo-700 dark:text-indigo-300 bg-indigo-50/60 dark:bg-indigo-950/40 p-2.5 rounded-lg border border-indigo-100 dark:border-indigo-900/50">
                    <span className="font-semibold">Semantic Summary: </span>
                    {clause.change_summary}
                  </p>
                )}

                {/* Side-by-Side Clause Comparison */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Document A Clause */}
                  <div className="space-y-1.5 p-4 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs">
                    <div className="flex justify-between items-center text-slate-400 font-mono text-[11px]">
                      <span>{comparisonResult.title_a}</span>
                      {clause.page_a && <span>Page {clause.page_a}</span>}
                    </div>
                    {clause.section_path_a && (
                      <p className="text-[11px] text-slate-500 font-mono">{clause.section_path_a}</p>
                    )}
                    <p className="text-slate-800 dark:text-slate-200 font-mono leading-relaxed mt-2 whitespace-pre-wrap">
                      {clause.text_a || <span className="italic text-slate-400">[No clause in Document A]</span>}
                    </p>
                  </div>

                  {/* Document B Clause */}
                  <div className="space-y-1.5 p-4 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs">
                    <div className="flex justify-between items-center text-slate-400 font-mono text-[11px]">
                      <span>{comparisonResult.title_b}</span>
                      {clause.page_b && <span>Page {clause.page_b}</span>}
                    </div>
                    {clause.section_path_b && (
                      <p className="text-[11px] text-slate-500 font-mono">{clause.section_path_b}</p>
                    )}
                    <p className="text-slate-800 dark:text-slate-200 font-mono leading-relaxed mt-2 whitespace-pre-wrap">
                      {clause.text_b || <span className="italic text-slate-400">[No clause in Document B]</span>}
                    </p>
                  </div>
                </div>

                {/* Entity & Metric Variances Table */}
                {clause.entity_diffs && clause.entity_diffs.length > 0 && (
                  <div className="space-y-2 pt-2">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                      Entity & Metric Divergences
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {clause.entity_diffs.map((diff, edIdx) => (
                        <div
                          key={edIdx}
                          className="p-2.5 rounded-lg bg-amber-50/50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/60 text-xs space-y-1"
                        >
                          <div className="flex justify-between font-mono text-[11px] text-amber-800 dark:text-amber-300">
                            <span className="uppercase">{diff.entity_type}</span>
                            {diff.is_divergent && <span className="font-bold">DIVERGENT</span>}
                          </div>
                          <div className="flex justify-between text-slate-700 dark:text-slate-300 text-[11px]">
                            <span>A: {diff.value_a || '—'}</span>
                            <span>B: {diff.value_b || '—'}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            ))}
          </div>

          {/* Telemetry Diagnostics Footer */}
          <div className="p-3.5 rounded-xl bg-slate-100/70 dark:bg-slate-900 text-xs text-slate-500 font-mono flex justify-between">
            <span>Comparison Latency: {formatLatency(comparisonResult.diagnostics.total_latency_ms)}</span>
            <span>Aligned Pairs: {comparisonResult.diagnostics.aligned_pairs}</span>
          </div>
        </div>
      )}
    </div>
  );
};
