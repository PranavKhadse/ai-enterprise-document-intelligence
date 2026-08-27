"""
Services package exposing storage, parser, chunker, embedding, vector store, BM25,
dual indexing, query analysis, fusion, hybrid retrieval, evaluation, optimizer,
cross-encoder reranking, context compression, evidence selection, reranking pipeline,
LLM providers, prompt builder, citation verifier, grounding verifier, RAG synthesis, RAG pipeline,
clause extractor, clause aligner, entity diff engine, document comparator, and auth service.
"""
from backend.app.services.storage import (
    LocalFileStorage,
    StorageService,
    StorageError,
    FileSizeExceededError,
    InvalidFileTypeError,
    storage_service,
)
from backend.app.services.parser import (
    PDFParserService,
    ParserError,
    CorruptedPDFError,
    EncryptedPDFError,
    EmptyDocumentError,
    parser_service,
)
from backend.app.services.chunker import (
    StructureAwareChunkerService,
    ChunkingError,
    TableTooLargeError,
    chunker_service,
)
from backend.app.services.embedding import (
    EmbeddingService,
    FastEmbedEmbeddingService,
    EmbeddingError,
    EmbeddingDimensionError,
    embedding_service,
)
from backend.app.services.vector_store import (
    VectorStoreService,
    VectorStoreError,
    VectorDimensionMismatchError,
    CollectionNotFoundError,
    vector_store_service,
)
from backend.app.services.indexer import (
    IndexingService,
    indexing_service,
)
from backend.app.services.bm25 import (
    BM25IndexService,
    BM25Error,
    IndexCorruptedError,
    bm25_service,
)
from backend.app.services.dual_indexer import (
    DualIndexingService,
    dual_indexing_service,
)
from backend.app.services.query_analyzer import (
    QueryAnalyzer,
    query_analyzer,
)
from backend.app.services.fusion import (
    FusionEngine,
    fusion_engine,
)
from backend.app.services.hybrid_retriever import (
    HybridRetrievalService,
    HybridRetrievalError,
    hybrid_retriever,
)
from backend.app.services.evaluator import (
    RetrievalEvaluator,
    retrieval_evaluator,
)
from backend.app.services.retrieval_optimizer import (
    RetrievalOptimizer,
    retrieval_optimizer,
)
from backend.app.services.cross_encoder import (
    CrossEncoderRerankerService,
    RerankerError,
    ModelInitializationError,
    cross_encoder_service,
)
from backend.app.services.context_compressor import (
    ContextCompressionService,
    context_compressor,
)
from backend.app.services.evidence_selector import (
    EvidenceSelector,
    evidence_selector,
)
from backend.app.services.reranking_pipeline import (
    RerankingPipelineService,
    reranking_pipeline,
)
from backend.app.services.llm_provider import (
    BaseLLMProvider,
    MockLLMProvider,
    OpenAICompatibleLLMProvider,
    LLMProviderError,
    LLMTimeoutError,
    LLMUnavailableError,
    LLMMalformedOutputError,
    get_llm_provider,
    llm_provider,
)
from backend.app.services.prompt_builder import (
    RAGPromptBuilder,
    prompt_builder,
)
from backend.app.services.citation_verifier import (
    CitationVerifierService,
    citation_verifier,
)
from backend.app.services.grounding_verifier import (
    GroundingVerifierService,
    grounding_verifier,
)
from backend.app.services.rag_synthesis import (
    RAGSynthesisService,
    rag_synthesis_service,
)
from backend.app.services.rag_pipeline import (
    RAGPipelineService,
    rag_pipeline_service,
)
from backend.app.services.clause_extractor import (
    ClauseExtractorService,
    ExtractedClause,
    clause_extractor,
)
from backend.app.services.clause_aligner import (
    ClauseAlignerService,
    AlignmentCandidate,
    clause_aligner,
)
from backend.app.services.entity_diff import (
    EntityDiffEngine,
    entity_diff_engine,
)
from backend.app.services.document_comparator import (
    DocumentComparatorService,
    LLMDiffProposal,
    document_comparator,
)
from backend.app.services.auth_service import (
    AuthService,
    auth_service,
)

__all__ = [
    "LocalFileStorage",
    "StorageService",
    "StorageError",
    "FileSizeExceededError",
    "InvalidFileTypeError",
    "storage_service",
    "PDFParserService",
    "ParserError",
    "CorruptedPDFError",
    "EncryptedPDFError",
    "EmptyDocumentError",
    "parser_service",
    "StructureAwareChunkerService",
    "ChunkingError",
    "TableTooLargeError",
    "chunker_service",
    "EmbeddingService",
    "FastEmbedEmbeddingService",
    "EmbeddingError",
    "EmbeddingDimensionError",
    "embedding_service",
    "VectorStoreService",
    "VectorStoreError",
    "VectorDimensionMismatchError",
    "CollectionNotFoundError",
    "vector_store_service",
    "IndexingService",
    "indexing_service",
    "BM25IndexService",
    "BM25Error",
    "IndexCorruptedError",
    "bm25_service",
    "DualIndexingService",
    "dual_indexing_service",
    "QueryAnalyzer",
    "query_analyzer",
    "FusionEngine",
    "fusion_engine",
    "HybridRetrievalService",
    "HybridRetrievalError",
    "hybrid_retriever",
    "RetrievalEvaluator",
    "retrieval_evaluator",
    "RetrievalOptimizer",
    "retrieval_optimizer",
    "CrossEncoderRerankerService",
    "RerankerError",
    "ModelInitializationError",
    "cross_encoder_service",
    "ContextCompressionService",
    "context_compressor",
    "EvidenceSelector",
    "evidence_selector",
    "RerankingPipelineService",
    "reranking_pipeline",
    "BaseLLMProvider",
    "MockLLMProvider",
    "OpenAICompatibleLLMProvider",
    "LLMProviderError",
    "LLMTimeoutError",
    "LLMUnavailableError",
    "LLMMalformedOutputError",
    "get_llm_provider",
    "llm_provider",
    "RAGPromptBuilder",
    "prompt_builder",
    "CitationVerifierService",
    "citation_verifier",
    "GroundingVerifierService",
    "grounding_verifier",
    "RAGSynthesisService",
    "rag_synthesis_service",
    "RAGPipelineService",
    "rag_pipeline_service",
    "ClauseExtractorService",
    "ExtractedClause",
    "clause_extractor",
    "ClauseAlignerService",
    "AlignmentCandidate",
    "clause_aligner",
    "EntityDiffEngine",
    "entity_diff_engine",
    "DocumentComparatorService",
    "LLMDiffProposal",
    "document_comparator",
    "AuthService",
    "auth_service",
]
