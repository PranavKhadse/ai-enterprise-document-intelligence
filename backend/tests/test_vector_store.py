"""
Unit and Integration tests for Qdrant Vector Store Service using ephemeral in-memory client.
"""
import uuid
import pytest
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from backend.app.schemas.embedding import VectorSearchResult
from backend.app.services.vector_store import (
    VectorDimensionMismatchError,
    VectorStoreService,
)


@pytest.fixture
def in_memory_qdrant():
    """Provides an isolated in-memory QdrantClient instance."""
    return QdrantClient(location=":memory:")


@pytest.fixture
def vector_service(in_memory_qdrant):
    """Provides a VectorStoreService bound to the isolated in-memory client."""
    return VectorStoreService(client=in_memory_qdrant, collection_name="test_collection")


def test_qdrant_collection_lifecycle(vector_service, in_memory_qdrant):
    """
    Verifies that ensure_collection creates a collection with 384 dimensions and Cosine distance.
    """
    vector_service.ensure_collection(dimension=384)

    assert in_memory_qdrant.collection_exists("test_collection")
    info = in_memory_qdrant.get_collection("test_collection")
    assert info.config.params.vectors.size == 384
    assert info.config.params.vectors.distance == Distance.COSINE


def test_dimension_mismatch_error_handling(in_memory_qdrant):
    """
    Verifies that attempting to use a 384-dim service with an existing 768-dim collection raises VectorDimensionMismatchError.
    """
    # Create 768-dim collection manually
    in_memory_qdrant.create_collection(
        collection_name="mismatched_collection",
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )

    svc = VectorStoreService(client=in_memory_qdrant, collection_name="mismatched_collection")

    with pytest.raises(VectorDimensionMismatchError):
        svc.ensure_collection(dimension=384)


def test_idempotent_point_upserts(vector_service, in_memory_qdrant):
    """
    Verifies that upserting points with the same ID overwrites rather than creating duplicate points.
    """
    chunk_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())

    dummy_vector = [0.1] * 384
    point_1 = PointStruct(
        id=chunk_id,
        vector=dummy_vector,
        payload={"document_id": doc_id, "content": "Initial version text."},
    )

    vector_service.upsert_points([point_1], dimension=384)
    count_1 = in_memory_qdrant.count("test_collection").count
    assert count_1 == 1

    # Upsert again with updated payload
    point_2 = PointStruct(
        id=chunk_id,
        vector=dummy_vector,
        payload={"document_id": doc_id, "content": "Updated version text."},
    )
    vector_service.upsert_points([point_2], dimension=384)
    count_2 = in_memory_qdrant.count("test_collection").count
    assert count_2 == 1  # Must still be exactly 1 point

    # Verify content was updated
    search_res = vector_service.search_vectors(query_vector=dummy_vector, limit=1)
    assert len(search_res) == 1
    assert search_res[0].content == "Updated version text."


def test_vector_similarity_search_and_filtering(vector_service):
    """
    Verifies vector search and payload filtering by department_id and document_id.
    """
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    dept_hr = uuid.uuid4()
    dept_eng = uuid.uuid4()

    # Create vectors
    vec_hr = [1.0] + [0.0] * 383
    vec_eng = [0.0, 1.0] + [0.0] * 382

    p_hr = PointStruct(
        id=str(uuid.uuid4()),
        vector=vec_hr,
        payload={
            "document_id": str(doc_a),
            "department_id": str(dept_hr),
            "content": "HR policy on annual leave.",
            "section_path": "HR > Leave",
        },
    )
    p_eng = PointStruct(
        id=str(uuid.uuid4()),
        vector=vec_eng,
        payload={
            "document_id": str(doc_b),
            "department_id": str(dept_eng),
            "content": "Engineering SOP on deployment.",
            "section_path": "Eng > Deployment",
        },
    )

    vector_service.upsert_points([p_hr, p_eng], dimension=384)

    # Search with HR query vector
    hits = vector_service.search_vectors(query_vector=vec_hr, limit=2)
    assert len(hits) == 2
    assert hits[0].content == "HR policy on annual leave."

    # Filter strictly by department_id
    filtered_hits = vector_service.search_vectors(
        query_vector=vec_hr,
        department_id=dept_eng,
        limit=2,
    )
    assert len(filtered_hits) == 1
    assert filtered_hits[0].content == "Engineering SOP on deployment."


def test_version_isolation_in_vector_store(vector_service, in_memory_qdrant):
    """
    Verifies that deleting points for Version 1 leaves Version 2 points intact.
    """
    doc_id = uuid.uuid4()
    v1_id = uuid.uuid4()
    v2_id = uuid.uuid4()

    dummy_vector = [0.2] * 384

    p_v1 = PointStruct(
        id=str(uuid.uuid4()),
        vector=dummy_vector,
        payload={"document_id": str(doc_id), "version_id": str(v1_id), "content": "Version 1"},
    )
    p_v2 = PointStruct(
        id=str(uuid.uuid4()),
        vector=dummy_vector,
        payload={"document_id": str(doc_id), "version_id": str(v2_id), "content": "Version 2"},
    )

    vector_service.upsert_points([p_v1, p_v2], dimension=384)
    assert in_memory_qdrant.count("test_collection").count == 2

    # Delete Version 1
    vector_service.delete_by_version(document_id=doc_id, version_id=v1_id)

    assert in_memory_qdrant.count("test_collection").count == 1
    remaining = vector_service.search_vectors(query_vector=dummy_vector, limit=5)
    assert len(remaining) == 1
    assert remaining[0].version_id == v2_id
