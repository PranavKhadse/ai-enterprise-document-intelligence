"""
Retrieval Quality Evaluation Framework.
Computes standard Information Retrieval metrics: Recall@K, Precision@K, HitRate@K, MRR, and NDCG@K
across benchmark datasets comparing dense, sparse, and hybrid retrieval strategies.
"""
import math
import uuid
from typing import Dict, List, Optional
from backend.app.schemas.retrieval import EvalSample, EvaluationReport, FusionStrategy
from backend.app.services.hybrid_retriever import HybridRetrievalService


class RetrievalEvaluator:
    """
    Lightweight deterministic evaluator for benchmarking retrieval quality.
    """

    @staticmethod
    def compute_metrics(
        retrieved_ids: List[uuid.UUID],
        expected_ids: List[uuid.UUID],
        relevance_grades: Optional[Dict[str, float]] = None,
        k: int = 10,
    ) -> Dict[str, float]:
        """
        Computes Recall@K, Precision@K, HitRate@K, MRR, and NDCG@K for a single query.
        """
        if not expected_ids or k <= 0:
            return {
                "recall": 0.0,
                "precision": 0.0,
                "hit_rate": 0.0,
                "mrr": 0.0,
                "ndcg": 0.0,
            }

        top_k_retrieved = retrieved_ids[:k]
        expected_set = set(expected_ids)

        # 1. Hits & Set intersections
        hits = [cid for cid in top_k_retrieved if cid in expected_set]
        num_hits = len(hits)

        # 2. Recall@K & Precision@K
        recall = num_hits / len(expected_ids)
        precision = num_hits / k
        hit_rate = 1.0 if num_hits > 0 else 0.0

        # 3. Mean Reciprocal Rank (MRR)
        mrr = 0.0
        for rank_0, cid in enumerate(top_k_retrieved):
            if cid in expected_set:
                mrr = 1.0 / (rank_0 + 1)
                break

        # 4. Normalized Discounted Cumulative Gain (NDCG@K)
        dcg = 0.0
        for rank_0, cid in enumerate(top_k_retrieved):
            rel = 0.0
            if relevance_grades and str(cid) in relevance_grades:
                rel = relevance_grades[str(cid)]
            elif cid in expected_set:
                rel = 1.0

            if rel > 0.0:
                dcg += (math.pow(2.0, rel) - 1.0) / math.log2((rank_0 + 1) + 1.0)

        # Ideal DCG (IDCG)
        ideal_rels: List[float] = []
        if relevance_grades:
            ideal_rels = sorted(relevance_grades.values(), reverse=True)[:k]
        else:
            ideal_rels = [1.0] * min(len(expected_ids), k)

        idcg = 0.0
        for rank_0, rel in enumerate(ideal_rels):
            idcg += (math.pow(2.0, rel) - 1.0) / math.log2((rank_0 + 1) + 1.0)

        ndcg = (dcg / idcg) if idcg > 0.0 else 0.0

        return {
            "recall": float(recall),
            "precision": float(precision),
            "hit_rate": float(hit_rate),
            "mrr": float(mrr),
            "ndcg": float(ndcg),
        }

    async def evaluate_dataset(
        self,
        dataset: List[EvalSample],
        retriever: HybridRetrievalService,
        strategy: FusionStrategy = FusionStrategy.RRF,
        k: int = 10,
    ) -> EvaluationReport:
        """
        Evaluates a dataset of queries and returns an aggregate EvaluationReport.
        """
        if not dataset:
            return EvaluationReport(
                recall_at_k=0.0,
                precision_at_k=0.0,
                hit_rate_at_k=0.0,
                mrr=0.0,
                ndcg_at_k=0.0,
                total_queries=0,
                k=k,
                strategy=strategy.value,
            )

        total_recall = 0.0
        total_precision = 0.0
        total_hit_rate = 0.0
        total_mrr = 0.0
        total_ndcg = 0.0

        for sample in dataset:
            response = await retriever.retrieve(
                query=sample.query,
                filter=sample.filter,
                strategy=strategy,
                final_top_k=k,
            )

            retrieved_ids = [chunk.chunk_id for chunk in response.results]
            metrics = self.compute_metrics(
                retrieved_ids=retrieved_ids,
                expected_ids=sample.expected_chunk_ids,
                relevance_grades=sample.relevance_grades,
                k=k,
            )

            total_recall += metrics["recall"]
            total_precision += metrics["precision"]
            total_hit_rate += metrics["hit_rate"]
            total_mrr += metrics["mrr"]
            total_ndcg += metrics["ndcg"]

        n = len(dataset)
        return EvaluationReport(
            recall_at_k=float(total_recall / n),
            precision_at_k=float(total_precision / n),
            hit_rate_at_k=float(total_hit_rate / n),
            mrr=float(total_mrr / n),
            ndcg_at_k=float(total_ndcg / n),
            total_queries=n,
            k=k,
            strategy=strategy.value,
        )


# Global retrieval evaluator singleton
retrieval_evaluator = RetrievalEvaluator()
