"""
Services package exposing storage, parser, chunker, embedding, vector store, BM25, and indexing services.
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
]
