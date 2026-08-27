from typing import List, Optional, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Settings configured via Pydantic Settings.
    Values are dynamically loaded from environment variables or .env file.
    """
    PROJECT_NAME: str = "AI-Powered Enterprise Document Intelligence & Knowledge Platform"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # CORS Origins
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return []

    # Storage and Ingestion Settings
    STORAGE_DIR: str = "data/uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 52_428_800  # 50 MB
    ALLOWED_UPLOAD_EXTENSIONS: List[str] = [".pdf"]

    @field_validator("ALLOWED_UPLOAD_EXTENSIONS", mode="before")
    @classmethod
    def assemble_allowed_extensions(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip().lower() for i in v.split(",")]
        elif isinstance(v, list):
            return [ext.lower() for ext in v]
        return [".pdf"]

    # Structure-Aware Chunking Settings
    CHUNK_TARGET_SIZE_TOKENS: int = 450
    CHUNK_MAX_SIZE_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 50
    CHUNK_TOKENIZER_ENCODING: str = "cl100k_base"

    # Dense Embedding Settings
    EMBEDDING_PROVIDER: str = "fastembed"
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_BATCH_SIZE: int = 32

    # Qdrant Vector Database Settings
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION_NAME: str = "enterprise_documents"

    # BM25 Sparse Lexical Search Settings
    BM25_K1: float = 1.5
    BM25_B: float = 0.75
    BM25_INDEX_PATH: str = "data/bm25_index.pkl"
    BM25_AUTO_PERSIST: bool = True

    # Hybrid Retrieval & Rank Fusion Settings
    HYBRID_DENSE_TOP_K: int = 50
    HYBRID_SPARSE_TOP_K: int = 50
    HYBRID_FINAL_TOP_K: int = 10
    HYBRID_RRF_K: int = 60
    HYBRID_DENSE_WEIGHT: float = 0.6
    HYBRID_SPARSE_WEIGHT: float = 0.4
    HYBRID_FUSION_STRATEGY: str = "rrf"
    HYBRID_RETRIEVAL_TIMEOUT_SECONDS: float = 5.0
    HYBRID_ENABLE_QUERY_AWARE_TUNING: bool = True

    # Phase 7 Cross-Encoder Reranking Settings
    RERANKER_ENABLED: bool = True
    RERANKER_MODEL_NAME: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_ONNX_FILENAME: str = "onnx/model.onnx"
    RERANKER_TOP_K: int = 10
    RERANKER_CANDIDATE_WINDOW: int = 25
    RERANKER_BATCH_SIZE: int = 16
    RERANKER_MAX_LENGTH: int = 512
    RERANKER_QUERY_MAX_TOKENS: int = 128
    RERANKER_TIMEOUT_SECONDS: float = 3.0

    # Phase 7 Context Compression & Evidence Selection Settings
    COMPRESSION_ENABLED: bool = True
    COMPRESSION_TARGET_TOKENS_PER_CHUNK: int = 150
    COMPRESSION_MAX_CONTEXT_TOKENS: int = 1500
    COMPRESSION_PRESERVE_TABLES: bool = True
    DIVERSITY_NEAR_DUPLICATE_THRESHOLD: float = 0.85
    DIVERSITY_MAX_CHUNKS_PER_SECTION: int = 2

    # Phase 8 LLM Provider & RAG Synthesis Settings
    LLM_PROVIDER: str = "mock"
    LLM_MODEL_NAME: str = "gpt-4o-mini"
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 1024
    LLM_TIMEOUT_SECONDS: float = 10.0
    RAG_ENABLE_VERIFICATION: bool = True
    RAG_LEXICAL_SUPPORT_THRESHOLD: float = 0.35
    RAG_CONFLICT_DETECTION_ENABLED: bool = True

    # Database Settings
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "enterprise_doc_intelligence"
    DATABASE_URL: Optional[str] = None

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
