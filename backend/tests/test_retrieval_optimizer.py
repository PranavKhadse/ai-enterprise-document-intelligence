"""
Unit tests for RetrievalOptimizer parameter grid search and objective score calculation.
"""
import uuid
import pytest
from backend.app.schemas.optimizer import GridConfig
from backend.app.schemas.retrieval import EvalSample, EvaluationReport, FusionStrategy
from backend.app.services.retrieval_optimizer import RetrievalOptimizer


@pytest.fixture
def optimizer():
    return RetrievalOptimizer()


def test_objective_score_calculation(optimizer):
    """
    Verifies that objective score calculation weights Recall@10, MRR, NDCG@10, and HitRate@10 correctly.
    """
    metrics = EvaluationReport(
        recall_at_k=1.0,
        precision_at_k=0.5,
        hit_rate_at_k=1.0,
        mrr=1.0,
        ndcg_at_k=1.0,
        total_queries=10,
        k=10,
        strategy="rrf",
    )

    # 0.45 * 1.0 + 0.25 * 1.0 + 0.20 * 1.0 + 0.10 * 1.0 = 1.0
    score = optimizer.compute_objective_score(metrics)
    assert pytest.approx(score, rel=1e-4) == 1.0


@pytest.mark.asyncio
async def test_optimizer_isolated_stack_and_baselines(optimizer):
    """
    Verifies that the isolated benchmark stack indexes corpus chunks and executes baseline evaluations.
    """
    corpus_data, tuning_samples, _ = optimizer.load_fixtures()
    assert len(corpus_data) == 25
    assert len(tuning_samples) == 16

    retriever = optimizer.build_isolated_stack(corpus_data)
    baselines = await optimizer.evaluate_baselines(retriever, tuning_samples[:3], k=10)

    assert "dense_only" in baselines
    assert "sparse_only" in baselines
    assert "default_rrf" in baselines
    assert "default_weighted_score" in baselines

    for name, report in baselines.items():
        assert isinstance(report, EvaluationReport)
        assert report.recall_at_k >= 0.0
        assert report.total_queries == 3


@pytest.mark.asyncio
async def test_optimizer_grid_search_execution(optimizer):
    """
    Verifies that grid search evaluates configurations across tuning queries deterministically.
    """
    corpus_data, tuning_samples, _ = optimizer.load_fixtures()
    retriever = optimizer.build_isolated_stack(corpus_data)

    # Test on a small subset of queries for fast deterministic verification
    grid_results, best_cfg = await optimizer.run_grid_search(
        retriever, tuning_samples[:2], k=10
    )

    assert len(grid_results) == 600
    assert isinstance(best_cfg, GridConfig)
    assert grid_results[0].rank == 1
    assert grid_results[0].objective_score >= grid_results[-1].objective_score
