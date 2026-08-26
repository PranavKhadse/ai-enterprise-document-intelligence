"""
Pydantic schemas and Data Transfer Objects (DTOs).
"""
from backend.app.schemas.health import HealthResponse
from backend.app.schemas.document import DocumentUploadResponse
from backend.app.schemas.parser import (
    ElementType,
    ParsedElement,
    ParsedPage,
    ParsedDocument,
)
from backend.app.schemas.chunk import (
    ChunkMetadata,
    ChunkingConfig,
    ChunkDTO,
    DocumentChunksResponse,
)
from backend.app.schemas.embedding import (
    EmbeddingConfig,
    VectorSearchResult,
    IndexingResult,
)
from backend.app.schemas.bm25 import (
    BM25Config,
    BM25SearchResult,
    DualIndexingResult,
)
from backend.app.schemas.retrieval import (
    QueryType,
    FusionStrategy,
    RetrievalFilter,
    ScoredChunk,
    RetrievalDiagnostics,
    HybridRetrievalResponse,
    EvalSample,
    EvaluationReport,
)
from backend.app.schemas.optimizer import (
    GridConfig,
    ConfigurationResult,
    QueryTypeBreakdown,
    LatencyStats,
    OptimizationReport,
)
from backend.app.schemas.reranking import (
    RerankerConfig,
    CompressionConfig,
    RerankedChunk,
    RerankingDiagnostics,
    RAGContextItem,
    RerankedRetrievalResponse,
)

__all__ = [
    "HealthResponse",
    "DocumentUploadResponse",
    "ElementType",
    "ParsedElement",
    "ParsedPage",
    "ParsedDocument",
    "ChunkMetadata",
    "ChunkingConfig",
    "ChunkDTO",
    "DocumentChunksResponse",
    "EmbeddingConfig",
    "VectorSearchResult",
    "IndexingResult",
    "BM25Config",
    "BM25SearchResult",
    "DualIndexingResult",
    "QueryType",
    "FusionStrategy",
    "RetrievalFilter",
    "ScoredChunk",
    "RetrievalDiagnostics",
    "HybridRetrievalResponse",
    "EvalSample",
    "EvaluationReport",
    "GridConfig",
    "ConfigurationResult",
    "QueryTypeBreakdown",
    "LatencyStats",
    "OptimizationReport",
    "RerankerConfig",
    "CompressionConfig",
    "RerankedChunk",
    "RerankingDiagnostics",
    "RAGContextItem",
    "RerankedRetrievalResponse",
]
