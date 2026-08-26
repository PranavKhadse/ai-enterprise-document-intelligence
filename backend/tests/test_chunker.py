"""
Unit & Integration Tests for Structure-Aware Chunking & Metadata Enrichment.
"""
import json
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.db.base import Base
from backend.app.db.models import Document, DocumentChunk, DocumentVersion
from backend.app.schemas.chunk import ChunkingConfig
from backend.app.schemas.parser import ElementType, ParsedDocument, ParsedElement, ParsedPage
from backend.app.services.chunker import (
    ChunkingError,
    StructureAwareChunkerService,
    TableTooLargeError,
    chunker_service,
)


@pytest.fixture
def mock_document_id():
    return uuid.uuid4()


@pytest.fixture
def mock_version_id():
    return uuid.uuid4()


@pytest.fixture
def sample_parsed_document():
    """Generates a structured parsed document with multiple sections, tables, and paragraphs."""
    p1 = ParsedPage(
        page_number=1,
        width=595,
        height=842,
        elements=[
            ParsedElement(
                element_id="elem_h1_1",
                element_type=ElementType.HEADING_1,
                content="1. Corporate Leave Policy",
                page_number=1,
                section_path="Handbook > 1. Corporate Leave Policy",
            ),
            ParsedElement(
                element_id="elem_p_1",
                element_type=ElementType.PARAGRAPH,
                content="This policy defines all paid and unpaid leave entitlements for full-time employees.",
                page_number=1,
                section_path="Handbook > 1. Corporate Leave Policy",
                bbox=(50.0, 100.0, 500.0, 140.0),
            ),
            ParsedElement(
                element_id="elem_h2_1",
                element_type=ElementType.HEADING_2,
                content="1.1 Maternity Benefits",
                page_number=1,
                section_path="Handbook > 1. Corporate Leave Policy > 1.1 Maternity Benefits",
            ),
            ParsedElement(
                element_id="elem_p_2",
                element_type=ElementType.PARAGRAPH,
                content="Female employees are entitled to 26 weeks of paid maternity leave.",
                page_number=1,
                section_path="Handbook > 1. Corporate Leave Policy > 1.1 Maternity Benefits",
                bbox=(50.0, 160.0, 500.0, 200.0),
            ),
        ],
    )

    table_content = (
        "| Leave Type | Duration | Pay Percentage |\n"
        "| :--- | :--- | :--- |\n"
        "| Maternity | 26 Weeks | 100% |\n"
        "| Paternity | 4 Weeks | 100% |\n"
        "| Sick Leave | 12 Days | 100% |"
    )

    p2 = ParsedPage(
        page_number=2,
        width=595,
        height=842,
        elements=[
            ParsedElement(
                element_id="elem_tab_1",
                element_type=ElementType.TABLE,
                content=table_content,
                page_number=2,
                section_path="Handbook > 1. Corporate Leave Policy > 1.2 Summary Table",
                bbox=(50.0, 100.0, 500.0, 250.0),
            ),
            ParsedElement(
                element_id="elem_p_3",
                element_type=ElementType.PARAGRAPH,
                content="All leaves must be approved by the reporting manager through the HR portal.",
                page_number=2,
                section_path="Handbook > 1. Corporate Leave Policy > 1.3 Approval Workflow",
                bbox=(50.0, 280.0, 500.0, 320.0),
            ),
        ],
    )

    all_elems = p1.elements + p2.elements
    return ParsedDocument(
        total_pages=2,
        pages=[p1, p2],
        all_elements=all_elems,
        document_title="Employee Handbook",
    )


def test_basic_chunk_creation(sample_parsed_document, mock_document_id):
    """
    Test standard parsed document generates valid ChunkDTO objects.
    """
    chunks = chunker_service.create_chunks(sample_parsed_document, mock_document_id)

    assert len(chunks) > 0
    for i, chunk in enumerate(chunks):
        assert chunk.document_id == mock_document_id
        assert chunk.chunk_index == i
        assert chunk.token_count > 0
        assert chunk.token_count <= 512
        assert "[Context:" in chunk.content
        assert chunk.metadata.chunk_hash is not None


