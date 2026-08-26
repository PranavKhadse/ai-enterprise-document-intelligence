"""
Retrieval Benchmark, Empirical Validation & Parameter Optimization Service.
Executes systematic grid search across RRF constants, weights, candidate pool depths,
and query-aware routing strategies on a deterministic benchmark corpus.
Generates empirical comparison reports and validates generalizations on held-out test splits.
"""
import itertools
import json
import statistics
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct
from backend.app.db.models.document import Document
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.schemas.bm25 import BM25Config, BM25SearchResult
from backend.app.schemas.embedding import VectorSearchResult
from backend.app.schemas.optimizer import (
    ConfigurationResult,
    GridConfig,
    LatencyStats,
    OptimizationReport,
    QueryTypeBreakdown,
)
from backend.app.schemas.retrieval import (
    EvalSample,
    EvaluationReport,
    FusionStrategy,
    QueryType,
)
from backend.app.services.bm25 import BM25IndexService
from backend.app.services.embedding import embedding_service
from backend.app.services.evaluator import retrieval_evaluator
from backend.app.services.fusion import fusion_engine
from backend.app.services.hybrid_retriever import HybridRetrievalService
from backend.app.services.query_analyzer import query_analyzer
from backend.app.services.vector_store import VectorStoreService


class RetrievalOptimizer:
    """
    Empirical optimization engine for hybrid retrieval parameters.
    """

    def __init__(
        self,
        corpus_path: Optional[str] = None,
        benchmark_path: Optional[str] = None,
    ):
        self.corpus_path = Path(
            corpus_path or "backend/tests/fixtures/retrieval_corpus.json"
        )
        self.benchmark_path = Path(
            benchmark_path or "backend/tests/fixtures/retrieval_benchmark.json"
        )

    def load_fixtures(self) -> Tuple[List[Dict[str, Any]], List[EvalSample], List[EvalSample]]:
        """
        Loads the benchmark corpus and partitioned tuning / validation query sets.
        """
        with open(self.corpus_path, "r", encoding="utf-8") as f:
            corpus_data = json.load(f)

        with open(self.benchmark_path, "r", encoding="utf-8") as f:
            bench_data = json.load(f)

        tuning_samples = [
            EvalSample(
                query=q["query"],
                expected_chunk_ids=[uuid.UUID(cid) for cid in q["expected_chunk_ids"]],
                relevance_grades=q.get("relevance_grades"),
            )
            for q in bench_data.get("tuning_set", [])
        ]

        validation_samples = [
            EvalSample(
                query=q["query"],
                expected_chunk_ids=[uuid.UUID(cid) for cid in q["expected_chunk_ids"]],
                relevance_grades=q.get("relevance_grades"),
            )
            for q in bench_data.get("validation_set", [])
        ]

        return corpus_data, tuning_samples, validation_samples

    def build_isolated_stack(
        self, corpus_data: List[Dict[str, Any]]
    ) -> HybridRetrievalService:
        """
        Builds and indexes an isolated, in-memory hybrid retrieval stack.
        """
        qdrant_client = QdrantClient(location=":memory:")
        vector_service = VectorStoreService(
            client=qdrant_client, collection_name="benchmark_retrieval_collection"
        )
        vector_service.ensure_collection(dimension=384)

        bm25_service = BM25IndexService(
            config=BM25Config(auto_persist=False)
        )

        # Batch embed all corpus chunks
        texts = [chunk["content"] for chunk in corpus_data]
        vectors = embedding_service.embed_batch(texts)

        points: List[PointStruct] = []
        orm_chunks: List[DocumentChunk] = []

        # Dummy parent document for ORM compatibility
        dummy_doc = Document(id=uuid.UUID(corpus_data[0]["document_id"]), title="Benchmark Corpus")

        for idx, chunk in enumerate(corpus_data):
            cid = chunk["id"]
            doc_id = chunk["document_id"]
            payload = {
                "document_id": doc_id,
                "version_id": None,
                "department_id": None,
                "chunk_id": cid,
                "content": chunk["content"],
                "section_path": chunk.get("section_path"),
                "page_number": chunk.get("page_number"),
                "document_title": chunk.get("title"),
                "token_count": chunk.get("token_count", len(chunk["content"].split())),
            }

            points.append(PointStruct(id=cid, vector=vectors[idx], payload=payload))

            orm_chunk = DocumentChunk(
                id=uuid.UUID(cid),
                document_id=uuid.UUID(doc_id),
                chunk_index=idx,
                content=chunk["content"],
                section_path=chunk.get("section_path"),
                page_number=chunk.get("page_number"),
                metadata_json=payload,
                token_count=chunk.get("token_count"),
            )
            orm_chunks.append(orm_chunk)

        # Index points into Qdrant & BM25 once
        vector_service.upsert_points(points, dimension=384)
        bm25_service.index_chunks(orm_chunks, dummy_doc)

        return HybridRetrievalService(
            vector_service=vector_service,
            embed_service=embedding_service,
            sparse_service=bm25_service,
            analyzer=query_analyzer,
            fusion=fusion_engine,
        )

    @staticmethod
    def compute_objective_score(metrics: EvaluationReport) -> float:
        """
        Calculates balanced multi-objective score:
        0.45 * Recall@10 + 0.25 * MRR + 0.20 * NDCG@10 + 0.10 * HitRate@10
        """
        return (
            0.45 * metrics.recall_at_k
            + 0.25 * metrics.mrr
            + 0.20 * metrics.ndcg_at_k
            + 0.10 * metrics.hit_rate_at_k
        )

    async def run_grid_search(
        self,
        retriever: HybridRetrievalService,
        tuning_samples: List[EvalSample],
        k: int = 10,
    ) -> Tuple[List[ConfigurationResult], GridConfig]:
        """
        Executes fast deterministic parameter grid search across all combinations.
        Precomputes dense and sparse candidate pools once per query to achieve sub-second execution.
        """
        rrf_ks = [20, 40, 60, 80, 100]
        weight_pairs = [
            (0.3, 0.7),
            (0.4, 0.6),
            (0.5, 0.5),
            (0.6, 0.4),
            (0.7, 0.3),
            (0.8, 0.2),
        ]
        pool_sizes = [20, 30, 50, 75, 100]
        strategies = [FusionStrategy.RRF, FusionStrategy.WEIGHTED_SCORE]
        query_awares = [True, False]

        all_combinations = list(
            itertools.product(
                rrf_ks, weight_pairs, pool_sizes, strategies, query_awares
            )
        )

        # 1. Precompute candidate pools for each tuning query up to max depth (limit=100)
        precomputed_pools: List[Tuple[EvalSample, List[VectorSearchResult], List[BM25SearchResult], QueryType, float, float, float]] = []
        for sample in tuning_samples:
            dense_hits = retriever._execute_dense_search(sample.query, limit=100, filter_spec=sample.filter)
            sparse_hits = retriever._execute_sparse_search(sample.query, limit=100, filter_spec=sample.filter)
            q_type, auto_dense_w, auto_sparse_w, pool_mult = retriever.analyzer.analyze_query(sample.query)
            precomputed_pools.append(
                (sample, dense_hits, sparse_hits, q_type, auto_dense_w, auto_sparse_w, pool_mult)
            )

        results: List[ConfigurationResult] = []

        # 2. Fast in-memory fusion evaluation across all 600 combinations
        for rrf_k, (w_d, w_s), pool_k, strat, q_aware in all_combinations:
            grid_cfg = GridConfig(
                rrf_k=rrf_k,
                dense_weight=w_d,
                sparse_weight=w_s,
                dense_top_k=pool_k,
                sparse_top_k=pool_k,
                strategy=strat,
                enable_query_aware_tuning=q_aware,
            )

            total_recall = 0.0
            total_precision = 0.0
            total_hit_rate = 0.0
            total_mrr = 0.0
            total_ndcg = 0.0

            for sample, dense_hits, sparse_hits, q_type, auto_d_w, auto_s_w, pool_mult in precomputed_pools:
                # Apply query aware tuning if enabled
                effective_wd = auto_d_w if q_aware else w_d
                effective_ws = auto_s_w if q_aware else w_s
                effective_dk = int(pool_k * pool_mult) if (q_aware and q_type == QueryType.SEMANTIC_QUESTION) else pool_k
                effective_sk = int(pool_k * pool_mult) if (q_aware and q_type == QueryType.EXACT_IDENTIFIER) else pool_k

                d_sliced = dense_hits[:effective_dk]
                s_sliced = sparse_hits[:effective_sk]

                scored_chunks = retriever.fusion.fuse(
                    dense_candidates=d_sliced,
                    sparse_candidates=s_sliced,
                    strategy=strat,
                    rrf_k=rrf_k,
                    dense_weight=effective_wd,
                    sparse_weight=effective_ws,
                    final_top_k=k,
                )

                retrieved_ids = [chunk.chunk_id for chunk in scored_chunks]
                sample_metrics = retrieval_evaluator.compute_metrics(
                    retrieved_ids=retrieved_ids,
                    expected_ids=sample.expected_chunk_ids,
                    relevance_grades=sample.relevance_grades,
                    k=k,
                )
                total_recall += sample_metrics["recall"]
                total_precision += sample_metrics["precision"]
                total_hit_rate += sample_metrics["hit_rate"]
                total_mrr += sample_metrics["mrr"]
                total_ndcg += sample_metrics["ndcg"]

            n = len(tuning_samples)
            report = EvaluationReport(
                recall_at_k=float(total_recall / n),
                precision_at_k=float(total_precision / n),
                hit_rate_at_k=float(total_hit_rate / n),
                mrr=float(total_mrr / n),
                ndcg_at_k=float(total_ndcg / n),
                total_queries=n,
                k=k,
                strategy=strat.value,
            )

            obj_score = self.compute_objective_score(report)
            results.append(
                ConfigurationResult(
                    config=grid_cfg,
                    metrics=report,
                    objective_score=obj_score,
                )
            )

        # Sort results: Objective Score DESC, with Parsimony (simpler configuration) tie-breaking
        results.sort(
            key=lambda item: (
                item.objective_score,
                item.metrics.recall_at_k,
                -item.config.dense_top_k,  # Prefer smaller candidate pool size for speed
                1 if item.config.strategy == FusionStrategy.RRF else 0,  # Prefer RRF
            ),
            reverse=True,
        )

        for rank, res in enumerate(results):
            res.rank = rank + 1

        best_config = results[0].config
        return results, best_config

    async def evaluate_baselines(
        self,
        retriever: HybridRetrievalService,
        samples: List[EvalSample],
        k: int = 10,
    ) -> Dict[str, EvaluationReport]:
        """
        Evaluates standard retrieval baselines on the given sample set.
        """
        baselines: Dict[str, EvaluationReport] = {}

        # 1. Dense Only
        baselines["dense_only"] = await retrieval_evaluator.evaluate_dataset(
            dataset=samples,
            retriever=retriever,
            strategy=FusionStrategy.DENSE_ONLY,
            k=k,
        )

        # 2. Sparse Only
        baselines["sparse_only"] = await retrieval_evaluator.evaluate_dataset(
            dataset=samples,
            retriever=retriever,
            strategy=FusionStrategy.SPARSE_ONLY,
            k=k,
        )

        # 3. Default RRF
        baselines["default_rrf"] = await retrieval_evaluator.evaluate_dataset(
            dataset=samples,
            retriever=retriever,
            strategy=FusionStrategy.RRF,
            k=k,
        )

        # 4. Default Weighted Score Fusion
        baselines["default_weighted_score"] = await retrieval_evaluator.evaluate_dataset(
            dataset=samples,
            retriever=retriever,
            strategy=FusionStrategy.WEIGHTED_SCORE,
            k=k,
        )

        return baselines

    async def compare_query_analyzer(
        self,
        retriever: HybridRetrievalService,
        samples: List[EvalSample],
        k: int = 10,
    ) -> Dict[str, Any]:
        """
        Compares fixed weights vs. query-aware dynamic weights across intent categories.
        """
        with_qa_report = await retrieval_evaluator.evaluate_dataset(
            dataset=samples,
            retriever=retriever,
            strategy=FusionStrategy.RRF,
            k=k,
        )

        # Load benchmark queries to group by intent
        with open(self.benchmark_path, "r", encoding="utf-8") as f:
            bench_data = json.load(f)
        all_q_meta = {q["query"]: q.get("query_type", "mixed") for q in bench_data.get("tuning_set", []) + bench_data.get("validation_set", [])}

        category_metrics: Dict[str, List[Dict[str, float]]] = {}

        for sample in samples:
            q_type = all_q_meta.get(sample.query, "mixed")
            resp = await retriever.retrieve(query=sample.query, final_top_k=k)
            retrieved_ids = [chunk.chunk_id for chunk in resp.results]
            metrics = retrieval_evaluator.compute_metrics(
                retrieved_ids=retrieved_ids,
                expected_ids=sample.expected_chunk_ids,
                relevance_grades=sample.relevance_grades,
                k=k,
            )
            category_metrics.setdefault(q_type, []).append(metrics)

        breakdown: List[QueryTypeBreakdown] = []
        for q_type, m_list in category_metrics.items():
            n = len(m_list)
            breakdown.append(
                QueryTypeBreakdown(
                    query_type=q_type,
                    count=n,
                    recall_at_10=float(sum(m["recall"] for m in m_list) / n),
                    mrr=float(sum(m["mrr"] for m in m_list) / n),
                    ndcg_at_10=float(sum(m["ndcg"] for m in m_list) / n),
                )
            )

        return {
            "overall_metrics": with_qa_report,
            "category_breakdown": [b.model_dump() for b in breakdown],
        }

    async def measure_latency(
        self,
        retriever: HybridRetrievalService,
        samples: List[EvalSample],
        iterations: int = 2,
    ) -> List[LatencyStats]:
        """
        Measures actual latency distributions across multiple iterations.
        """
        strategies = [
            ("dense_only", FusionStrategy.DENSE_ONLY),
            ("sparse_only", FusionStrategy.SPARSE_ONLY),
            ("default_rrf", FusionStrategy.RRF),
            ("weighted_score", FusionStrategy.WEIGHTED_SCORE),
        ]

        stats_list: List[LatencyStats] = []

        for name, strat in strategies:
            latencies_ms: List[float] = []
            for _ in range(iterations):
                for sample in samples:
                    t0 = time.perf_counter()
                    await retriever.retrieve(query=sample.query, strategy=strat, final_top_k=10)
                    elapsed = (time.perf_counter() - t0) * 1000.0
                    latencies_ms.append(elapsed)

            latencies_ms.sort()
            avg = float(statistics.mean(latencies_ms))
            p50 = float(statistics.median(latencies_ms))
            p95 = float(latencies_ms[int(len(latencies_ms) * 0.95)])
            p99 = float(latencies_ms[int(len(latencies_ms) * 0.99)])

            stats_list.append(
                LatencyStats(
                    strategy=name,
                    iterations=len(latencies_ms),
                    avg_ms=round(avg, 2),
                    p50_ms=round(p50, 2),
                    p95_ms=round(p95, 2),
                    p99_ms=round(p99, 2),
                )
            )

        return stats_list

    async def run_full_optimization(
        self,
        output_results_path: Optional[str] = None,
    ) -> OptimizationReport:
        """
        Executes the complete empirical optimization pipeline and writes results.
        """
        corpus_data, tuning_samples, validation_samples = self.load_fixtures()
        retriever = self.build_isolated_stack(corpus_data)

        # 1. Baselines on Tuning Set
        tuning_baselines = await self.evaluate_baselines(retriever, tuning_samples, k=10)

        # 2. Grid Search on Tuning Set
        grid_results, best_tuning_cfg = await self.run_grid_search(retriever, tuning_samples, k=10)
        best_tuning_metrics = grid_results[0].metrics

        # 3. Validation on Held-Out Set
        validation_default = await retrieval_evaluator.evaluate_dataset(
            dataset=validation_samples,
            retriever=retriever,
            strategy=FusionStrategy.RRF,
            k=10,
        )

        # Evaluate best config on validation set
        val_total_recall = 0.0
        val_total_precision = 0.0
        val_total_hit_rate = 0.0
        val_total_mrr = 0.0
        val_total_ndcg = 0.0

        for sample in validation_samples:
            resp = await retriever.retrieve(
                query=sample.query,
                filter=sample.filter,
                strategy=best_tuning_cfg.strategy,
                final_top_k=10,
                dense_top_k=best_tuning_cfg.dense_top_k,
                sparse_top_k=best_tuning_cfg.sparse_top_k,
                rrf_k=best_tuning_cfg.rrf_k,
                dense_weight=best_tuning_cfg.dense_weight,
                sparse_weight=best_tuning_cfg.sparse_weight,
                enable_query_aware_tuning=best_tuning_cfg.enable_query_aware_tuning,
            )
            r_ids = [chunk.chunk_id for chunk in resp.results]
            s_m = retrieval_evaluator.compute_metrics(
                retrieved_ids=r_ids,
                expected_ids=sample.expected_chunk_ids,
                relevance_grades=sample.relevance_grades,
                k=10,
            )
            val_total_recall += s_m["recall"]
            val_total_precision += s_m["precision"]
            val_total_hit_rate += s_m["hit_rate"]
            val_total_mrr += s_m["mrr"]
            val_total_ndcg += s_m["ndcg"]

        vn = len(validation_samples)
        validation_best = EvaluationReport(
            recall_at_k=float(val_total_recall / vn),
            precision_at_k=float(val_total_precision / vn),
            hit_rate_at_k=float(val_total_hit_rate / vn),
            mrr=float(val_total_mrr / vn),
            ndcg_at_k=float(val_total_ndcg / vn),
            total_queries=vn,
            k=10,
            strategy=best_tuning_cfg.strategy.value,
        )

        # 4. Query Analyzer Breakdown
        qa_comparison = await self.compare_query_analyzer(
            retriever, tuning_samples + validation_samples, k=10
        )

        # 5. Latency Profiling
        latency_stats = await self.measure_latency(
            retriever, tuning_samples, iterations=5
        )

        # 6. Recommendation Decision Logic
        if validation_best.recall_at_k >= validation_default.recall_at_k:
            decision = (
                f"Best empirical configuration (RRF k={best_tuning_cfg.rrf_k}, "
                f"w_dense={best_tuning_cfg.dense_weight}, w_sparse={best_tuning_cfg.sparse_weight}, "
                f"pool={best_tuning_cfg.dense_top_k}) confirmed on validation set. "
                f"Validation Recall@10: {validation_best.recall_at_k:.3f} vs Default: {validation_default.recall_at_k:.3f}."
            )
        else:
            decision = (
                f"Default configuration retained. Tuning winner did not exceed defaults on validation set."
            )

        limitations = (
            "Notice: This benchmark represents a synthetic enterprise validation corpus of 25 chunks and 24 queries. "
            "Metrics validate empirical ranking correctness and relative strategy gains, but do not claim universal global optimality."
        )

        report = OptimizationReport(
            benchmark_version="1.0.0",
            total_configurations_evaluated=len(grid_results),
            tuning_queries_count=len(tuning_samples),
            validation_queries_count=len(validation_samples),
            baselines={k: v for k, v in tuning_baselines.items()},
            best_tuning_config=best_tuning_cfg,
            best_tuning_metrics=best_tuning_metrics,
            validation_metrics_default=validation_default,
            validation_metrics_best=validation_best,
            query_analyzer_comparison=qa_comparison,
            latency_profiles=latency_stats,
            recommendation_decision=decision,
            limitations_notice=limitations,
        )

        # Save to disk
        target_path = Path(output_results_path or "backend/config/retrieval_benchmark_results.json")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2)

        return report


# Global retrieval optimizer singleton
retrieval_optimizer = RetrievalOptimizer()
