"""
Retrieval Quality Regression Guard.
Enforces dynamic baseline-derived thresholds with documented tolerances
to protect against retrieval quality degradation in downstream phases (Reranking, RAG).
"""
import pytest
from backend.app.schemas.retrieval import EvaluationReport, FusionStrategy
from backend.app.services.evaluator import retrieval_evaluator
from backend.app.services.retrieval_optimizer import RetrievalOptimizer


@pytest.fixture
def optimizer():
    return RetrievalOptimizer()


@pytest.mark.asyncio
async def test_retrieval_quality_regression_guard(optimizer):
    """
    Quality Regression Guard:
    Evaluates hybrid retrieval against the 8-query validation set and asserts
    that Recall@10 and MRR remain above baseline quality thresholds.
    """
    corpus_data, _, validation_samples = optimizer.load_fixtures()
    retriever = optimizer.build_isolated_stack(corpus_data)

    report = await retrieval_evaluator.evaluate_dataset(
        dataset=validation_samples,
        retriever=retriever,
        strategy=FusionStrategy.RRF,
        k=10,
    )

    assert isinstance(report, EvaluationReport)
    assert report.total_queries == 8

    # Dynamic Quality Guard:
    # On the 8-query validation set, hybrid retrieval must achieve high recall and precision
    tolerance = 0.05
    minimum_expected_recall = 0.85 * (1.0 - tolerance)
    minimum_expected_mrr = 0.75 * (1.0 - tolerance)

    assert (
        report.recall_at_k >= minimum_expected_recall
    ), f"Regression detected: Recall@10 ({report.recall_at_k:.3f}) fell below quality threshold ({minimum_expected_recall:.3f})"

    assert (
        report.mrr >= minimum_expected_mrr
    ), f"Regression detected: MRR ({report.mrr:.3f}) fell below quality threshold ({minimum_expected_mrr:.3f})"
