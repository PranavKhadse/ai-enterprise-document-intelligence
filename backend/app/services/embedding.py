"""
Dense Embeddings Service using FastEmbed (ONNX Runtime).
Generates L2-normalized dense semantic vectors with batching and dimension validation.
"""
from typing import List, Optional
import numpy as np
from fastembed import TextEmbedding
from backend.app.core.config import settings
from backend.app.schemas.embedding import EmbeddingConfig


class EmbeddingError(Exception):
    """Base exception for embedding operations."""
    pass


class EmbeddingDimensionError(EmbeddingError):
    """Raised when generated embedding vector does not match expected dimension."""
    pass


class EmbeddingService:
    """
    Abstract interface for dense embedding generation.
    """

    def embed_text(self, text: str) -> List[float]:
        raise NotImplementedError

    def embed_batch(self, texts: List[str], batch_size: Optional[int] = None) -> List[List[float]]:
        raise NotImplementedError

    @property
    def dimension(self) -> int:
        raise NotImplementedError


class FastEmbedEmbeddingService(EmbeddingService):
    """
    FastEmbed implementation powered by ONNX Runtime.
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig(
            provider=settings.EMBEDDING_PROVIDER,
            model_name=settings.EMBEDDING_MODEL_NAME,
            dimension=settings.EMBEDDING_DIMENSION,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
        )
        self._model: Optional[TextEmbedding] = None

    def _get_model(self) -> TextEmbedding:
        if self._model is None:
            try:
                self._model = TextEmbedding(model_name=self.config.model_name)
            except Exception as e:
                raise EmbeddingError(f"Failed to load embedding model '{self.config.model_name}': {str(e)}")
        return self._model

    @property
    def dimension(self) -> int:
        return self.config.dimension

    def embed_text(self, text: str) -> List[float]:
        """
        Generates an L2-normalized embedding vector for a single text passage.
        """
        if not text or not text.strip():
            # Return zero vector if empty
            return [0.0] * self.dimension

        results = self.embed_batch([text], batch_size=1)
        return results[0]

    def embed_batch(self, texts: List[str], batch_size: Optional[int] = None) -> List[List[float]]:
        """
        Generates L2-normalized embeddings for a list of text passages in batches.
        """
        if not texts:
            return []

        bs = batch_size or self.config.batch_size
        model = self._get_model()

        try:
            # fastembed embed() yields numpy arrays
            raw_embeddings = list(model.embed(texts, batch_size=bs))
        except Exception as e:
            raise EmbeddingError(f"Batch embedding generation failed: {str(e)}")

        normalized_vectors: List[List[float]] = []
        for i, vec in enumerate(raw_embeddings):
            # Convert to numpy array if needed
            np_vec = np.array(vec, dtype=np.float32)
            norm = np.linalg.norm(np_vec)
            if norm > 0:
                np_vec = np_vec / norm

            if len(np_vec) != self.dimension:
                raise EmbeddingDimensionError(
                    f"Vector dimension mismatch at index {i}: expected {self.dimension}, got {len(np_vec)}"
                )

            normalized_vectors.append(np_vec.tolist())

        return normalized_vectors


# Global embedding service singleton
embedding_service = FastEmbedEmbeddingService()