def test_strict_token_ceiling_512(sample_parsed_document, mock_document_id):
    """
    Asserts that EVERY generated chunk strictly satisfies tokens(content) <= 512.
    """
    # Create a document with huge paragraphs
    long_para = "This is a detailed corporate compliance sentence with important facts. " * 50
    parsed_doc = ParsedDocument(
        total_pages=1,
        pages=[
            ParsedPage(
                page_number=1,
                width=595,
                height=842,
                elements=[
                    ParsedElement(
                        element_id="long_1",
                        element_type=ElementType.PARAGRAPH,
                        content=long_para,
                        page_number=1,
                        section_path="Legal Policy > Compliance Obligations",
                    )
                ],
            )
        ],
        all_elements=[
            ParsedElement(
                element_id="long_1",
                element_type=ElementType.PARAGRAPH,
                content=long_para,
                page_number=1,
                section_path="Legal Policy > Compliance Obligations",
            )
        ],
        document_title="Legal Policy",
    )

    chunks = chunker_service.create_chunks(parsed_doc, mock_document_id)
    assert len(chunks) >= 2

    for chunk in chunks:
        tokens = chunker_service.count_tokens(chunk.content, "cl100k_base")
        assert tokens <= 512, f"Chunk exceeded 512 tokens: {tokens}"
        assert chunk.token_count == tokens


def test_overlap_does_not_cross_section_boundaries(mock_document_id):
    """
    Verifies overlap text is never carried across distinct section boundaries.
    """
    parsed_doc = ParsedDocument(
        total_pages=1,
        pages=[],
        all_elements=[
            ParsedElement(
                element_id="p1",
                element_type=ElementType.PARAGRAPH,
                content="First section body text defining confidential trade secrets.",
                page_number=1,
                section_path="Doc > Section 1",
            ),
            ParsedElement(
                element_id="p2",
                element_type=ElementType.PARAGRAPH,
                content="Second section body text defining patent licensing rules.",
                page_number=1,
                section_path="Doc > Section 2",
            ),
        ],
        document_title="Doc",
    )

    chunks = chunker_service.create_chunks(parsed_doc, mock_document_id)
    assert len(chunks) == 2

    # Chunk for Section 2 must NOT contain overlap text from Section 1
    assert "trade secrets" not in chunks[1].content
    assert "[... First section" not in chunks[1].content


def test_overlap_remains_within_512_ceiling(mock_document_id):
    """
    Verifies that overlap is truncated or omitted if adding it would push total tokens > 512.
    """
    long_para1 = "Sentence number one in section A with extensive descriptions. " * 30
    long_para2 = "Sentence number two in section A with additional crucial details. " * 30

    parsed_doc = ParsedDocument(
        total_pages=1,
        pages=[],
        all_elements=[
            ParsedElement(
                element_id="p1",
                element_type=ElementType.PARAGRAPH,
                content=long_para1,
                page_number=1,
                section_path="Doc > Section A",
            ),
            ParsedElement(
                element_id="p2",
                element_type=ElementType.PARAGRAPH,
                content=long_para2,
                page_number=1,
                section_path="Doc > Section A",
            ),
        ],
        document_title="Doc",
    )

    config = ChunkingConfig(target_size_tokens=400, max_size_tokens=512, overlap_tokens=50)
    chunks = chunker_service.create_chunks(parsed_doc, mock_document_id, config=config)

    for chunk in chunks:
        assert chunk.token_count <= 512


def test_table_integrity_never_split_mid_row(mock_document_id):
    """
    Verifies multi-row tables are split strictly between complete rows, never mid-row.
    """
    # Create a 20-row table
    rows = [f"| Item {i} | Value {i * 100} | Status Active |" for i in range(1, 21)]
    table_str = "| Item | Value | Status |\n| :--- | :--- | :--- |\n" + "\n".join(rows)

    parsed_doc = ParsedDocument(
        total_pages=1,
        pages=[],
        all_elements=[
            ParsedElement(
                element_id="tab1",
                element_type=ElementType.TABLE,
                content=table_str,
                page_number=1,
                section_path="Finance > Budget Breakdown",
            )
        ],
        document_title="Budget",
    )

    chunks = chunker_service.create_chunks(parsed_doc, mock_document_id)
    assert len(chunks) >= 1

    for chunk in chunks:
        # Every line in chunk table must start and end with '|'
        lines = [line.strip() for line in chunk.content.split("\n") if line.strip() and not line.startswith("[Context:")]
        for line in lines:
            assert line.startswith("|"), f"Malformed table row: {line}"
            assert line.endswith("|"), f"Malformed table row: {line}"


