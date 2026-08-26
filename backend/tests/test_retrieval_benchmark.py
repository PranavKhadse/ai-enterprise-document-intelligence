"""
Empirical Benchmark Execution and Latency Profiling.
Runs the complete optimization pipeline and generates backend/config/retrieval_benchmark_results.json.
"""
from pathlib import Path
import pytest
from backend.app.schemas.optimizer import OptimizationReport
from backend.app.services.retrieval_optimizer import RetrievalOptimizer


@pytest.fixture
def optimizer():
    return RetrievalOptimizer()


@pytest.mark.asyncio
async def test_run_full_benchmark_and_generate_results(optimizer):
    """
    Executes full empirical benchmark grid search, validates on held-out test split,
    profiles latencies, and writes backend/config/retrieval_benchmark_results.json from real execution.
    """
    output_path = "backend/config/retrieval_benchmark_results.json"
    report = await optimizer.run_full_optimization(output_results_path=output_path)

    assert isinstance(report, OptimizationReport)
    assert report.total_configurations_evaluated == 600
    assert report.tuning_queries_count == 16
    assert report.validation_queries_count == 8

    # Verify report was written to disk
    file_path = Path(output_path)
    assert file_path.exists()

    # Verify metrics are properly recorded
    assert report.best_tuning_metrics.recall_at_k > 0.0
    assert report.validation_metrics_default.recall_at_k > 0.0
    assert report.validation_metrics_best.recall_at_k > 0.0
    assert len(report.latency_profiles) == 4
    for lat in report.latency_profiles:
        assert lat.avg_ms > 0.0
        assert lat.p50_ms > 0.0
