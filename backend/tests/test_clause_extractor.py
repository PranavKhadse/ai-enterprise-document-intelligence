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
