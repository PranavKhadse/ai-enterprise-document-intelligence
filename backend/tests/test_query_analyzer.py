"""
Unit tests for QueryAnalyzer heuristic intent classification and parameter tuning.
"""
import pytest
from backend.app.schemas.retrieval import QueryType
from backend.app.services.query_analyzer import QueryAnalyzer


@pytest.fixture
def analyzer():
    return QueryAnalyzer()


def test_exact_identifier_classification(analyzer):
    """
    Verifies that technical codes, standards, and enterprise IDs trigger EXACT_IDENTIFIER
    with higher sparse weights.
    """
    queries = [
        "What is specified in RFC-4821?",
        "compliance with ISO-9001 standard",
        "System raised error_500 in backend",
        "Update dependency to v2.1.0",
        "Core algorithm implemented in C++",
        "Filing tax Form W-2 requirements",
        "Review Clause_3.1 in vendor contract",
    ]

    for q in queries:
        q_type, dense_w, sparse_w, pool_mult = analyzer.analyze_query(q)
        assert q_type == QueryType.EXACT_IDENTIFIER, f"Failed for query: {q}"
        assert sparse_w > dense_w
        assert pool_mult > 1.0


def test_semantic_question_classification(analyzer):
    """
    Verifies that natural language questions trigger SEMANTIC_QUESTION with higher dense weights.
    """
    queries = [
        "How do I submit an expense reimbursement?",
        "Why is data retention mandated for 7 years?",
        "Where can employees find company leave guidelines?",
        "Explain the performance evaluation workflow",
        "Can a full-time contractor request parental leave?",
    ]

    for q in queries:
        q_type, dense_w, sparse_w, pool_mult = analyzer.analyze_query(q)
        assert q_type == QueryType.SEMANTIC_QUESTION, f"Failed for query: {q}"
        assert dense_w > sparse_w


def test_keyword_search_classification(analyzer):
    """
    Verifies that short non-question queries trigger KEYWORD_SEARCH.
    """
    queries = [
        "maternity leave",
        "travel policy",
        "health insurance",
        "vacation days",
    ]

    for q in queries:
        q_type, dense_w, sparse_w, pool_mult = analyzer.analyze_query(q)
        assert q_type == QueryType.KEYWORD_SEARCH, f"Failed for query: {q}"
        assert sparse_w >= dense_w


def test_empty_query_analysis(analyzer):
    """
    Verifies that empty string or whitespace does not crash the analyzer.
    """
    q_type, dense_w, sparse_w, pool_mult = analyzer.analyze_query("")
    assert q_type == QueryType.KEYWORD_SEARCH
    assert pool_mult == 1.0
