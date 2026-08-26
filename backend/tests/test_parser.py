import io
import uuid
import fitz  # PyMuPDF
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.db.base import Base
from backend.app.db.models import Document
from backend.app.schemas.parser import ElementType, ParsedDocument
from backend.app.services.parser import (
    CorruptedPDFError,
    EmptyDocumentError,
    EncryptedPDFError,
    PDFParserService,
    parser_service,
)


@pytest.fixture
def sample_multi_page_pdf():
    """Generates a 3-page in-memory PDF."""
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 100), f"Page {i + 1} header content", fontsize=16)
        page.insert_text((50, 140), f"This is body text on page {i + 1}.", fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def sample_structured_pdf():
    """Generates a PDF with H1, H2, H3, and body text."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Mode body font = 10pt
    # H1 = 16pt (1.6x)
    page.insert_text((50, 80), "1. Leave and Absence Policy", fontsize=16)
    # H2 = 13pt (1.3x)
    page.insert_text((50, 120), "1.1 Parental Support Benefits", fontsize=13)
    # H3 = 12pt (1.2x) with bold styling
    page.insert_text((50, 160), "1.1.1 Paternity Leave Duration", fontsize=12, fontname="helv")
    # Body text = 10pt
    page.insert_text((50, 190), "Employees are entitled to 20 working days of paternity leave.", fontsize=10)
    page.insert_text((50, 220), "Leave must be taken within 12 months of birth or adoption.", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def sample_bold_body_pdf():
    """Generates a PDF with normal bold sentences at standard body font size (10pt)."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # 10pt standard body text
    page.insert_text((50, 80), "Standard regular text describing the corporate office hours.", fontsize=10)
    # 10pt bold sentence that should NOT be misclassified as a heading
    page.insert_text(
        (50, 110),
        "IMPORTANT NOTICE: All employees must submit their weekly timesheets before Friday 5 PM.",
        fontsize=10,
    )
    page.insert_text((50, 140), "Another regular sentence following the important notice.", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def sample_two_column_pdf():
    """Generates a 2-column layout PDF."""
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)

    # Top banner header across both columns
    page.insert_text((50, 60), "Annual Engineering Report 2026", fontsize=18)

    # Left Column (x=50 to x=250)
    page.insert_text((50, 120), "Left Column Section A: Core Infrastructure", fontsize=13)
    page.insert_text((50, 160), "We migrated to Kubernetes clusters and microservices.", fontsize=10)
    page.insert_text((50, 200), "Database query latencies dropped by 45 percent.", fontsize=10)

    # Right Column (x=350 to x=550)
    page.insert_text((350, 120), "Right Column Section B: Quality Assurance", fontsize=13)
    page.insert_text((350, 160), "Automated integration testing reached 92 percent coverage.", fontsize=10)
    page.insert_text((350, 200), "Release velocity doubled over the previous quarter.", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def sample_encrypted_pdf():
    """Generates a password-protected PDF."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 100), "Confidential Executive Document", fontsize=14)
    # Save with encryption
    pdf_bytes = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret123")
    doc.close()
    return pdf_bytes


def test_parse_multi_page_pdf(sample_multi_page_pdf):
    """
    Test page counting and 1-indexed page numbering across a 3-page document.
    """
    parsed_doc = parser_service.parse_bytes(sample_multi_page_pdf, document_title="Employee Handbook")

    assert isinstance(parsed_doc, ParsedDocument)
    assert parsed_doc.total_pages == 3
    assert len(parsed_doc.pages) == 3

    for i, page in enumerate(parsed_doc.pages):
        assert page.page_number == i + 1
        assert len(page.elements) > 0
        for elem in page.elements:
            assert elem.page_number == i + 1


def test_heading_hierarchy_and_breadcrumbs(sample_structured_pdf):
    """
    Test that H1, H2, H3 headings are detected and breadcrumb paths are constructed correctly.
    """
    parsed_doc = parser_service.parse_bytes(sample_structured_pdf, document_title="Leave Policy")

    elements = parsed_doc.all_elements
    types = [e.element_type for e in elements]

    assert ElementType.HEADING_1 in types
    assert ElementType.HEADING_2 in types
    assert ElementType.HEADING_3 in types
    assert ElementType.PARAGRAPH in types

    # Check paragraph breadcrumb inheritance
    paragraphs = [e for e in elements if e.element_type == ElementType.PARAGRAPH]
    assert len(paragraphs) >= 1
    assert "Leave Policy" in paragraphs[0].section_path
    assert "1. Leave and Absence Policy" in paragraphs[0].section_path
    assert "1.1 Parental Support Benefits" in paragraphs[0].section_path


def test_bold_body_text_safeguard(sample_bold_body_pdf):
    """
    Test that bold sentences at body font size are NOT misclassified as headings.
    """
    parsed_doc = parser_service.parse_bytes(sample_bold_body_pdf, document_title="Notice")

    elements = parsed_doc.all_elements
    notice_element = next(
        (e for e in elements if "IMPORTANT NOTICE" in e.content), None
    )

    assert notice_element is not None
    # Must be classified as PARAGRAPH, NOT HEADING_3
    assert notice_element.element_type == ElementType.PARAGRAPH


def test_two_column_reading_order(sample_two_column_pdf):
    """
    Test that multi-column layouts read left column top-to-bottom first, then right column.
    """
    parsed_doc = parser_service.parse_bytes(sample_two_column_pdf, document_title="Tech Report")

    texts = [e.content for e in parsed_doc.all_elements]
    full_text_sequence = " ".join(texts)

    # Left column text must appear before right column text in sequence
    left_pos = full_text_sequence.find("Left Column Section A")
    right_pos = full_text_sequence.find("Right Column Section B")

    assert left_pos != -1
    assert right_pos != -1
    assert left_pos < right_pos, "Left column must be read before right column"


def test_encrypted_pdf_rejection(sample_encrypted_pdf):
    """
    Test that encrypted/password-protected PDFs raise EncryptedPDFError.
    """
    with pytest.raises(EncryptedPDFError):
        parser_service.parse_bytes(sample_encrypted_pdf)


def test_corrupted_pdf_rejection():
    """
    Test that corrupted/malformed binary streams raise CorruptedPDFError.
    """
    garbage_bytes = b"%PDF-1.4\nMaliciousCorruptPayload\x00\xff\xfe\x01\x02\x03\x04"
    with pytest.raises(CorruptedPDFError):
        parser_service.parse_bytes(garbage_bytes)


def test_empty_document_rejection():
    """
    Test that empty 0-byte payload raises EmptyDocumentError.
    """
    with pytest.raises(EmptyDocumentError):
        parser_service.parse_bytes(b"")


def test_parser_service_api_interface(sample_structured_pdf):
    """
    Test that ParsedDocument provides clean interface ready for Phase 3 chunking.
    """
    parsed_doc = parser_service.parse_bytes(sample_structured_pdf, document_title="Policy Guide")

    assert parsed_doc.total_pages == 1
    assert parsed_doc.document_title == "Policy Guide"
    assert len(parsed_doc.all_elements) > 0

    for elem in parsed_doc.all_elements:
        assert elem.page_number == 1
        assert elem.content is not None
        assert elem.section_path is not None
        assert elem.bbox is not None


@pytest.mark.asyncio
async def test_parse_and_update_document_db_integration(tmp_path, sample_multi_page_pdf):
    """
    Test parse_and_update_document() updates Document.total_pages in PostgreSQL.
    """
    # Setup in-memory SQLite async database
    test_async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_async_session = async_sessionmaker(
        bind=test_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Save PDF to tmp file
    pdf_path = tmp_path / "handbook.pdf"
    pdf_path.write_bytes(sample_multi_page_pdf)

    async with test_async_session() as session:
        # Create Document without total_pages
        doc = Document(
            title="Handbook 2026",
            file_path=str(pdf_path),
            file_hash="dummy_hash_123",
            file_type="pdf",
            total_pages=None,
        )
        session.add(doc)
        await session.commit()
        doc_id = doc.id

        # Execute parser service DB helper
        parsed = await parser_service.parse_and_update_document(doc_id, session)

        assert parsed.total_pages == 3

        # Verify DB record was updated
        updated_doc = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one()
        assert updated_doc.total_pages == 3

    await test_async_engine.dispose()
