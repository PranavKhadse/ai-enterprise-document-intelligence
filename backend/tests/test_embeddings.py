"""
Unit tests for Dense Embedding Service (FastEmbed).
"""
import numpy as np
import pytest
from backend.app.schemas.embedding import EmbeddingConfig
from backend.app.services.embedding import (
    EmbeddingDimensionError,
    FastEmbedEmbeddingService,
    embedding_service,
)


def test_embedding_dimension_and_normalization():
    """
    Verifies that generated embeddings have expected dimension (384) and L2 norm approx 1.0.
    """
    text = "The quick brown fox jumps over the lazy dog."
    vector = embedding_service.embed_text(text)

    assert isinstance(vector, list)
    assert len(vector) == 384

    # Check L2 normalization
    norm = np.linalg.norm(np.array(vector))
    assert pytest.approx(norm, rel=1e-3) == 1.0


def test_embedding_batch_consistency():
    """
    Verifies that single embedding matches batch embedding output for identical text.
    """
    texts = [
        "First document paragraph regarding leaves.",
        "Second document paragraph regarding reimbursement.",
    ]

    batch_vectors = embedding_service.embed_batch(texts)
    assert len(batch_vectors) == 2
    assert len(batch_vectors[0]) == 384
    assert len(batch_vectors[1]) == 384

    single_0 = embedding_service.embed_text(texts[0])
    single_1 = embedding_service.embed_text(texts[1])

    # Cosine similarity between single and batch vectors should be approx 1.0
    sim_0 = np.dot(np.array(single_0), np.array(batch_vectors[0]))
    sim_1 = np.dot(np.array(single_1), np.array(batch_vectors[1]))

    assert pytest.approx(sim_0, rel=1e-3) == 1.0
    assert pytest.approx(sim_1, rel=1e-3) == 1.0


def test_empty_string_embedding():
    """
    Verifies that empty string returns a zero vector without throwing an error.
    """
    zero_vec = embedding_service.embed_text("")
    assert len(zero_vec) == 384
    assert all(v == 0.0 for v in zero_vec)


def test_dimension_validation_mismatch():
    """
    Verifies that configuring an incorrect expected dimension raises EmbeddingDimensionError.
    """
    # Model produces 384-dim, but config expects 512-dim
    bad_config = EmbeddingConfig(
        provider="fastembed",
        model_name="BAAI/bge-small-en-v1.5",
        dimension=512,
    )
    bad_service = FastEmbedEmbeddingService(config=bad_config)

    with pytest.raises(EmbeddingDimensionError):
        bad_service.embed_text("Test sentence that should fail dimension check.")