def test_table_continuation_repeats_headers(mock_document_id):
    """
    Verifies table continuation slices retain Markdown header syntax.
    """
    # Create a large 40-row table that forces multiple chunks
    rows = [f"| Long Item Name {i} | Category {i} | Subcategory {i} | Value {i * 500} |" for i in range(1, 40)]
    table_str = "| Item | Category | Subcategory | Value |\n| :--- | :--- | :--- | :--- |\n" + "\n".join(rows)

    parsed_doc = ParsedDocument(
        total_pages=1,
        pages=[],
        all_elements=[
            ParsedElement(
                element_id="big_tab",
                element_type=ElementType.TABLE,
                content=table_str,
                page_number=1,
                section_path="Inventory > Master Catalog",
            )
        ],
        document_title="Inventory",
    )

    config = ChunkingConfig(target_size_tokens=150, max_size_tokens=250)
    chunks = chunker_service.create_chunks(parsed_doc, mock_document_id, config=config)

    assert len(chunks) > 1

    for chunk in chunks:
        assert "| Item | Category | Subcategory | Value |" in chunk.content
        assert "| :--- | :--- | :--- | :--- |" in chunk.content


def test_table_header_exceeding_512_raises_error(mock_document_id):
    """
    Verifies that a massive table header + breadcrumb >= 512 raises TableTooLargeError.
    """
    massive_cols = [f"VeryLongColumnHeaderName_{i}" for i in range(150)]
    massive_header = "| " + " | ".join(massive_cols) + " |\n| " + " | ".join([":---"] * 150) + " |\n| row1 |"

    parsed_doc = ParsedDocument(
        total_pages=1,
        pages=[],
        all_elements=[
            ParsedElement(
                element_id="massive_tab",
                element_type=ElementType.TABLE,
                content=massive_header,
                page_number=1,
                section_path="Section > Super Wide Table",
            )
        ],
        document_title="Wide Table Doc",
    )

    with pytest.raises(TableTooLargeError):
        chunker_service.create_chunks(parsed_doc, mock_document_id)


def test_heading_only_sections_skip_empty_chunks(mock_document_id):
    """
    Verifies that pure heading elements are absorbed into breadcrumbs and do NOT create useless single-line chunks.
    """
    parsed_doc = ParsedDocument(
        total_pages=1,
        pages=[],
        all_elements=[
            ParsedElement(
                element_id="h1_only",
                element_type=ElementType.HEADING_1,
                content="Chapter 1: Introduction",
                page_number=1,
                section_path="Book > Chapter 1",
            ),
            ParsedElement(
                element_id="h2_only",
                element_type=ElementType.HEADING_2,
                content="1.1 Overview",
                page_number=1,
                section_path="Book > Chapter 1 > 1.1 Overview",
            ),
            # Only one paragraph in the whole doc
            ParsedElement(
                element_id="p1",
                element_type=ElementType.PARAGRAPH,
                content="This is the actual introductory text for chapter 1.",
                page_number=1,
                section_path="Book > Chapter 1 > 1.1 Overview",
            ),
        ],
        document_title="Book",
    )

    chunks = chunker_service.create_chunks(parsed_doc, mock_document_id)
    # Must produce exactly 1 chunk (not 3 chunks!)
    assert len(chunks) == 1
    assert "Book > Chapter 1 > 1.1 Overview" in chunks[0].content


def test_metadata_json_serializability(sample_parsed_document, mock_document_id):
    """
    Asserts metadata is strictly JSON-serializable.
    """
    chunks = chunker_service.create_chunks(sample_parsed_document, mock_document_id)
    for chunk in chunks:
        meta_dict = chunk.metadata.model_dump()
        json_str = json.dumps(meta_dict)
        assert json_str is not None
        assert "chunk_hash" in meta_dict
        assert "page_numbers" in meta_dict
        assert "token_count" in meta_dict


def test_deterministic_chunk_hash(sample_parsed_document, mock_document_id):
    """
    Asserts identical input produces identical chunk_hash values.
    """
    chunks_1 = chunker_service.create_chunks(sample_parsed_document, mock_document_id)
    chunks_2 = chunker_service.create_chunks(sample_parsed_document, mock_document_id)

    assert len(chunks_1) == len(chunks_2)
    for c1, c2 in zip(chunks_1, chunks_2):
        assert c1.metadata.chunk_hash == c2.metadata.chunk_hash


