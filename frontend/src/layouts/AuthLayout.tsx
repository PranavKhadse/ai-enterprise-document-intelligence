import React from 'react';
import { Outlet } from 'react-router-dom';
import { ShieldCheck, Search, FileCheck2, Cpu } from 'lucide-react';

export const AuthLayout: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-slate-900 text-white">
      {/* Left Value Proposition Banner */}
      <div className="md:w-1/2 p-8 lg:p-16 flex flex-col justify-between bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 border-r border-slate-800">
        <div>
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-2xl bg-indigo-600 flex items-center justify-center text-white font-bold text-lg shadow-lg shadow-indigo-500/30">
              EDI
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight">Enterprise Document Intelligence</h1>
              <p className="text-xs text-indigo-300 font-mono">Knowledge & Grounded RAG Platform</p>
            </div>
          </div>

          <div className="mt-12 space-y-6 max-w-lg">
            <h2 className="text-2xl lg:text-3xl font-extrabold tracking-tight text-slate-100">
              Deterministic, grounded AI for critical enterprise knowledge.
            </h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Hybrid retrieval with BM25 & Qdrant vectors, ONNX Cross-Encoder reranking, factual citation verification, and policy conflict detection.
            </p>

            <div className="space-y-4 pt-4">
              <div className="flex items-start space-x-3">
                <div className="p-2 rounded-lg bg-indigo-950/60 border border-indigo-800 text-indigo-400 mt-0.5">
                  <ShieldCheck className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-slate-200">Pre-Retrieval RBAC & Clearance Isolation</h4>
                  <p className="text-xs text-slate-400">Security authorization enforced before search execution.</p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <div className="p-2 rounded-lg bg-indigo-950/60 border border-indigo-800 text-indigo-400 mt-0.5">
                  <Search className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-slate-200">Hybrid Search & Reciprocal Rank Fusion</h4>
                  <p className="text-xs text-slate-400">Dense semantic vectors + BM25 sparse keyword precision.</p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <div className="p-2 rounded-lg bg-indigo-950/60 border border-indigo-800 text-indigo-400 mt-0.5">
                  <FileCheck2 className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-slate-200">Deterministic Citation Verification</h4>
                  <p className="text-xs text-slate-400">Verified document, page, and section provenance for every answer.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="pt-8 text-xs text-slate-500 font-mono flex items-center space-x-2">
          <Cpu className="w-3.5 h-3.5" />
          <span>PostgreSQL · Qdrant Vector DB · FastEmbed · FastAPI</span>
        </div>
      </div>

      {/* Right Form Container */}
      <div className="md:w-1/2 p-8 lg:p-16 flex items-center justify-center bg-slate-950/80">
        <div className="w-full max-w-md">
          <Outlet />
        </div>
      </div>
    </div>
  );
};
