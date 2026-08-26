"""
Rank and Score Fusion Engine.
Implements Reciprocal Rank Fusion (RRF), Min-Max Normalized Weighted Score Fusion,
candidate deduplication, deterministic 4-level tie-breaking, and retrieval explainability.
"""
import uuid
from typing import Any, Dict, List, Optional
from backend.app.schemas.bm25 import BM25SearchResult
from backend.app.schemas.embedding import VectorSearchResult
from backend.app.schemas.retrieval import FusionStrategy, ScoredChunk


class CandidatePoolItem:
    """
    Internal accumulator for consolidating candidates from multiple retrieval backends.
    """
    def __init__(self, chunk_id: uuid.UUID, document_id: uuid.UUID, content: str):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.version_id: Optional[uuid.UUID] = None
        self.department_id: Optional[uuid.UUID] = None
        self.content = content
        self.page_number: Optional[int] = None
        self.section_path: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
        self.dense_score: Optional[float] = None
        self.sparse_score: Optional[float] = None
        self.dense_rank: Optional[int] = None
        self.sparse_rank: Optional[int] = None
        self.retrieval_methods: List[str] = []


class FusionEngine:
    """
    Orchestrates candidate merging, rank/score fusion, and deterministic ordering.
    """

    @staticmethod
    def _merge_candidates(
        dense_candidates: List[VectorSearchResult],
        sparse_candidates: List[BM25SearchResult],
    ) -> Dict[uuid.UUID, CandidatePoolItem]:
        """
        Deduplicates and merges candidates from dense and sparse lists by chunk_id.
        """
        pool: Dict[uuid.UUID, CandidatePoolItem] = {}

        # 1. Ingest Dense Candidates
        for rank_0, hit in enumerate(dense_candidates):
            cid = hit.chunk_id
            if cid not in pool:
                item = CandidatePoolItem(chunk_id=cid, document_id=hit.document_id, content=hit.content)
                item.version_id = hit.version_id
                item.page_number = hit.page_number
                item.section_path = hit.section_path
                item.metadata = dict(hit.payload) if hit.payload else {}
                dept = hit.payload.get("department_id") if hit.payload else None
                item.department_id = uuid.UUID(dept) if dept else None
                pool[cid] = item

            pool[cid].dense_score = hit.score
            pool[cid].dense_rank = rank_0 + 1  # 1-based rank
            if "dense" not in pool[cid].retrieval_methods:
                pool[cid].retrieval_methods.append("dense")

        # 2. Ingest Sparse Candidates
        for rank_0, hit in enumerate(sparse_candidates):
            cid = hit.chunk_id
            if cid not in pool:
                item = CandidatePoolItem(chunk_id=cid, document_id=hit.document_id, content=hit.content)
                item.version_id = hit.version_id
                item.page_number = hit.page_number
                item.section_path = hit.section_path
                item.metadata = dict(hit.payload) if hit.payload else {}
                dept = hit.payload.get("department_id") if hit.payload else None
                item.department_id = uuid.UUID(dept) if dept else None
                pool[cid] = item

            pool[cid].sparse_score = hit.score
            pool[cid].sparse_rank = rank_0 + 1  # 1-based rank
            if "bm25" not in pool[cid].retrieval_methods:
                pool[cid].retrieval_methods.append("bm25")

        return pool

    @staticmethod
    def _generate_explanation(item: CandidatePoolItem, strategy: str) -> str:
        """
        Generates a human-readable explanation of why this chunk was ranked.
        """
        has_dense = item.dense_rank is not None
        has_sparse = item.sparse_rank is not None

        if has_dense and has_sparse:
            return (
                f"Retrieved by both semantic similarity (dense rank #{item.dense_rank}) "
                f"and exact keyword match (sparse rank #{item.sparse_rank}) using {strategy.upper()} fusion."
            )
        elif has_dense:
            return f"Retrieved by semantic similarity (dense rank #{item.dense_rank}, score {item.dense_score:.3f})."
        elif has_sparse:
            return f"Retrieved by exact keyword match (sparse rank #{item.sparse_rank}, score {item.sparse_score:.3f})."
        return f"Retrieved via {strategy} fusion."

    def reciprocal_rank_fusion(
        self,
        dense_candidates: List[VectorSearchResult],
        sparse_candidates: List[BM25SearchResult],
        rrf_k: int = 60,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        final_top_k: int = 10,
    ) -> List[ScoredChunk]:
        """
        Fuses candidate lists using weighted Reciprocal Rank Fusion (RRF):
        RRF(d) = w_dense / (k + rank_dense(d)) + w_sparse / (k + rank_sparse(d))
        """
        pool = self._merge_candidates(dense_candidates, sparse_candidates)
        if not pool:
            return []

        scored_items: List[ScoredChunk] = []

        for cid, item in pool.items():
            rrf_score = 0.0
            if item.dense_rank is not None:
                rrf_score += dense_weight / (rrf_k + item.dense_rank)
            if item.sparse_rank is not None:
                rrf_score += sparse_weight / (rrf_k + item.sparse_rank)

            explanation = self._generate_explanation(item, "rrf")

            scored_items.append(
                ScoredChunk(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    version_id=item.version_id,
                    department_id=item.department_id,
                    content=item.content,
                    page_number=item.page_number,
                    section_path=item.section_path,
                    final_score=float(rrf_score),
                    dense_score=item.dense_score,
                    sparse_score=item.sparse_score,
                    dense_rank=item.dense_rank,
                    sparse_rank=item.sparse_rank,
                    rrf_score=float(rrf_score),
                    retrieval_methods=item.retrieval_methods,
                    explanation=explanation,
                    metadata=item.metadata,
                )
            )

        # Deterministic 4-level tie-breaking
        scored_items.sort(
            key=lambda x: (
                x.final_score,
                x.dense_score if x.dense_score is not None else -1.0,
                x.sparse_score if x.sparse_score is not None else -1.0,
                -int(x.chunk_id.int % 1000000),  # Consistent secondary tie breaker
            ),
            reverse=True,
        )

        return scored_items[:final_top_k]

    def weighted_score_fusion(
        self,
        dense_candidates: List[VectorSearchResult],
        sparse_candidates: List[BM25SearchResult],
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        final_top_k: int = 10,
    ) -> List[ScoredChunk]:
        """
        Fuses candidate lists using Min-Max Normalized Weighted Score Fusion:
        Score(d) = w_dense * Norm(DenseScore) + w_sparse * Norm(SparseScore)
        """
        pool = self._merge_candidates(dense_candidates, sparse_candidates)
        if not pool:
            return []

        # Min-Max Normalization bounds
        dense_scores = [hit.score for hit in dense_candidates]
        sparse_scores = [hit.score for hit in sparse_candidates]

        min_d = min(dense_scores) if dense_scores else 0.0
        max_d = max(dense_scores) if dense_scores else 1.0
        range_d = max_d - min_d

        min_s = min(sparse_scores) if sparse_scores else 0.0
        max_s = max(sparse_scores) if sparse_scores else 1.0
        range_s = max_s - min_s

        scored_items: List[ScoredChunk] = []

        for cid, item in pool.items():
            # Normalized Dense Score
            if item.dense_score is not None:
                norm_dense = 1.0 if range_d == 0 else (item.dense_score - min_d) / range_d
            else:
                norm_dense = 0.0

            # Normalized Sparse Score
            if item.sparse_score is not None:
                norm_sparse = 1.0 if range_s == 0 else (item.sparse_score - min_s) / range_s
            else:
                norm_sparse = 0.0

            fused_score = (dense_weight * norm_dense) + (sparse_weight * norm_sparse)
            explanation = self._generate_explanation(item, "weighted_score")

            scored_items.append(
                ScoredChunk(
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    version_id=item.version_id,
                    department_id=item.department_id,
                    content=item.content,
                    page_number=item.page_number,
                    section_path=item.section_path,
                    final_score=float(fused_score),
                    dense_score=item.dense_score,
                    sparse_score=item.sparse_score,
                    dense_rank=item.dense_rank,
                    sparse_rank=item.sparse_rank,
                    normalized_dense_score=float(norm_dense),
                    normalized_sparse_score=float(norm_sparse),
                    retrieval_methods=item.retrieval_methods,
                    explanation=explanation,
                    metadata=item.metadata,
                )
            )

        # Deterministic 4-level tie-breaking
        scored_items.sort(
            key=lambda x: (
                x.final_score,
                x.dense_score if x.dense_score is not None else -1.0,
                x.sparse_score if x.sparse_score is not None else -1.0,
                -int(x.chunk_id.int % 1000000),
            ),
            reverse=True,
        )

        return scored_items[:final_top_k]

    def fuse(
        self,
        dense_candidates: List[VectorSearchResult],
        sparse_candidates: List[BM25SearchResult],
        strategy: FusionStrategy = FusionStrategy.RRF,
        rrf_k: int = 60,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        final_top_k: int = 10,
    ) -> List[ScoredChunk]:
        """
        Unified fusion dispatcher.
        """
        if strategy == FusionStrategy.DENSE_ONLY:
            return self.reciprocal_rank_fusion(
                dense_candidates=dense_candidates,
                sparse_candidates=[],
                rrf_k=rrf_k,
                dense_weight=1.0,
                sparse_weight=0.0,
                final_top_k=final_top_k,
            )
        elif strategy == FusionStrategy.SPARSE_ONLY:
            return self.reciprocal_rank_fusion(
                dense_candidates=[],
                sparse_candidates=sparse_candidates,
                rrf_k=rrf_k,
                dense_weight=0.0,
                sparse_weight=1.0,
                final_top_k=final_top_k,
            )
        elif strategy == FusionStrategy.WEIGHTED_SCORE:
            return self.weighted_score_fusion(
                dense_candidates=dense_candidates,
                sparse_candidates=sparse_candidates,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                final_top_k=final_top_k,
            )
        else:  # FusionStrategy.RRF
            return self.reciprocal_rank_fusion(
                dense_candidates=dense_candidates,
                sparse_candidates=sparse_candidates,
                rrf_k=rrf_k,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
                final_top_k=final_top_k,
            )


# Global fusion engine singleton
fusion_engine = FusionEngine()
