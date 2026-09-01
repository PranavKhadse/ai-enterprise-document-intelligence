"""
Unit tests for ClauseExtractorService.
Verifies heading hierarchy extraction, table preservation, normalization, and clause boundary detection.
"""
import pytest
from backend.app.services.clause_extractor import ClauseExtractorService, clause_extractor


def test_clause_extractor_heading_hierarchy():
    """Verifies breadcrumb hierarchy extraction from markdown headers."""
    md_text = """
# 1. Security Policy
## 1.1 Authentication
Multi-factor authentication is mandatory starting v2.4.0.

## 1.2 Password Rules
Passwords must be at least 16 characters.
"""
    clauses = clause_extractor.extract_from_markdown(md_text, doc_prefix="test")

    assert len(clauses) == 2
    assert clauses[0].section_path == "1. Security Policy > 1.1 Authentication"
    assert clauses[0].normalized_heading == "security policy > authentication"
    assert "Multi-factor authentication is mandatory" in clauses[0].raw_text

    assert clauses[1].section_path == "1. Security Policy > 1.2 Password Rules"
    assert clauses[1].normalized_heading == "security policy > password rules"


def test_clause_extractor_table_preservation():
    """Verifies that markdown tables are kept intact as cohesive table clauses."""
    md_text = """
# System Configuration
Here is the timeout matrix:

| Service | Timeout |
|---|---|
| Gateway | 5000ms |
| Auth | 2000ms |

After the table, regular operations resume.
"""
    clauses = clause_extractor.extract_from_markdown(md_text)

    assert len(clauses) == 3
    assert clauses[0].is_table is False
    assert clauses[1].is_table is True
    assert "| Gateway | 5000ms |" in clauses[1].raw_text
    assert clauses[2].is_table is False


def test_clause_extractor_normalization():
    """Verifies normalization preserves polarity terms and critical identifiers."""
    extractor = ClauseExtractorService()

    heading_norm = extractor.normalize_heading("Section 4.1.2: Backup Retention Policy")
    assert heading_norm == "backup retention policy"

    text_norm = extractor.normalize_text_for_comparison("**Mandatory** backup for 30 days under RFC-7519.")
    assert "mandatory" in text_norm
    assert "30 days" in text_norm
    assert "rfc-7519" in text_norm
    assert "**" not in text_norm


def test_clause_extractor_context_breadcrumbs_not_clauses():
    """Verifies that [Context: ...] breadcrumbs are treated as metadata and not emitted as clauses."""
    chunk_text = """
[Context: Enterprise_Security_Policy > 1. Information Security Principles]

Employees must protect company information against unauthorized access, alteration, disclosure, and loss.

[Context: Enterprise_Security_Policy > 3. Authentication & Password Rules]

Passwords must be at least 12 characters long and must not contain the user's email address.
"""
    clauses = clause_extractor.extract_from_markdown(chunk_text, doc_prefix="policy")

    assert len(clauses) == 2
    # Verify no [Context: ...] lines were emitted as clauses
    for c in clauses:
        assert not c.raw_text.startswith("[Context:")

    # Verify section paths were extracted from breadcrumbs
    assert clauses[0].section_path == "Enterprise_Security_Policy > 1. Information Security Principles"
    assert clauses[0].normalized_heading == "enterprise_security_policy > information security principles"
    assert "Employees must protect company information" in clauses[0].raw_text

    assert clauses[1].section_path == "Enterprise_Security_Policy > 3. Authentication & Password Rules"
    assert clauses[1].normalized_heading == "enterprise_security_policy > authentication & password rules"
    assert "Passwords must be at least 12 characters" in clauses[1].raw_text


def test_clause_extractor_plain_text_section_headings():
    """Verifies that plain-text section headings like 'Section 1: ...' are treated as headings, not clauses."""
    doc_text = """
Section 1: Access Control

All corporate documents must be stored in encrypted repositories with multi-factor authentication enforced.

Section 2: Data Classification

Customer records and financial reports are classified as Confidential.

Section 3: Authentication & Password Rules

Passwords must be at least 16 characters.
"""
    clauses = clause_extractor.extract_from_markdown(doc_text, doc_prefix="sec")

    assert len(clauses) == 3
    # Headings must not be standalone clauses
    for c in clauses:
        assert not c.raw_text.startswith("Section ")

    # Section paths must reflect the plain-text headings
    assert clauses[0].section_path == "Section 1: Access Control"
    assert clauses[0].normalized_heading == "access control"
    assert "All corporate documents must be stored" in clauses[0].raw_text

    assert clauses[1].section_path == "Section 2: Data Classification"
    assert clauses[1].normalized_heading == "data classification"
    assert "Customer records and financial reports" in clauses[1].raw_text

    assert clauses[2].section_path == "Section 3: Authentication & Password Rules"
    assert clauses[2].normalized_heading == "authentication & password rules"
    assert "Passwords must be at least 16 characters." in clauses[2].raw_text


def test_clause_extractor_top_of_document_title_not_clause():
    """Verifies that top-level document title lines before section headings are treated as title context, not body clauses."""
    doc_text = """
Enterprise Security Policy 2026

Section 1: Access Control

All corporate documents must be stored in encrypted repositories with multi-factor authentication enforced.
"""
    clauses = clause_extractor.extract_from_markdown(doc_text, doc_prefix="doc_a")

    assert len(clauses) == 1
    assert not clauses[0].raw_text.startswith("Enterprise Security Policy")
    assert "All corporate documents must be stored" in clauses[0].raw_text
    assert clauses[0].is_metadata is False


def test_clause_extractor_document_metadata_identification():
    """Verifies that administrative metadata blocks are flagged with is_metadata=True."""
    meta_text = """
Policy owner: Enterprise Security Team. Review cycle: every 12 months or after a major security incident. Current version: 2.1.
"""
    clauses = clause_extractor.extract_from_markdown(meta_text, doc_prefix="meta")

    assert len(clauses) == 1
    assert clauses[0].is_metadata is True
    assert "Policy owner:" in clauses[0].raw_text
