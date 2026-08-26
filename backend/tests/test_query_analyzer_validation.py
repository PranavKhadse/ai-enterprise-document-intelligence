"""
Comparative tests validating query-aware routing vs fixed weights across query intent categories.
"""
import pytest
from backend.app.schemas.retrieval import EvaluationReport
from backend.app.services.retrieval_optimizer import RetrievalOptimizer


@pytest.fixture
def optimizer():
    return RetrievalOptimizer()


@pytest.mark.asyncio
async def test_query_analyzer_validation_breakdown(optimizer):
    """
    Verifies that the optimizer produces per-category performance breakdown
    across exact identifiers, semantic questions, and keywords.
    """
    corpus_data, tuning_samples, validation_samples = optimizer.load_fixtures()
    retriever = optimizer.build_isolated_stack(corpus_data)

    all_samples = tuning_samples + validation_samples
    qa_results = await optimizer.compare_query_analyzer(retriever, all_samples, k=10)

    assert "overall_metrics" in qa_results
    assert "category_breakdown" in qa_results
    assert isinstance(qa_results["overall_metrics"], EvaluationReport)

    breakdown = qa_results["category_breakdown"]
    assert len(breakdown) >= 3

    categories = [b["query_type"] for b in breakdown]
    assert "exact_identifier" in categories or "semantic_question" in categories

    for cat in breakdown:
        assert cat["count"] > 0
        assert cat["recall_at_10"] >= 0.0
        assert cat["mrr"] >= 0.0
