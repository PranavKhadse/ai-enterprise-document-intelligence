import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.app.db.base import Base
from backend.app.db.models import (
    Department,
    Role,
    UserRole,
    User,
    Document,
    DocumentVersion,
    DocumentChunk,
    QueryLog,
    EvaluationResult,
)


def test_metadata_tables_registered():
    """
    Verify all 9 expected database tables are properly registered in SQLAlchemy Base.metadata.
    """
    expected_tables = {
        "departments",
        "users",
        "roles",
        "user_roles",
        "documents",
        "document_versions",
        "document_chunks",
        "query_logs",
        "evaluation_results",
    }
    registered_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(registered_tables), (
        f"Missing tables: {expected_tables - registered_tables}"
    )


def test_foreign_key_definitions():
    """
    Verify foreign keys, cascading configurations, and target columns across all models.
    """
    tables = Base.metadata.tables

    # users -> departments
    user_fks = tables["users"].foreign_keys
    assert any(fk.target_fullname == "departments.id" for fk in user_fks)
    assert any(fk.ondelete == "SET NULL" for fk in user_fks)

    # user_roles -> users, roles
    user_role_fks = tables["user_roles"].foreign_keys
    assert any(fk.target_fullname == "users.id" for fk in user_role_fks)
    assert any(fk.target_fullname == "roles.id" for fk in user_role_fks)

    # documents -> departments
    doc_fks = tables["documents"].foreign_keys
    assert any(fk.target_fullname == "departments.id" for fk in doc_fks)

    # document_versions -> documents
    ver_fks = tables["document_versions"].foreign_keys
    assert any(fk.target_fullname == "documents.id" for fk in ver_fks)
    assert any(fk.ondelete == "CASCADE" for fk in ver_fks)

    # document_chunks -> documents, document_versions
    chunk_fks = tables["document_chunks"].foreign_keys
    assert any(fk.target_fullname == "documents.id" for fk in chunk_fks)
    assert any(fk.target_fullname == "document_versions.id" for fk in chunk_fks)
    assert all(fk.ondelete == "CASCADE" for fk in chunk_fks)

    # query_logs -> users
    ql_fks = tables["query_logs"].foreign_keys
    assert any(fk.target_fullname == "users.id" for fk in ql_fks)

    # evaluation_results -> query_logs
    eval_fks = tables["evaluation_results"].foreign_keys
    assert any(fk.target_fullname == "query_logs.id" for fk in eval_fks)
    assert any(fk.ondelete == "CASCADE" for fk in eval_fks)


def test_unique_constraints():
    """
    Verify unique columns and composite constraints.
    """
    tables = Base.metadata.tables

    # Unique columns
    assert tables["departments"].columns["name"].unique is True
    assert tables["roles"].columns["name"].unique is True
    assert tables["users"].columns["email"].unique is True

    # Composite UniqueConstraint on user_roles (user_id, role_id)
    user_roles_uqs = tables["user_roles"].constraints
    composite_uqs = [
        c for c in user_roles_uqs
        if hasattr(c, "columns") and {col.name for col in c.columns} == {"user_id", "role_id"}
    ]
    assert len(composite_uqs) > 0


