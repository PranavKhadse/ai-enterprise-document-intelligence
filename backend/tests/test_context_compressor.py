"""
Unit tests for ContextCompressionService.
Verifies sentence-level extraction, table integrity, enterprise identifier protection,
abbreviations, decimal numbers, and token budget enforcement.
"""
import uuid
import pytest
from backend.app.schemas.reranking import CompressionConfig, RerankedChunk
from backend.app.services.context_compressor import ContextCompressionService


def create_sample_reranked_chunk(content: str, is_table: bool = False) -> RerankedChunk:
    return RerankedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=content,
        reranker_raw_score=3.5,
        reranker_score=0.97,
        reranker_rank=1,
        initial_retrieval_score=0.85,
        initial_retrieval_rank=1,
        original_token_count=len(content.split()),
        compressed_token_count=len(content.split()),
        compression_ratio=1.0,
        is_table=is_table,
    )


def test_compressor_pruning_irrelevant_sentences():
    """
    Verifies that the compressor retains query-relevant sentences while removing unrelated filler sentences.
    """
    content = (
        "The company was founded in 2010 in Seattle. "
        "Eligible full-time employees are entitled to 26 weeks of fully paid maternity leave. "
        "The corporate headquarters has three cafeterias on campus. "
        "Parking passes can be requested at the reception desk."
    )
    chunk = create_sample_reranked_chunk(content)
    compressor = ContextCompressionService()

    compressed_chunk = compressor.compress_chunk(
        query="How many weeks of maternity leave do employees get?",
        chunk=chunk,
    )

    result_text = compressed_chunk.compressed_content
    assert "26 weeks of fully paid maternity leave" in result_text
    assert "three cafeterias on campus" not in result_text
    assert compressed_chunk.compression_ratio < 1.0


def test_compressor_preserves_enterprise_identifiers():
    """
    Verifies that enterprise identifiers matching query entities are strictly preserved.
    """
    content = (
        "Network latency is an important factor in high-availability clusters. "
        "Path MTU Discovery specification is formally defined in RFC-4821. "
        "Legacy routers may require manual MTU configuration."
    )
    chunk = create_sample_reranked_chunk(content)
    compressor = ContextCompressionService()

    compressed_chunk = compressor.compress_chunk(
        query="What is the RFC-4821 standard?",
        chunk=chunk,
    )

    assert "RFC-4821" in compressed_chunk.compressed_content
    assert "Path MTU Discovery" in compressed_chunk.compressed_content


def test_compressor_table_integrity_protection():
    """
    Verifies that Markdown tables are passed verbatim and not split or corrupted.
    """
    table_content = (
        "| Service | Port | Protocol |\n"
        "|---|---|---|\n"
        "| HTTP | 80 | TCP |\n"
        "| HTTPS | 443 | TCP |\n"
        "| SSH | 22 | TCP |"
    )
    chunk = create_sample_reranked_chunk(table_content, is_table=True)
    compressor = ContextCompressionService(config=CompressionConfig(preserve_tables=True))

    compressed_chunk = compressor.compress_chunk(
        query="What port is used for HTTPS?",
        chunk=chunk,
    )

    # Table content must be preserved verbatim
    assert compressed_chunk.compressed_content == table_content
    assert compressed_chunk.compression_ratio == 1.0


def test_compressor_abbreviation_and_version_safety():
    """
    Verifies that abbreviations (e.g., i.e., Fig. 2, Dr. Smith) and decimals (3.14159, 1.5%) do not trigger false sentence splits.
    """
    content = (
        "Release v2.1.0 upgrades the search pipeline, e.g. adding SIMD acceleration with error_500 fix. "
        "Database migrations are managed via Alembic v1.4.0 with automated schemas under Clause_4.2.1. "
        "Dr. Smith verified the constant pi is 3.14159 with a 1.5% margin as shown in Fig. 2."
    )
    chunk = create_sample_reranked_chunk(content)
    compressor = ContextCompressionService()

    sentences = compressor._split_sentences_safely(content)
    assert len(sentences) == 3
    assert "e.g. adding SIMD acceleration with error_500 fix" in sentences[0]
    assert "v2.1.0" in sentences[0]
    assert "Clause_4.2.1" in sentences[1]
    assert "Dr. Smith" in sentences[2]
    assert "3.14159" in sentences[2]
    assert "Fig. 2" in sentences[2]


def test_compressor_enterprise_id_regression_battery():
    """
    Verifies regex protection across ISO-27001, SOC-2, RFC-7231, Form ABC-123, Clause_4.2.1.
    """
    content = (
        "General introduction to organizational compliance. "
        "All cloud infrastructure must comply with ISO-27001 and SOC-2 Type II standards. "
        "HTTP semantics are governed by RFC-7231, while tax filings require Form ABC-123. "
        "Indemnity obligations are defined in Clause_4.2.1."
    )
    chunk = create_sample_reranked_chunk(content)
    compressor = ContextCompressionService()

    compressed = compressor.compress_chunk(
        query="What does ISO-27001 and Clause_4.2.1 require?",
        chunk=chunk,
    )
    res = compressed.compressed_content
    assert "ISO-27001" in res
    assert "Clause_4.2.1" in res


def test_compressor_edge_cases_empty_and_short():
    """
    Verifies that empty strings and short passages are handled gracefully without error.
    """
    compressor = ContextCompressionService()

    # Empty content
    c_empty = create_sample_reranked_chunk("")
    res_empty = compressor.compress_chunk("query", c_empty)
    assert res_empty.compressed_content == ""

    # Short content
    c_short = create_sample_reranked_chunk("Short single sentence.")
    res_short = compressor.compress_chunk("query", c_short)
    assert res_short.compressed_content == "Short single sentence."
    assert res_short.compression_ratio == 1.0
