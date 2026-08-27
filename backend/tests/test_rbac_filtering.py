"""
Unit and Integration tests for True Pre-Retrieval RBAC & Multi-Tenant Isolation
(backend/tests/test_rbac_filtering.py).
Verifies that department isolation and clearance level filtering happen BEFORE
scoring and candidate selection in both BM25 and Qdrant, preventing top-K leakage.
"""
import uuid
import pytest
from backend.app.db.models.document import Document
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.schemas.retrieval import RetrievalFilter
from backend.app.services.bm25 import BM25IndexService
from backend.app.services.hybrid_retriever import HybridRetrievalService


@pytest.fixture
def bm25_rbac_service(tmp_path):
    """Provides an isolated BM25 index with multi-department test data."""
    service = BM25IndexService()
    service.clear()

    dept_hr = uuid.uuid4()
    dept_eng = uuid.uuid4()
    dept_legal = uuid.uuid4()

    # Document 1: HR Confidential (Clearance L3)
    doc_hr = Document(id=uuid.uuid4(), title="HR Executive Compensation", department_id=dept_hr)
    chunk_hr = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_hr.id,
        chunk_index=0,
        content="Executive bonus plan for 2026 performance targets compensation guidelines.",
        metadata_json={"clearance_level": 3, "department_id": str(dept_hr)},
    )

    # Document 2: Engineering Public (Clearance L1)
    doc_eng = Document(id=uuid.uuid4(), title="Engineering Architecture", department_id=dept_eng)
    chunk_eng = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_eng.id,
        chunk_index=0,
        content="Microservices platform architecture performance optimization guidelines.",
        metadata_json={"clearance_level": 1, "department_id": str(dept_eng)},
    )

    # Document 3: Legal Policy (Clearance L2)
    doc_legal = Document(id=uuid.uuid4(), title="Compliance Guidelines", department_id=dept_legal)
    chunk_legal = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_legal.id,
        chunk_index=0,
        content="Corporate legal policy compliance and employee regulatory guidelines.",
        metadata_json={"clearance_level": 2, "department_id": str(dept_legal)},
    )

    service.index_document_chunks(doc_hr, [chunk_hr], auto_persist=False)
    service.index_document_chunks(doc_eng, [chunk_eng], auto_persist=False)
    service.index_document_chunks(doc_legal, [chunk_legal], auto_persist=False)

    return {
        "service": service,
        "dept_hr": dept_hr,
        "dept_eng": dept_eng,
        "dept_legal": dept_legal,
        "doc_hr_id": doc_hr.id,
        "doc_eng_id": doc_eng.id,
        "doc_legal_id": doc_legal.id,
        "chunk_hr_id": chunk_hr.id,
        "chunk_eng_id": chunk_eng.id,
        "chunk_legal_id": chunk_legal.id,
    }


def test_bm25_pre_retrieval_department_filter(bm25_rbac_service):
    """Verifies that department pre-filtering prevents returning unauthorized department chunks."""
    env = bm25_rbac_service
    service: BM25IndexService = env["service"]

    # Query matching both HR and Engineering ('performance guidelines')
    # Search restricting only to Engineering department
    results = service.search(
        query="performance guidelines",
        limit=5,
        allowed_department_ids=[env["dept_eng"]],
    )

    assert len(results) == 1
    assert results[0].chunk_id == env["chunk_eng_id"]
    assert results[0].document_id == env["doc_eng_id"]


def test_bm25_pre_retrieval_clearance_filter(bm25_rbac_service):
    """Verifies that clearance pre-filtering excludes high-clearance chunks before scoring."""
    env = bm25_rbac_service
    service: BM25IndexService = env["service"]

    # Search with L1 clearance: only Engineering (L1) should be visible; HR (L3) and Legal (L2) blocked
    results_l1 = service.search(
        query="guidelines",
        limit=5,
        max_clearance_level=1,
    )
    chunk_ids_l1 = {r.chunk_id for r in results_l1}
    assert env["chunk_eng_id"] in chunk_ids_l1
    assert env["chunk_hr_id"] not in chunk_ids_l1
    assert env["chunk_legal_id"] not in chunk_ids_l1

    # Search with L2 clearance: Engineering (L1) and Legal (L2) visible; HR (L3) blocked
    results_l2 = service.search(
        query="guidelines",
        limit=5,
        max_clearance_level=2,
    )
    chunk_ids_l2 = {r.chunk_id for r in results_l2}
    assert env["chunk_eng_id"] in chunk_ids_l2
    assert env["chunk_legal_id"] in chunk_ids_l2
    assert env["chunk_hr_id"] not in chunk_ids_l2


def test_pre_retrieval_no_topk_starvation(bm25_rbac_service):
    """
    Verifies that pre-retrieval filtering returns the top-K authorized items without starvation.
    If HR has higher lexical match for 'compensation guidelines', pre-filtering on Engineering
    returns the top Engineering match rather than empty results.
    """
    env = bm25_rbac_service
    service: BM25IndexService = env["service"]

    # Engineering search with limit=1
    results = service.search(
        query="performance compensation guidelines",
        limit=1,
        allowed_department_ids=[env["dept_eng"]],
    )

    assert len(results) == 1
    assert results[0].chunk_id == env["chunk_eng_id"]


@pytest.mark.asyncio
async def test_hybrid_retrieval_with_rbac_filter(bm25_rbac_service):
    """Verifies end-to-end HybridRetrievalService applies pre-retrieval RBAC filters."""
    env = bm25_rbac_service
    hybrid = HybridRetrievalService(sparse_service=env["service"])

    # Filter with L1 clearance
    rbac_filter = RetrievalFilter(
        allowed_department_ids=[env["dept_eng"]],
        max_clearance_level=1,
    )

    response = await hybrid.retrieve(
        query="guidelines architecture",
        filter=rbac_filter,
    )

    for item in response.results:
        assert item.department_id == env["dept_eng"]
