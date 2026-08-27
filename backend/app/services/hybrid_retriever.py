"""
Hybrid Retrieval and Rank Fusion Service.
Orchestrates parallel dense vector search (Qdrant) and sparse inverted index search (BM25)
with query-aware adaptive parameter tuning, rank/score fusion, and pre-retrieval RBAC filtering.
"""
import asyncio
import time
from typing import List, Optional
import uuid
from backend.app.core.config import settings
from backend.app.schemas.bm25 import BM25SearchResult
from backend.app.schemas.embedding import VectorSearchResult
from backend.app.schemas.retrieval import (
    FusionStrategy,
    HybridRetrievalResponse,
    QueryType,
    RetrievalDiagnostics,
    RetrievalFilter,
)
from backend.app.services.bm25 import BM25IndexService, bm25_service
from backend.app.services.embedding import EmbeddingService, embedding_service
from backend.app.services.fusion import FusionEngine, fusion_engine
from backend.app.services.query_analyzer import QueryAnalyzer, query_analyzer
from backend.app.services.vector_store import VectorStoreService, vector_store_service


class HybridRetrievalError(Exception):
    """Base exception for hybrid retrieval pipeline failures."""
    pass


class HybridRetrievalService:
    """
    Coordinates multi-modal candidate generation and rank fusion with robust degraded-mode fallbacks.
    """

    def __init__(
        self,
        vector_service: Optional[VectorStoreService] = None,
        embed_service: Optional[EmbeddingService] = None,
        sparse_service: Optional[BM25IndexService] = None,
        analyzer: Optional[QueryAnalyzer] = None,
        fusion: Optional[FusionEngine] = None,
    ):
        self.vector_service = vector_service or vector_store_service
        self.embed_service = embed_service or embedding_service
        self.sparse_service = sparse_service or bm25_service
        self.analyzer = analyzer or query_analyzer
        self.fusion = fusion or fusion_engine

    def _execute_dense_search(
        self,
        query: str,
        limit: int,
        filter_spec: Optional[RetrievalFilter] = None,
    ) -> List[VectorSearchResult]:
        """
        Synchronous helper for embedding generation and Qdrant vector retrieval.
        """
        query_vector = self.embed_service.embed_text(query)
        doc_id = filter_spec.document_id if filter_spec else None
        ver_id = filter_spec.version_id if filter_spec else None
        dept_id = filter_spec.department_id if filter_spec else None
        allowed_depts = filter_spec.allowed_department_ids if filter_spec else None
        allowed_docs = filter_spec.allowed_document_ids if filter_spec else None
        max_clearance = filter_spec.max_clearance_level if filter_spec else None

        return self.vector_service.search_vectors(
            query_vector=query_vector,
            limit=limit,
            document_id=doc_id,
            version_id=ver_id,
            department_id=dept_id,
            allowed_department_ids=allowed_depts,
            allowed_document_ids=allowed_docs,
            max_clearance_level=max_clearance,
        )

    def _execute_sparse_search(
        self,
        query: str,
        limit: int,
        filter_spec: Optional[RetrievalFilter] = None,
    ) -> List[BM25SearchResult]:
        """
        Synchronous helper for BM25 inverted index retrieval.
        """
        doc_id = filter_spec.document_id if filter_spec else None
        ver_id = filter_spec.version_id if filter_spec else None
        dept_id = filter_spec.department_id if filter_spec else None
        allowed_depts = filter_spec.allowed_department_ids if filter_spec else None
        allowed_docs = filter_spec.allowed_document_ids if filter_spec else None
        max_clearance = filter_spec.max_clearance_level if filter_spec else None

        return self.sparse_service.search(
            query=query,
            limit=limit,
            document_id=doc_id,
            version_id=ver_id,
            department_id=dept_id,
            allowed_department_ids=allowed_depts,
            allowed_document_ids=allowed_docs,
            max_clearance_level=max_clearance,
        )

    async def retrieve(
        self,
        query: str,
        filter: Optional[RetrievalFilter] = None,
        strategy: Optional[FusionStrategy] = None,
        final_top_k: Optional[int] = None,
        dense_top_k: Optional[int] = None,
        sparse_top_k: Optional[int] = None,
        rrf_k: Optional[int] = None,
        dense_weight: Optional[float] = None,
        sparse_weight: Optional[float] = None,
        enable_query_aware_tuning: Optional[bool] = None,
    ) -> HybridRetrievalResponse:
        """
        Executes parallel hybrid retrieval across Qdrant and BM25 with query-aware tuning and fusion.
        """
        start_total = time.perf_counter()

        # Handle empty/whitespace query cleanly
        if not query or not query.strip():
            total_latency = (time.perf_counter() - start_total) * 1000.0
            return HybridRetrievalResponse(
                results=[],
                diagnostics=RetrievalDiagnostics(
                    query=query or "",
                    query_type=QueryType.KEYWORD_SEARCH.value,
                    dense_latency_ms=0.0,
                    sparse_latency_ms=0.0,
                    fusion_latency_ms=0.0,
                    total_latency_ms=total_latency,
                    dense_candidates_count=0,
                    sparse_candidates_count=0,
                    merged_candidates_count=0,
                    fusion_strategy=strategy.value if strategy else settings.HYBRID_FUSION_STRATEGY,
                    degraded_mode=False,
                ),
            )

        # 1. Query Analysis & Intent Classification
        q_type, auto_dense_w, auto_sparse_w, pool_mult = self.analyzer.analyze_query(query)
        is_tuning_enabled = (
            enable_query_aware_tuning
            if enable_query_aware_tuning is not None
            else settings.HYBRID_ENABLE_QUERY_AWARE_TUNING
        )

        # Determine weights
        if is_tuning_enabled and dense_weight is None and sparse_weight is None:
            w_dense = auto_dense_w
            w_sparse = auto_sparse_w
        else:
            w_dense = dense_weight if dense_weight is not None else settings.HYBRID_DENSE_WEIGHT
            w_sparse = sparse_weight if sparse_weight is not None else settings.HYBRID_SPARSE_WEIGHT

        # Determine candidate pool depths
        d_k = dense_top_k or settings.HYBRID_DENSE_TOP_K
        s_k = sparse_top_k or settings.HYBRID_SPARSE_TOP_K
        if is_tuning_enabled:
            if q_type == QueryType.EXACT_IDENTIFIER:
                s_k = int(s_k * pool_mult)
            elif q_type == QueryType.SEMANTIC_QUESTION:
                d_k = int(d_k * pool_mult)

        f_k = final_top_k or settings.HYBRID_FINAL_TOP_K
        k_val = rrf_k or settings.HYBRID_RRF_K
        chosen_strategy = strategy or FusionStrategy(settings.HYBRID_FUSION_STRATEGY)

        # 2. Parallel Candidate Retrieval via asyncio.gather
        dense_candidates: List[VectorSearchResult] = []
        sparse_candidates: List[BM25SearchResult] = []
        warnings: List[str] = []
        degraded_mode = False

        dense_start = time.perf_counter()
        sparse_start = time.perf_counter()
        dense_latency = 0.0
        sparse_latency = 0.0

        async def run_dense():
            nonlocal dense_latency
            t0 = time.perf_counter()
            res = await asyncio.to_thread(self._execute_dense_search, query, d_k, filter)
            dense_latency = (time.perf_counter() - t0) * 1000.0
            return res

        async def run_sparse():
            nonlocal sparse_latency
            t0 = time.perf_counter()
            res = await asyncio.to_thread(self._execute_sparse_search, query, s_k, filter)
            sparse_latency = (time.perf_counter() - t0) * 1000.0
            return res

        results_dense, results_sparse = await asyncio.gather(
            run_dense(),
            run_sparse(),
            return_exceptions=True,
        )

        # 3. Degraded Mode & Partial Failure Handling
        dense_failed = isinstance(results_dense, Exception)
        sparse_failed = isinstance(results_sparse, Exception)

        if dense_failed and sparse_failed:
            raise HybridRetrievalError(
                f"Both retrieval backends failed. Dense: {results_dense}, Sparse: {results_sparse}"
            )
        elif dense_failed:
            degraded_mode = True
            warnings.append(f"Dense vector retrieval failed: {str(results_dense)}. Falling back to sparse search.")
            sparse_candidates = results_sparse  # type: ignore
        elif sparse_failed:
            degraded_mode = True
            warnings.append(f"Sparse lexical retrieval failed: {str(results_sparse)}. Falling back to dense search.")
            dense_candidates = results_dense  # type: ignore
        else:
            dense_candidates = results_dense  # type: ignore
            sparse_candidates = results_sparse  # type: ignore

        # 4. Fusion and Ranking
        fusion_start = time.perf_counter()
        scored_chunks = self.fusion.fuse(
            dense_candidates=dense_candidates,
            sparse_candidates=sparse_candidates,
            strategy=chosen_strategy,
            rrf_k=k_val,
            dense_weight=w_dense,
            sparse_weight=w_sparse,
            final_top_k=f_k,
        )
        fusion_latency = (time.perf_counter() - fusion_start) * 1000.0
        total_latency = (time.perf_counter() - start_total) * 1000.0

        # Diagnostics summary
        unique_merged_count = len({c.chunk_id for c in dense_candidates} | {c.chunk_id for c in sparse_candidates})

        diagnostics = RetrievalDiagnostics(
            query=query,
            query_type=q_type.value,
            dense_latency_ms=dense_latency,
            sparse_latency_ms=sparse_latency,
            fusion_latency_ms=fusion_latency,
            total_latency_ms=total_latency,
            dense_candidates_count=len(dense_candidates),
            sparse_candidates_count=len(sparse_candidates),
            merged_candidates_count=unique_merged_count,
            fusion_strategy=chosen_strategy.value,
            degraded_mode=degraded_mode,
            warnings=warnings,
        )

        return HybridRetrievalResponse(
            results=scored_chunks,
            diagnostics=diagnostics,
        )


# Global hybrid retrieval service singleton
hybrid_retriever = HybridRetrievalService()
