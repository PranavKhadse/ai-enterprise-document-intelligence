"""
Phase 7 End-to-End Orchestrator: Reranking, Compression, and Evidence Selection Pipeline.
Coordinates candidate window slicing, ONNX Cross-Encoder inference, deterministic compression,
diversity filtering, and Phase 8 RAG Context generation with degraded-mode fault tolerance.
"""
import asyncio
import time
from typing import List, Optional
import tiktoken
from backend.app.core.config import settings
from backend.app.schemas.reranking import (
    RAGContextItem,
    RerankedChunk,
    RerankedRetrievalResponse,
    RerankerConfig,
    RerankingDiagnostics,
)
from backend.app.schemas.retrieval import HybridRetrievalResponse, ScoredChunk
from backend.app.services.context_compressor import ContextCompressionService, context_compressor
from backend.app.services.cross_encoder import CrossEncoderRerankerService, cross_encoder_service
from backend.app.services.evidence_selector import EvidenceSelector, evidence_selector


class RerankingPipelineService:
    """
    Unified Phase 7 orchestration service transforming Phase 6 ScoredChunks
    into high-precision, compressed, citation-ready RAG evidence.
    """

    def __init__(
        self,
        reranker: Optional[CrossEncoderRerankerService] = None,
        compressor: Optional[ContextCompressionService] = None,
        selector: Optional[EvidenceSelector] = None,
    ):
        self.reranker = reranker or cross_encoder_service
        self.compressor = compressor or context_compressor
        self.selector = selector or evidence_selector

    async def process(
        self,
        query: str,
        retrieval_response: HybridRetrievalResponse,
        top_k: Optional[int] = None,
        candidate_window_size: Optional[int] = None,
        max_context_tokens: Optional[int] = None,
    ) -> RerankedRetrievalResponse:
        """
        Executes the complete Phase 7 pipeline on the candidate response from Phase 6.
        """
        start_total = time.perf_counter()
        warnings: List[str] = []
        degraded_mode = False

        candidates = retrieval_response.results
        k = top_k or self.reranker.config.top_k
        window_size = candidate_window_size or self.reranker.config.candidate_window_size
        timeout_sec = self.reranker.config.timeout_seconds

        # 0. Handle Empty Input Candidates
        if not candidates or not query or not query.strip():
            total_lat = (time.perf_counter() - start_total) * 1000.0
            return RerankedRetrievalResponse(
                results=[],
                context_items=[],
                diagnostics=RerankingDiagnostics(
                    query=query or "",
                    reranker_model=self.reranker.config.model_name,
                    total_phase7_latency_ms=total_lat,
                    phase6_diagnostics=retrieval_response.diagnostics,
                ),
            )

        # 1. Step 1: Cross-Encoder Reranking
        t_rerank_start = time.perf_counter()
        reranked_chunks: List[RerankedChunk] = []

        try:
            # Execute reranker inside thread pool with strict timeout guard
            reranked_chunks = await asyncio.wait_for(
                asyncio.to_thread(
                    self.reranker.rerank_sync,
                    query,
                    candidates,
                    top_k=k,
                    candidate_window_size=window_size,
                ),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            degraded_mode = True
            warnings.append(
                f"Cross-encoder reranking timed out after {timeout_sec}s. Falling back to Phase 6 ranking."
            )
        except Exception as e:
            degraded_mode = True
            warnings.append(
                f"Cross-encoder reranking failed ({str(e)}). Falling back to Phase 6 ranking."
            )

        # Fallback: Construct RerankedChunks directly from Phase 6 candidate order
        if degraded_mode or not reranked_chunks:
            tok_encoder = tiktoken.get_encoding("cl100k_base")
            reranked_chunks = []
            for rank, chunk in enumerate(candidates[:k], start=1):
                orig_tokens = len(tok_encoder.encode(chunk.content, disallowed_special=()))
                reranked_chunks.append(
                    RerankedChunk(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        version_id=chunk.version_id,
                        department_id=chunk.department_id,
                        content=chunk.content,
                        compressed_content=chunk.content,
                        page_number=chunk.page_number,
                        section_path=chunk.section_path,
                        is_table=chunk.metadata.get("is_table", False),
                        reranker_raw_score=chunk.final_score,
                        reranker_score=chunk.final_score,
                        reranker_rank=rank,
                        rank_delta=0,
                        initial_retrieval_score=chunk.final_score,
                        initial_retrieval_rank=rank,
                        dense_score=chunk.dense_score,
                        sparse_score=chunk.sparse_score,
                        dense_rank=chunk.dense_rank,
                        sparse_rank=chunk.sparse_rank,
                        rrf_score=chunk.rrf_score,
                        retrieval_methods=chunk.retrieval_methods,
                        original_token_count=orig_tokens,
                        compressed_token_count=orig_tokens,
                        compression_ratio=1.0,
                        metadata=chunk.metadata,
                    )
                )

        reranker_latency = (time.perf_counter() - t_rerank_start) * 1000.0

        # 2. Step 2: Deterministic Context Compression
        t_compress_start = time.perf_counter()
        try:
            compressed_chunks = self.compressor.compress_all(query, reranked_chunks)
        except Exception as e:
            warnings.append(f"Context compression failed ({str(e)}). Falling back to uncompressed text.")
            compressed_chunks = reranked_chunks
        compression_latency = (time.perf_counter() - t_compress_start) * 1000.0

        # 3. Step 3: Evidence Selection & Token Budget Allocator
        t_select_start = time.perf_counter()
        try:
            final_chunks, context_items = self.selector.select_evidence(
                compressed_chunks,
                max_context_tokens=max_context_tokens,
            )
        except Exception as e:
            warnings.append(f"Evidence selection failed ({str(e)}). Returning unpruned candidates.")
            final_chunks = compressed_chunks
            context_items = []
        selection_latency = (time.perf_counter() - t_select_start) * 1000.0

        total_latency = (time.perf_counter() - start_total) * 1000.0

        # 4. Diagnostics Summary
        orig_tokens_total = sum(c.original_token_count for c in final_chunks)
        comp_tokens_total = sum(c.compressed_token_count for c in final_chunks)
        comp_ratio = (
            round(float(comp_tokens_total / max(orig_tokens_total, 1)), 3)
            if orig_tokens_total > 0
            else 1.0
        )

        diagnostics = RerankingDiagnostics(
            query=query,
            reranker_model=self.reranker.config.model_name,
            reranker_latency_ms=round(reranker_latency, 2),
            compression_latency_ms=round(compression_latency, 2),
            selection_latency_ms=round(selection_latency, 2),
            total_phase7_latency_ms=round(total_latency, 2),
            input_candidates_count=len(candidates),
            candidate_window_size=min(len(candidates), window_size),
            reranked_candidates_count=len(reranked_chunks),
            final_evidence_count=len(final_chunks),
            total_original_tokens=orig_tokens_total,
            total_compressed_tokens=comp_tokens_total,
            overall_compression_ratio=comp_ratio,
            degraded_mode=degraded_mode,
            warnings=warnings,
            phase6_diagnostics=retrieval_response.diagnostics,
        )

        return RerankedRetrievalResponse(
            results=final_chunks,
            context_items=context_items,
            diagnostics=diagnostics,
        )


# Global Phase 7 pipeline singleton
reranking_pipeline = RerankingPipelineService()
