"""
Unit tests for ClauseAlignerService.
Verifies bipartite matching, resilience to renumbering/reordering, additions, removals,
and absence of phantom alignments below similarity thresholds.
"""
import pytest
from backend.app.services.clause_aligner import ClauseAlignerService, clause_aligner
from backend.app.services.clause_extractor import clause_extractor


def test_clause_aligner_identical_documents():
    """Verifies that identical documents align with 100% precision and similarity 1.0."""
    doc_text = """
# 1. Security
Multi-factor authentication is mandatory.

# 2. Storage
Backups are retained for 30 days.
"""
    clauses_a = clause_extractor.extract_from_markdown(doc_text, doc_prefix="a")
    clauses_b = clause_extractor.extract_from_markdown(doc_text, doc_prefix="b")

    alignments = clause_aligner.align_clauses(clauses_a, clauses_b)

    assert len(alignments) == 2
    assert alignments[0].clause_a is not None and alignments[0].clause_b is not None
    assert alignments[0].similarity_score >= 0.99
    assert alignments[1].similarity_score >= 0.99


def test_clause_aligner_renumbered_sections():
    """Verifies that clauses align accurately even when section numbers are shifted."""
    doc_a = """
# 1. Introduction
This document describes corporate guidelines.

# 2. Data Retention
All customer data must be retained for 30 days.
"""
    doc_b = """
# 1. Scope & Purpose
This document describes corporate guidelines.

# 2. Executive Summary
Overview of all company operations.

# 3. Data Retention
All customer data must be retained for 30 days.
"""
    clauses_a = clause_extractor.extract_from_markdown(doc_a, doc_prefix="a")
    clauses_b = clause_extractor.extract_from_markdown(doc_b, doc_prefix="b")

    alignments = clause_aligner.align_clauses(clauses_a, clauses_b)

    # We expect:
    # - Intro matched to Scope & Purpose
    # - Data Retention matched to Data Retention (even though section shifted from 2 to 3)
    # - Executive Summary is ADDED (unmatched)
    matched_pairs = [al for al in alignments if al.clause_a and al.clause_b]
    assert len(matched_pairs) == 2

    retention_match = next(al for al in matched_pairs if "Retention" in al.clause_a.section_path)
    assert retention_match.clause_b.section_path == "3. Data Retention"
    assert retention_match.similarity_score >= 0.95

    added_clauses = [al for al in alignments if al.clause_a is None and al.clause_b]
    assert len(added_clauses) == 1
    assert "Executive Summary" in added_clauses[0].clause_b.section_path


def test_clause_aligner_unmatched_low_similarity():
    """Verifies that completely disjoint clauses are left unmatched without phantom pairings."""
    doc_a = """
# 1. Legal Compliance
All contracts require review by legal counsel.
"""
    doc_b = """
# 1. Cafeteria Menu
Lunch is served from 12:00 to 14:00 daily.
"""
    clauses_a = clause_extractor.extract_from_markdown(doc_a, doc_prefix="a")
    clauses_b = clause_extractor.extract_from_markdown(doc_b, doc_prefix="b")

    alignments = clause_aligner.align_clauses(clauses_a, clauses_b, similarity_threshold=0.65)

    # Neither should match each other
    matched = [al for al in alignments if al.clause_a and al.clause_b]
    assert len(matched) == 0

    removed = [al for al in alignments if al.clause_a and al.clause_b is None]
    added = [al for al in alignments if al.clause_a is None and al.clause_b]
    assert len(removed) == 1
    assert len(added) == 1