def test_configurable_tokenizer_encoding(sample_parsed_document, mock_document_id):
    """
    Verifies custom tokenizer encoding (e.g. cl100k_base) is respected.
    """
    config = ChunkingConfig(tokenizer_encoding="cl100k_base")
    chunks = chunker_service.create_chunks(sample_parsed_document, mock_document_id, config=config)
    assert len(chunks) > 0


def test_empty_parsed_document_returns_empty(mock_document_id):
    """
    Verifies empty parsed document returns [] cleanly.
    """
    parsed_doc = ParsedDocument(total_pages=0, pages=[], all_elements=[], document_title="Empty")
    chunks = chunker_service.create_chunks(parsed_doc, mock_document_id)
    assert chunks == []


@pytest.mark.asyncio
async def test_chunk_and_persist_db_integration(sample_parsed_document, mock_document_id):
    """
    Test transactional database persistence and rollback safety.
    """
    test_async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_async_session = async_sessionmaker(
        bind=test_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_async_session() as session:
        # Create parent document
        doc = Document(
            id=mock_document_id,
            title="Handbook",
            file_path="/tmp/handbook.pdf",
            file_hash="hash_123",
            file_type="pdf",
        )
        session.add(doc)
        await session.commit()

        # Persist chunks
        persisted = await chunker_service.chunk_and_persist(
            document_id=mock_document_id,
            parsed_doc=sample_parsed_document,
            version_id=None,
            db=session,
        )

        assert len(persisted) > 0

        # Query database directly
        stmt = select(DocumentChunk).where(DocumentChunk.document_id == mock_document_id)
        db_chunks = (await session.execute(stmt)).scalars().all()
        assert len(db_chunks) == len(persisted)

        # Idempotent rechunking test: calling it again replaces old chunks without duplication
        rechunked = await chunker_service.chunk_and_persist(
            document_id=mock_document_id,
            parsed_doc=sample_parsed_document,
            version_id=None,
            db=session,
        )
        db_chunks_after = (await session.execute(stmt)).scalars().all()
        assert len(db_chunks_after) == len(rechunked)

    await test_async_engine.dispose()


@pytest.mark.asyncio
async def test_version_isolation_during_persistence(sample_parsed_document, mock_document_id, mock_version_id):
    """
    Verifies rechunking version A leaves version B chunks intact.
    """
    test_async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_async_session = async_sessionmaker(
        bind=test_async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    version_2_id = uuid.uuid4()

    async with test_async_session() as session:
        doc = Document(
            id=mock_document_id,
            title="Handbook",
            file_path="/tmp/handbook.pdf",
            file_hash="hash_123",
            file_type="pdf",
        )
        session.add(doc)

        v1 = DocumentVersion(
            id=mock_version_id,
            document_id=mock_document_id,
            version_number="1.0.0",
            file_hash="hash_v1",
        )
        v2 = DocumentVersion(
            id=version_2_id,
            document_id=mock_document_id,
            version_number="2.0.0",
            file_hash="hash_v2",
        )
        session.add_all([v1, v2])
        await session.commit()

        # Persist chunks for Version 1
        await chunker_service.chunk_and_persist(
            document_id=mock_document_id,
            parsed_doc=sample_parsed_document,
            version_id=mock_version_id,
            db=session,
        )

        # Persist chunks for Version 2
        await chunker_service.chunk_and_persist(
            document_id=mock_document_id,
            parsed_doc=sample_parsed_document,
            version_id=version_2_id,
            db=session,
        )

        # Count total in DB (should be 2 * chunks)
        total_stmt = select(DocumentChunk).where(DocumentChunk.document_id == mock_document_id)
        total_chunks = (await session.execute(total_stmt)).scalars().all()

        v1_chunks = [c for c in total_chunks if c.version_id == mock_version_id]
        v2_chunks = [c for c in total_chunks if c.version_id == version_2_id]

        assert len(v1_chunks) > 0
        assert len(v2_chunks) > 0
        assert len(total_chunks) == len(v1_chunks) + len(v2_chunks)

        # Rechunk Version 1: Version 2 chunks must remain untouched
        await chunker_service.chunk_and_persist(
            document_id=mock_document_id,
            parsed_doc=sample_parsed_document,
            version_id=mock_version_id,
            db=session,
        )

        total_chunks_after = (await session.execute(total_stmt)).scalars().all()
        v2_chunks_after = [c for c in total_chunks_after if c.version_id == version_2_id]
        assert len(v2_chunks_after) == len(v2_chunks)

    await test_async_engine.dispose()