@pytest.mark.asyncio
async def test_async_database_lifecycle_and_relationships():
    """
    Test end-to-end model instantiation, relationship navigation, and bidirectional linking.
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
        # 1. Department + User + Role + UserRole
        hr_dept = Department(name="Human Resources", description="HR and Talent Department")
        session.add(hr_dept)
        await session.flush()

        admin_role = Role(name="Admin", description="Platform Administrator")
        session.add(admin_role)
        await session.flush()

        user = User(
            email="admin.hr@enterprise.local",
            hashed_password="argon2_hashed_secret_123",
            department_id=hr_dept.id,
            is_active=True,
        )
        user.roles.append(admin_role)
        session.add(user)
        await session.flush()

        # 2. Document + Version + Chunk
        doc = Document(
            title="Global Leave Policy 2026",
            file_path="/storage/docs/leave_policy_2026.pdf",
            file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            file_type="pdf",
            total_pages=15,
            department_id=hr_dept.id,
            current_version="1.0.0",
        )
        session.add(doc)
        await session.flush()

        version = DocumentVersion(
            document_id=doc.id,
            version_number="1.0.0",
            file_hash=doc.file_hash,
        )
        session.add(version)
        await session.flush()

        chunk_1 = DocumentChunk(
            document_id=doc.id,
            version_id=version.id,
            chunk_index=0,
            content="Employees are entitled to 20 days of paid annual leave.",
            metadata_json={"section": "Annual Leave", "tags": ["leave", "hr"]},
            page_number=1,
            section_path="Leave Policy > Section 1 > Annual Leave",
            token_count=12,
        )
        session.add(chunk_1)
        await session.flush()

        # 3. QueryLog + EvaluationResult
        query_log = QueryLog(
            user_id=user.id,
            raw_query="How many annual leave days do employees receive?",
            rewritten_query="Global Leave Policy Annual Leave entitlement days",
            retrieved_chunk_ids=[str(chunk_1.id)],
            llm_response="Employees receive 20 days of paid annual leave.",
            latency_ms=245.5,
            prompt_tokens=320,
            completion_tokens=15,
            estimated_cost_usd=0.00045,
        )
        session.add(query_log)
        await session.flush()

        eval_res = EvaluationResult(
            query_log_id=query_log.id,
            faithfulness_score=1.0,
            answer_relevance_score=0.98,
            context_precision_score=1.0,
            evaluation_model="gpt-4o",
        )
        session.add(eval_res)
        await session.commit()

        # 4. Verify Queries and Bidirectional Relationships
        stmt = select(User).where(User.email == "admin.hr@enterprise.local")
        result = await session.execute(stmt)
        queried_user = result.scalar_one()

        assert queried_user.department is not None
        assert queried_user.department.name == "Human Resources"
        assert len(queried_user.roles) == 1
        assert queried_user.roles[0].name == "Admin"

        # Verify Document & Chunk relationship
        doc_stmt = select(Document).where(Document.id == doc.id)
        doc_result = await session.execute(doc_stmt)
        queried_doc = doc_result.scalar_one()
        assert len(queried_doc.versions) == 1
        assert len(queried_doc.chunks) == 1
        assert queried_doc.chunks[0].page_number == 1
        assert queried_doc.chunks[0].metadata_json["section"] == "Annual Leave"

        # Verify QueryLog & Evaluation relationship
        ql_stmt = select(QueryLog).where(QueryLog.id == query_log.id)
        ql_result = await session.execute(ql_stmt)
        queried_ql = ql_result.scalar_one()
        assert len(queried_ql.evaluations) == 1
        assert queried_ql.evaluations[0].faithfulness_score == 1.0

    await test_async_engine.dispose()


@pytest.mark.asyncio
async def test_cascading_deletes():
    """
    Test that deleting parent records (Document, QueryLog) properly cascades to child records.
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
        # Create Document with Version and Chunk
        doc = Document(
            title="Deletable Document",
            file_path="/storage/test.pdf",
            file_hash="hash123",
            file_type="pdf",
        )
        session.add(doc)
        await session.flush()

        ver = DocumentVersion(document_id=doc.id, version_number="1.0.0", file_hash="hash123")
        session.add(ver)
        await session.flush()

        chunk = DocumentChunk(
            document_id=doc.id,
            version_id=ver.id,
            chunk_index=0,
            content="Sample text",
            metadata_json={},
        )
        session.add(chunk)
        await session.commit()

        # Delete the Document
        await session.delete(doc)
        await session.commit()

        # Verify Document, Versions, and Chunks are gone
        remaining_docs = (await session.execute(select(Document))).scalars().all()
        remaining_vers = (await session.execute(select(DocumentVersion))).scalars().all()
        remaining_chunks = (await session.execute(select(DocumentChunk))).scalars().all()

        assert len(remaining_docs) == 0
        assert len(remaining_vers) == 0
        assert len(remaining_chunks) == 0

    await test_async_engine.dispose()
