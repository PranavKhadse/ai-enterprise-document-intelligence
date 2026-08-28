import hashlib
import io
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.core.config import settings
from backend.app.db.base import Base
from backend.app.db.models import Department, Document
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.services.storage import LocalFileStorage, storage_service


@pytest.fixture
def mock_pdf_bytes():
    """Generates a valid mock PDF binary stream with %PDF- header."""
    return b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"


@pytest.fixture
async def document_test_env(tmp_path):
    """
    Sets up an isolated in-memory SQLite database and temporary storage directory
    for document upload testing.
    """
    # 1. Isolate Storage Service to temp directory
    test_storage = LocalFileStorage(base_dir=tmp_path / "uploads")
    original_base_dir = storage_service.base_dir
    storage_service.base_dir = test_storage.base_dir

    # 2. Isolate Database Engine
    test_async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_async_session = async_sessionmaker(
        bind=test_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Dependency override for FastAPI get_db
    async def override_get_db():
        async with test_async_session() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, test_async_session

    # Cleanup
    app.dependency_overrides.clear()
    storage_service.base_dir = original_base_dir
    await test_async_engine.dispose()


@pytest.mark.asyncio
async def test_upload_valid_pdf(document_test_env, mock_pdf_bytes):
    """
    Test uploading a valid PDF document.
    """
    client, _ = document_test_env
    expected_hash = hashlib.sha256(mock_pdf_bytes).hexdigest()

    files = {"file": ("test_policy.pdf", io.BytesIO(mock_pdf_bytes), "application/pdf")}
    data = {"title": "Company Policy 2026"}

    response = await client.post("/api/v1/documents/upload", files=files, data=data)

    assert response.status_code == 201
    res_data = response.json()
    assert res_data["title"] == "Company Policy 2026"
    assert res_data["file_hash"] == expected_hash
    assert res_data["file_type"] == "pdf"
    assert res_data["status"] == "uploaded"
    assert res_data["is_duplicate"] is False
    assert "id" in res_data
    assert "created_at" in res_data


@pytest.mark.asyncio
async def test_upload_duplicate_pdf(document_test_env, mock_pdf_bytes):
    """
    Test uploading the exact same PDF twice returns existing document metadata with status='already_exists'.
    """
    client, _ = document_test_env

    files1 = {"file": ("first_upload.pdf", io.BytesIO(mock_pdf_bytes), "application/pdf")}
    response1 = await client.post("/api/v1/documents/upload", files=files1)
    assert response1.status_code == 201
    doc1_id = response1.json()["id"]

    # Second upload with identical bytes
    files2 = {"file": ("second_upload.pdf", io.BytesIO(mock_pdf_bytes), "application/pdf")}
    response2 = await client.post("/api/v1/documents/upload", files=files2)

    assert response2.status_code == 200
    res2_data = response2.json()
    assert res2_data["id"] == doc1_id
    assert res2_data["status"] == "already_exists"
    assert res2_data["is_duplicate"] is True


@pytest.mark.asyncio
async def test_upload_unsupported_file_extension(document_test_env):
    """
    Test uploading a non-PDF file extension (e.g. .txt, .exe) is rejected with HTTP 400.
    """
    client, _ = document_test_env
    text_bytes = b"Hello, this is a plain text file."

    files = {"file": ("document.txt", io.BytesIO(text_bytes), "text/plain")}
    response = await client.post("/api/v1/documents/upload", files=files)

    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_spoofed_pdf_magic_bytes(document_test_env):
    """
    Test uploading a file named .pdf containing non-PDF bytes is rejected via magic byte inspection.
    """
    client, _ = document_test_env
    fake_pdf_bytes = b"NOT_A_PDF_HEADER: Malicious executable or plain text content"

    files = {"file": ("fake_file.pdf", io.BytesIO(fake_pdf_bytes), "application/pdf")}
    response = await client.post("/api/v1/documents/upload", files=files)

    assert response.status_code == 400
    assert "Invalid PDF content" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_empty_pdf(document_test_env):
    """
    Test uploading an empty 0-byte file is rejected with HTTP 400.
    """
    client, _ = document_test_env
    empty_bytes = b""

    files = {"file": ("empty.pdf", io.BytesIO(empty_bytes), "application/pdf")}
    response = await client.post("/api/v1/documents/upload", files=files)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_oversized_file(document_test_env):
    """
    Test uploading a file that exceeds MAX_UPLOAD_SIZE_BYTES is rejected with HTTP 413.
    """
    client, _ = document_test_env
    original_limit = settings.MAX_UPLOAD_SIZE_BYTES
    settings.MAX_UPLOAD_SIZE_BYTES = 50  # Set limit to 50 bytes for test

    try:
        large_bytes = b"%PDF-1.4\n" + b"A" * 100
        files = {"file": ("oversized.pdf", io.BytesIO(large_bytes), "application/pdf")}
        response = await client.post("/api/v1/documents/upload", files=files)

        assert response.status_code == 413
        assert "exceeds maximum permitted limit" in response.json()["detail"]
    finally:
        settings.MAX_UPLOAD_SIZE_BYTES = original_limit


@pytest.mark.asyncio
async def test_upload_with_department_association(document_test_env, mock_pdf_bytes):
    """
    Test uploading a PDF associated with a specific Department UUID.
    """
    client, session_factory = document_test_env

    # Pre-create a Department in database
    async with session_factory() as session:
        dept = Department(name="Legal Compliance", description="Legal Dept")
        session.add(dept)
        await session.commit()
        dept_id = dept.id

    files = {"file": ("compliance_doc.pdf", io.BytesIO(mock_pdf_bytes), "application/pdf")}
    data = {"department_id": str(dept_id), "title": "SOC2 Compliance Guide"}

    response = await client.post("/api/v1/documents/upload", files=files, data=data)

    assert response.status_code == 201
    res_data = response.json()
    assert res_data["department_id"] == str(dept_id)
    assert res_data["title"] == "SOC2 Compliance Guide"


@pytest.mark.asyncio
async def test_list_documents_pagination_and_filter(document_test_env, mock_pdf_bytes):
    """
    Test GET /api/v1/documents returns paginated list with total count and supports search filter.
    """
    client, _ = document_test_env

    # Upload 2 documents
    files1 = {"file": ("alpha_handbook.pdf", io.BytesIO(mock_pdf_bytes), "application/pdf")}
    await client.post("/api/v1/documents/upload", files=files1, data={"title": "Alpha Handbook"})

    files2 = {"file": ("beta_policy.pdf", io.BytesIO(mock_pdf_bytes + b" unique"), "application/pdf")}
    await client.post("/api/v1/documents/upload", files=files2, data={"title": "Beta Policy"})

    # List all
    res = await client.get("/api/v1/documents?limit=10&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Search filter
    search_res = await client.get("/api/v1/documents?query=Alpha")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total"] == 1
    assert search_data["items"][0]["title"] == "Alpha Handbook"


@pytest.mark.asyncio
async def test_get_document_detail_and_not_found(document_test_env, mock_pdf_bytes):
    """
    Test GET /api/v1/documents/{id} returns single document metadata and handles 404.
    """
    client, _ = document_test_env

    files = {"file": ("eng_runbook.pdf", io.BytesIO(mock_pdf_bytes), "application/pdf")}
    up_res = await client.post("/api/v1/documents/upload", files=files, data={"title": "Engineering Runbook"})
    doc_id = up_res.json()["id"]

    # Get valid
    get_res = await client.get(f"/api/v1/documents/{doc_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == doc_id
    assert get_res.json()["title"] == "Engineering Runbook"

    # Get non-existent
    non_existent = str(uuid.uuid4())
    nf_res = await client.get(f"/api/v1/documents/{non_existent}")
    assert nf_res.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_and_audit(document_test_env, mock_pdf_bytes):
    """
    Test DELETE /api/v1/documents/{id} removes document and returns success message.
    """
    client, _ = document_test_env

    files = {"file": ("deprecated_spec.pdf", io.BytesIO(mock_pdf_bytes), "application/pdf")}
    up_res = await client.post("/api/v1/documents/upload", files=files, data={"title": "Deprecated Spec"})
    doc_id = up_res.json()["id"]

    # Delete
    del_res = await client.delete(f"/api/v1/documents/{doc_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Verify document no longer exists
    nf_res = await client.get(f"/api/v1/documents/{doc_id}")
    assert nf_res.status_code == 404


@pytest.mark.asyncio
async def test_search_documents_endpoint(document_test_env):
    """
    Test POST /api/v1/documents/search returns HybridRetrievalResponse.
    """
    client, _ = document_test_env

    # Empty query rejected
    bad_res = await client.post("/api/v1/documents/search", json={"query": "  "})
    assert bad_res.status_code == 400

    # Valid search request
    search_res = await client.post("/api/v1/documents/search", json={"query": "security policy guidelines"})
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert "results" in search_data
    assert "diagnostics" in search_data
    assert search_data["diagnostics"]["query"] == "security policy guidelines"

