import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Search as SearchIcon,
  SlidersHorizontal,
  Clock,
  Sparkles,
  Database,
  ArrowRight,
} from 'lucide-react';
import { searchApi } from '../api/search';
import { FusionStrategy, ScoredChunk } from '../types/search';
import { Button } from '../components/common/Button';
import { Input } from '../components/common/Input';
import { Badge } from '../components/common/Badge';
import { Card } from '../components/common/Card';
import { Skeleton } from '../components/common/Skeleton';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { formatLatency } from '../utils/formatters';

export const SearchPage: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [executedQuery, setExecutedQuery] = useState('');
  const [strategy, setStrategy] = useState<FusionStrategy>('rrf');
  const [topK, setTopK] = useState<number>(10);

  const {
    data: searchResponse,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['hybrid-search', { query: executedQuery, strategy, topK }],
    queryFn: () =>
      searchApi.search({
        query: executedQuery,
        strategy,
        top_k: topK,
      }),
    enabled: !!executedQuery.trim(),
  });

  const handleSearch = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (searchTerm.trim()) {
      setExecutedQuery(searchTerm.trim());
    }
  };

  const sampleQueries = [
    'Termination notice requirements and severance policy',
    'Data retention compliance guidelines under SOC2',
    'Remote work expense reimbursement limits',
    'Incident response escalation matrix',
  ];

  return (
    <div className="space-y-6 text-left">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Hybrid Lexical & Semantic Search
        </h1>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Parallel vector retrieval (FastEmbed + Qdrant) combined with BM25 inverted lexical search via Reciprocal Rank Fusion.
        </p>
      </div>

      {/* Main Search Input & Parameter Controls */}
      <Card className="p-4 bg-white dark:bg-slate-900">
        <form onSubmit={handleSearch} className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-2.5">
            <div className="relative flex-1">
              <Input
                placeholder="Enter semantic questions, error codes, clauses, or policy queries..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                leftIcon={<SearchIcon className="w-4 h-4 text-indigo-500" />}
                className="w-full text-base py-2.5"
                autoFocus
              />
            </div>
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={!searchTerm.trim() || isLoading}
              isLoading={isLoading}
              rightIcon={<ArrowRight className="w-4 h-4" />}
            >
              Search
            </Button>
          </div>

          {/* Search Configuration Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 text-xs text-slate-500">
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-1.5">
                <SlidersHorizontal className="w-3.5 h-3.5 text-slate-400" />
                <span>Strategy:</span>
                <select
                  value={strategy}
                  onChange={(e) => setStrategy(e.target.value as FusionStrategy)}
                  className="bg-slate-100 dark:bg-slate-800 border-none rounded px-2 py-0.5 text-xs text-slate-800 dark:text-slate-200 cursor-pointer font-medium"
                >
                  <option value="rrf">Reciprocal Rank Fusion (RRF)</option>
                  <option value="weighted_score">Weighted Score</option>
                  <option value="dense_only">Dense Vectors Only</option>
                  <option value="sparse_only">BM25 Sparse Only</option>
                </select>
              </div>

              <div className="flex items-center space-x-1.5">
                <span>Top K:</span>
                <select
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  className="bg-slate-100 dark:bg-slate-800 border-none rounded px-2 py-0.5 text-xs text-slate-800 dark:text-slate-200 cursor-pointer font-medium"
                >
                  <option value={5}>5 passages</option>
                  <option value={10}>10 passages</option>
                  <option value={20}>20 passages</option>
                  <option value={50}>50 passages</option>
                </select>
              </div>
            </div>

            {/* Sample Queries Chips */}
            <div className="hidden lg:flex items-center space-x-1.5 overflow-x-auto">
              <span className="text-slate-400">Suggestions:</span>
              {sampleQueries.slice(0, 2).map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => {
                    setSearchTerm(q);
                    setExecutedQuery(q);
                  }}
                  className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 hover:bg-indigo-50 dark:hover:bg-indigo-950 text-[11px] text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors truncate max-w-[200px]"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </form>
      </Card>

      {/* Diagnostics Telemetry Banner (If Search Executed) */}
      {searchResponse && (
        <div className="p-3.5 rounded-xl bg-slate-100/70 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-1 font-mono text-slate-600 dark:text-slate-300">
              <Clock className="w-3.5 h-3.5 text-indigo-500" />
              <span>Latency: {formatLatency(searchResponse.diagnostics.total_latency_ms)}</span>
            </div>
            <span className="text-slate-300 dark:text-slate-700">|</span>
            <div className="flex items-center space-x-1 font-mono text-slate-600 dark:text-slate-300">
              <Sparkles className="w-3.5 h-3.5 text-emerald-500" />
              <span>Type: {searchResponse.diagnostics.query_type}</span>
            </div>
            <span className="text-slate-300 dark:text-slate-700">|</span>
            <div className="flex items-center space-x-1 font-mono text-slate-600 dark:text-slate-300">
              <Database className="w-3.5 h-3.5 text-purple-500" />
              <span>
                Pools: Qdrant ({searchResponse.diagnostics.dense_candidates_count}) + BM25 (
                {searchResponse.diagnostics.sparse_candidates_count})
              </span>
            </div>
          </div>

          <Badge variant="indigo" size="sm">
            {searchResponse.results.length} Candidates Ranked
          </Badge>
        </div>
      )}

      {/* Results View */}
      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="p-6 space-y-3">
              <div className="flex justify-between">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-4 w-16" />
              </div>
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-3 w-1/4" />
            </Card>
          ))}
        </div>
      ) : isError ? (
        <ErrorState
          title="Search Query Failed"
          message={(error as Error)?.message || 'Failed to execute hybrid search query.'}
          onRetry={() => refetch()}
        />
      ) : searchResponse?.results.length === 0 ? (
        <EmptyState
          icon={<SearchIcon className="w-6 h-6 text-slate-400" />}
          title="No Passages Found"
          description={`No candidate chunks matched query '${executedQuery}'. Try modifying your search terms or changing the fusion strategy.`}
        />
      ) : searchResponse ? (
        <div className="space-y-4">
          {searchResponse.results.map((chunk: ScoredChunk, index: number) => (
            <Card key={chunk.chunk_id} hoverEffect className="p-6 space-y-3">
              {/* Header */}
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="w-5 h-5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-mono text-xs flex items-center justify-center font-bold">
                      {index + 1}
                    </span>
                    <span className="text-sm font-semibold text-slate-900 dark:text-white">
                      {chunk.section_path || 'General Passage'}
                    </span>
                    {chunk.page_number && (
                      <Badge variant="slate" size="sm">
                        Page {chunk.page_number}
                      </Badge>
                    )}
                  </div>
                  <p className="text-[11px] font-mono text-slate-400">
                    Chunk ID: {chunk.chunk_id} · Doc ID: {chunk.document_id}
                  </p>
                </div>

                <div className="text-right shrink-0">
                  <div className="flex items-center space-x-1.5">
                    <span className="text-xs text-slate-400 font-mono">Score</span>
                    <Badge variant="indigo" size="md">
                      {chunk.final_score.toFixed(4)}
                    </Badge>
                  </div>
                </div>
              </div>

              {/* Passage Content */}
              <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800 font-mono text-xs leading-relaxed text-slate-800 dark:text-slate-200">
                {chunk.content}
              </div>

              {/* Retrieval Provenance & Explanation */}
              <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
                <div className="flex items-center space-x-2">
                  <span className="text-slate-400">Sources:</span>
                  {chunk.retrieval_methods.map((method) => (
                    <Badge key={method} variant={method === 'dense' ? 'purple' : 'emerald'} size="sm">
                      {method.toUpperCase()}
                    </Badge>
                  ))}
                  {chunk.dense_rank && (
                    <span className="text-[11px] font-mono text-slate-500">
                      Dense Rank: #{chunk.dense_rank}
                    </span>
                  )}
                  {chunk.sparse_rank && (
                    <span className="text-[11px] font-mono text-slate-500">
                      Sparse Rank: #{chunk.sparse_rank}
                    </span>
                  )}
                </div>

                <p className="text-[11px] text-slate-500 italic max-w-md truncate">
                  {chunk.explanation}
                </p>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        /* Initial Landing State */
        <div className="p-12 text-center rounded-2xl border border-dashed border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/40">
          <div className="w-12 h-12 rounded-full bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mx-auto mb-3">
            <SearchIcon className="w-6 h-6" />
          </div>
          <h3 className="text-base font-semibold text-slate-900 dark:text-white">
            Enterprise Knowledge Search
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto mt-1">
            Type any query above to trigger parallel Qdrant vector similarity and BM25 lexical candidate retrieval.
          </p>

          <div className="mt-6 flex flex-wrap justify-center gap-2 max-w-lg mx-auto">
            {sampleQueries.map((q) => (
              <Button
                key={q}
                variant="outline"
                size="sm"
                onClick={() => {
                  setSearchTerm(q);
                  setExecutedQuery(q);
                }}
              >
                {q}
              </Button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
