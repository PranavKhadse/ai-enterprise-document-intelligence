import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BotMessageSquare,
  Send,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Copy,
  Check,
  Sliders,
  BookOpen,
  Info,
} from 'lucide-react';
import { ragApi } from '../api/rag';
import { RAGAnswer, Citation, ClaimVerification, GroundingStatus } from '../types/rag';
import { useToast } from '../hooks/useToast';
import { Button } from '../components/common/Button';
import { Input } from '../components/common/Input';
import { Badge } from '../components/common/Badge';
import { Card } from '../components/common/Card';
import { Skeleton } from '../components/common/Skeleton';
import { ErrorState } from '../components/common/ErrorState';
import { formatLatency, formatPercentage } from '../utils/formatters';
import { ApiError } from '../types/api';

export const RAGAssistantPage: React.FC = () => {
  const { success } = useToast();

  const [question, setQuestion] = useState('');
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [copiedAnswer, setCopiedAnswer] = useState(false);

  // Parameter Configuration
  const [temperature, setTemperature] = useState<number>(0.0);
  const [enableVerification, setEnableVerification] = useState<boolean>(true);
  const [topK, setTopK] = useState<number>(10);
  const [showConfig, setShowConfig] = useState(false);

  const [executedQuery, setExecutedQuery] = useState<string>('');
  const [answerHistory, setAnswerHistory] = useState<RAGAnswer[]>([]);

  // Query: RAG Synthesis
  const {
    data: ragResult,
    isLoading: isRagLoading,
    isError: isRagError,
    error: ragError,
  } = useQuery({
    queryKey: ['rag-query', { query: executedQuery, temperature, enable_verification: enableVerification, top_k: topK }],
    queryFn: () =>
      ragApi.query({
        query: executedQuery,
        temperature,
        enable_verification: enableVerification,
        top_k: topK,
      }),
    enabled: !!executedQuery.trim(),
  });

  React.useEffect(() => {
    if (ragResult) {
      setAnswerHistory((prev) => {
        if (prev.some((a) => a.query === ragResult.query && a.answer === ragResult.answer)) {
          return prev;
        }
        return [ragResult, ...prev];
      });
    }
  }, [ragResult]);

  const handleQuery = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (question.trim()) {
      setExecutedQuery(question.trim());
    }
  };

  const copyAnswerText = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedAnswer(true);
    success('Copied to Clipboard', 'Answer text copied.');
    setTimeout(() => setCopiedAnswer(false), 2000);
  };

  const getGroundingBadge = (status: GroundingStatus) => {
    switch (status) {
      case 'fully_grounded':
        return (
          <Badge variant="emerald" size="md">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>FULLY GROUNDED</span>
          </Badge>
        );
      case 'partially_grounded':
        return (
          <Badge variant="amber" size="md">
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>PARTIALLY GROUNDED</span>
          </Badge>
        );
      case 'unsupported':
      case 'refused':
        return (
          <Badge variant="rose" size="md">
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>UNSUPPORTED / REFUSED</span>
          </Badge>
        );
      case 'insufficient_evidence':
        return (
          <Badge variant="slate" size="md">
            <Info className="w-3.5 h-3.5" />
            <span>INSUFFICIENT EVIDENCE</span>
          </Badge>
        );
      default:
        return <Badge variant="slate" size="md">{status}</Badge>;
    }
  };

  const renderAnswerWithClickableCitations = (answerText: string, citations: Citation[]) => {
    // Regex matching [1], [2], etc.
    const parts = answerText.split(/(\[\d+\])/g);

    return (
      <span className="leading-relaxed">
        {parts.map((part, idx) => {
          const match = part.match(/\[(\d+)\]/);
          if (match) {
            const citId = parseInt(match[1], 10);
            const foundCit = citations.find((c) => c.citation_id === citId);

            return (
              <button
                key={idx}
                type="button"
                onClick={() => foundCit && setActiveCitation(foundCit)}
                className="citation-chip inline-flex align-baseline cursor-pointer"
                title={foundCit ? `View Citation #${citId} Evidence` : `Citation #${citId}`}
              >
                [{citId}]
              </button>
            );
          }
          return <span key={idx}>{part}</span>;
        })}
      </span>
    );
  };

  const samplePrompts = [
    'What are the mandatory grounds for immediate employment termination?',
    'Summarize the data encryption standards required under the SOC2 compliance guide.',
    'Explain the expense reimbursement policy for home office equipment.',
  ];

  return (
    <div className="space-y-6 text-left">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Grounded Enterprise AI Assistant
        </h1>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
          Grounded document synthesis with deterministic citation mapping, claim verification, and conflict detection.
        </p>
      </div>

      {/* Query Formulation Input Card */}
      <Card className="p-5 bg-white dark:bg-slate-900">
        <form onSubmit={handleQuery} className="space-y-4">
          <div className="relative">
            <Input
              placeholder="Ask a factual question about corporate policies, engineering SOPs, or compliance requirements..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={isRagLoading}
              className="w-full text-sm py-2.5"
            />
          </div>

          {/* Action Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <div className="flex items-center space-x-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowConfig(!showConfig)}
                leftIcon={<Sliders className="w-3.5 h-3.5" />}
              >
                {showConfig ? 'Hide Parameters' : 'Model Parameters'}
              </Button>
            </div>

            <div className="flex items-center space-x-3">
              <span className="text-[11px] text-slate-400 hidden sm:inline font-mono">
                Press Ctrl+Enter to submit
              </span>
              <Button
                type="submit"
                variant="primary"
                size="md"
                onClick={() => handleQuery()}
                disabled={isRagLoading}
                isLoading={isRagLoading}
                rightIcon={<Send className="w-4 h-4" />}
              >
                Ask Assistant
              </Button>
            </div>
          </div>

          {/* Collapsible Model Parameters Panel */}
          {showConfig && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 text-xs">
              <div>
                <label className="block text-slate-500 font-medium mb-1">
                  Temperature: {temperature}
                </label>
                <input
                  type="range"
                  min={0.0}
                  max={1.0}
                  step={0.1}
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  className="w-full accent-indigo-600"
                />
              </div>

              <div>
                <label className="block text-slate-500 font-medium mb-1">
                  Candidate Chunks (Top K): {topK}
                </label>
                <input
                  type="range"
                  min={5}
                  max={30}
                  step={5}
                  value={topK}
                  onChange={(e) => setTopK(parseInt(e.target.value, 10))}
                  className="w-full accent-indigo-600"
                />
              </div>

              <div className="flex items-center space-x-2 pt-4">
                <input
                  type="checkbox"
                  id="enable-verification-chk"
                  checked={enableVerification}
                  onChange={(e) => setEnableVerification(e.target.checked)}
                  className="rounded text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="enable-verification-chk" className="text-slate-700 dark:text-slate-300 font-medium">
                  Deterministic Verification
                </label>
              </div>
            </div>
          )}
        </form>

        {/* Sample Prompts */}
        {answerHistory.length === 0 && (
          <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400 font-medium">Sample Inquiries:</span>
            {samplePrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => {
                  setQuestion(prompt);
                  setExecutedQuery(prompt);
                }}
                className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-indigo-50 dark:hover:bg-indigo-950 text-xs text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
              >
                {prompt}
              </button>
            ))}
          </div>
        )}
      </Card>

      {/* Loading Skeleton */}
      {isRagLoading && (
        <Card className="p-6 space-y-4">
          <div className="flex justify-between items-center">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-5 w-24" />
          </div>
          <Skeleton className="h-20 w-full" />
          <div className="grid grid-cols-3 gap-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        </Card>
      )}

      {/* Error Message */}
      {isRagError && (
        <ErrorState
          title="RAG Synthesis Failed"
          message={
            (ragError as unknown as ApiError)?.message ||
            'An error occurred while executing the RAG synthesis pipeline.'
          }
          requestId={(ragError as unknown as ApiError)?.requestId}
          onRetry={() => handleQuery()}
        />
      )}

      {/* RAG Answers List */}
      <div className="space-y-8">
        {answerHistory.map((ans: RAGAnswer, ansIndex: number) => (
          <Card key={ansIndex} className="p-6 space-y-6 shadow-md">
            {/* Answer Top Bar */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-4 border-b border-slate-100 dark:border-slate-800">
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <BotMessageSquare className="w-5 h-5 text-indigo-500" />
                  <span className="font-semibold text-sm text-slate-900 dark:text-slate-100">
                    Query: "{ans.query}"
                  </span>
                </div>
              </div>

              <div className="flex items-center space-x-2.5 shrink-0">
                {getGroundingBadge(ans.grounding_status)}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => copyAnswerText(ans.answer)}
                  leftIcon={copiedAnswer ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                >
                  Copy Answer
                </Button>
              </div>
            </div>

            {/* Policy Contradiction Warning (If Detected) */}
            {ans.conflicts_detected && (
              <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/60 border border-amber-300 dark:border-amber-800 text-amber-900 dark:text-amber-200 text-xs flex items-start space-x-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-bold">Contradictory Policy Rules Identified</h4>
                  <p className="mt-0.5 leading-relaxed">
                    {ans.conflict_details ||
                      'The retrieved context contains conflicting clauses across different versions or departments.'}
                  </p>
                </div>
              </div>
            )}

            {/* Grounded Synthetic Answer Text */}
            <div className="p-5 rounded-2xl bg-slate-50/80 dark:bg-slate-950/70 border border-slate-200/80 dark:border-slate-800 text-sm text-slate-800 dark:text-slate-100">
              {renderAnswerWithClickableCitations(ans.answer, ans.citations)}
            </div>

            {/* Claims Verification Breakdown */}
            {ans.claims && ans.claims.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Deterministic Claim Verification Breakdown
                </h4>
                <div className="space-y-2">
                  {ans.claims.map((claim: ClaimVerification, cIdx: number) => (
                    <div
                      key={cIdx}
                      className="p-3 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs space-y-1.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="font-medium text-slate-800 dark:text-slate-200">
                          "{claim.claim_text}"
                        </span>
                        <Badge
                          variant={
                            claim.status === 'supported'
                              ? 'emerald'
                              : claim.status === 'partially_supported'
                              ? 'amber'
                              : 'rose'
                          }
                          size="sm"
                        >
                          {claim.status.replace('_', ' ').toUpperCase()} ({formatPercentage(claim.entailment_score)})
                        </Badge>
                      </div>

                      {claim.unsupported_entities.length > 0 && (
                        <div className="flex items-center space-x-1.5 text-[11px] text-rose-600 dark:text-rose-400">
                          <span>Unsupported entities:</span>
                          {claim.unsupported_entities.map((ent) => (
                            <span key={ent} className="px-1.5 py-0.2 rounded bg-rose-100 dark:bg-rose-950 font-mono">
                              {ent}
                            </span>
                          ))}
                        </div>
                      )}

                      <p className="text-[11px] text-slate-500 italic">{claim.explanation}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Sources & Citations Section */}
            {ans.citations && ans.citations.length > 0 && (
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
                  <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Verified Document Sources ({ans.citations.length})</span>
                </h4>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {ans.citations.map((citation: Citation) => (
                    <div
                      key={citation.citation_id}
                      onClick={() => setActiveCitation(citation)}
                      className="p-3.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-indigo-400 dark:hover:border-indigo-600 transition-all cursor-pointer space-y-2"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-mono font-bold text-indigo-600 dark:text-indigo-400">
                          [{citation.citation_id}] {citation.document_title || 'Document'}
                        </span>
                        {citation.page_number && (
                          <Badge variant="slate" size="sm">
                            Page {citation.page_number}
                          </Badge>
                        )}
                      </div>

                      {citation.section_path && (
                        <p className="text-[11px] text-slate-500 truncate font-mono">
                          {citation.section_path}
                        </p>
                      )}

                      <p className="text-xs text-slate-700 dark:text-slate-300 font-mono line-clamp-2 bg-slate-50 dark:bg-slate-950 p-2 rounded">
                        "{citation.quoted_or_supported_text}"
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Telemetry & Performance Diagnostics */}
            <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <div className="flex items-center space-x-3 font-mono">
                <span>Total Latency: {formatLatency(ans.diagnostics.total_rag_latency_ms)}</span>
                <span>·</span>
                <span>LLM: {formatLatency(ans.diagnostics.llm_latency_ms)}</span>
                <span>·</span>
                <span>Tokens: {ans.diagnostics.prompt_tokens + ans.diagnostics.completion_tokens}</span>
              </div>
              <span className="text-[11px] font-mono text-slate-500">
                Model: {ans.diagnostics.model} ({ans.diagnostics.provider})
              </span>
            </div>
          </Card>
        ))}
      </div>

      {/* Selected Citation Evidence Modal */}
      {activeCitation && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div
            className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm transition-opacity"
            onClick={() => setActiveCitation(null)}
          />
          <div className="flex min-h-full items-center justify-center p-4">
            <div className="relative w-full max-w-xl rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 shadow-2xl text-left space-y-4">
              <div className="flex items-start justify-between pb-3 border-b border-slate-100 dark:border-slate-800">
                <div className="flex items-center space-x-2">
                  <Badge variant="indigo" size="md">
                    Citation [{activeCitation.citation_id}]
                  </Badge>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    {activeCitation.document_title || 'Document Evidence'}
                  </h3>
                </div>
                <button
                  onClick={() => setActiveCitation(null)}
                  className="text-slate-400 hover:text-slate-600 p-1"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-2 text-xs">
                <div className="flex justify-between text-slate-500 font-mono">
                  <span>Page: {activeCitation.page_number ?? '1'}</span>
                  <span>Cross-Encoder Relevance: {formatPercentage(activeCitation.relevance_score)}</span>
                </div>
                {activeCitation.section_path && (
                  <p className="text-indigo-600 dark:text-indigo-400 font-mono text-[11px]">
                    {activeCitation.section_path}
                  </p>
                )}
              </div>

              <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 font-mono text-xs leading-relaxed text-slate-800 dark:text-slate-200 max-h-60 overflow-y-auto">
                "{activeCitation.quoted_or_supported_text}"
              </div>

              <div className="flex justify-end pt-2">
                <Button variant="secondary" size="sm" onClick={() => setActiveCitation(null)}>
                  Close Evidence
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
