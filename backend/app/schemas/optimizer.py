"""
Pydantic schemas for Parameter Grid Search, Retrieval Optimization, and Latency Profiling.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.retrieval import EvaluationReport, FusionStrategy


class GridConfig(BaseModel):
    """
    Candidate retrieval parameter combination for empirical evaluation.
    """
    rrf_k: int = Field(default=60, description="RRF rank smoothing constant")
    dense_weight: float = Field(default=0.6, description="Weight assigned to dense semantic retriever")
    sparse_weight: float = Field(default=0.4, description="Weight assigned to sparse BM25 retriever")
    dense_top_k: int = Field(default=50, description="Candidate pool size retrieved from Qdrant")
    sparse_top_k: int = Field(default=50, description="Candidate pool size retrieved from BM25")
    strategy: FusionStrategy = Field(default=FusionStrategy.RRF, description="Fusion strategy")
    enable_query_aware_tuning: bool = Field(default=True, description="Whether query intent scaling is applied")

    model_config = ConfigDict(from_attributes=True)


class ConfigurationResult(BaseModel):
    """
    Evaluation result for a single configuration evaluated on the tuning set.
    """
    config: GridConfig
    metrics: EvaluationReport
    objective_score: float = Field(..., description="Calculated multi-metric objective score")
    rank: int = Field(default=1, description="Rank among all evaluated configurations")

    model_config = ConfigDict(from_attributes=True)


class QueryTypeBreakdown(BaseModel):
    """
    Metric breakdown per query intent category.
    """
    query_type: str
    count: int
    recall_at_10: float
    mrr: float
    ndcg_at_10: float

    model_config = ConfigDict(from_attributes=True)


class LatencyStats(BaseModel):
    """
    Empirically measured latency statistics across retrieval iterations.
    """
    strategy: str
    iterations: int
    avg_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float

    model_config = ConfigDict(from_attributes=True)


class OptimizationReport(BaseModel):
    """
    Complete empirical benchmark report containing baseline comparisons,
    grid search rankings, validation set generalization, and latency profiles.
    """
    benchmark_version: str = Field(default="1.0.0")
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_configurations_evaluated: int
    tuning_queries_count: int
    validation_queries_count: int
    baselines: Dict[str, EvaluationReport] = Field(default_factory=dict)
    best_tuning_config: GridConfig
    best_tuning_metrics: EvaluationReport
    validation_metrics_default: EvaluationReport
    validation_metrics_best: EvaluationReport
    query_analyzer_comparison: Dict[str, Any] = Field(default_factory=dict)
    latency_profiles: List[LatencyStats] = Field(default_factory=list)
    recommendation_decision: str
    limitations_notice: str

    model_config = ConfigDict(from_attributes=True)
