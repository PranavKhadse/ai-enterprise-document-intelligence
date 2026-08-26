"""
Evidence Selection & Token Budget Allocator.
Applies diversity filtering, near-duplicate suppression, and context window packing
to produce the frozen Phase 8 RAG Context Contract.
"""
import re
from typing import Dict, List, Optional, Set, Tuple
import tiktoken
from backend.app.core.config import settings
from backend.app.schemas.reranking import CompressionConfig, RAGContextItem, RerankedChunk


class EvidenceSelector:
    """
    Evidence selection engine packing high-utility, diverse evidence into a strict token budget.
    """

    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig(
            enabled=settings.COMPRESSION_ENABLED,
            target_tokens_per_chunk=settings.COMPRESSION_TARGET_TOKENS_PER_CHUNK,
            max_context_tokens=settings.COMPRESSION_MAX_CONTEXT_TOKENS,
            preserve_tables=settings.COMPRESSION_PRESERVE_TABLES,
            near_duplicate_threshold=settings.DIVERSITY_NEAR_DUPLICATE_THRESHOLD,
            max_chunks_per_section=settings.DIVERSITY_MAX_CHUNKS_PER_SECTION,
        )
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """
        Counts tokens using tiktoken cl100k_base.
        """
        if not text:
            return 0
        return len(self._tokenizer.encode(text, disallowed_special=()))

    @staticmethod
    def _compute_jaccard_similarity(text_a: str, text_b: str) -> float:
        """
        Calculates token-level Jaccard similarity between two text passages.
        """
        tokens_a = re.findall(r"\b\w+\b", text_a.lower())
        tokens_b = re.findall(r"\b\w+\b", text_b.lower())
        set_a = set(tokens_a)
        set_b = set(tokens_b)
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return float(intersection / union) if union > 0 else 0.0

    def select_evidence(
        self,
        chunks: List[RerankedChunk],
        max_context_tokens: Optional[int] = None,
        max_chunks: Optional[int] = None,
    ) -> Tuple[List[RerankedChunk], List[RAGContextItem]]:
        """
        Filters candidates for diversity and greedily packs them within the maximum context token budget.
        Returns the selected RerankedChunks and the frozen Phase 8 RAGContextItems.
        """
        if not chunks:
            return [], []

        token_ceiling = max_context_tokens or self.config.max_context_tokens
        near_dup_thresh = self.config.near_duplicate_threshold
        max_per_section = self.config.max_chunks_per_section

        selected_chunks: List[RerankedChunk] = []
        context_items: List[RAGContextItem] = []
        section_counts: Dict[Tuple[str, str], int] = {}
        accumulated_tokens = 0

        for chunk in chunks:
            text = chunk.compressed_content or chunk.content
            chunk_tokens = chunk.compressed_token_count or self.count_tokens(text)

            # 1. Check Hard Token Ceiling
            if accumulated_tokens + chunk_tokens > token_ceiling:
                continue

            # 2. Section Density Limit: max N chunks from same (doc_id, section_path)
            sec_key = (str(chunk.document_id), str(chunk.section_path or "root"))
            if section_counts.get(sec_key, 0) >= max_per_section:
                continue

            # 3. Near-Duplicate Suppression via Jaccard Similarity
            is_duplicate = False
            for prev_chunk in selected_chunks:
                prev_text = prev_chunk.compressed_content or prev_chunk.content
                sim = self._compute_jaccard_similarity(text, prev_text)
                if sim >= near_dup_thresh:
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            # Accept chunk
            selected_chunks.append(chunk)
            section_counts[sec_key] = section_counts.get(sec_key, 0) + 1
            accumulated_tokens += chunk_tokens

            # Create Phase 8 RAG Context Item
            citation_id = len(context_items) + 1
            doc_title = chunk.metadata.get("document_title") if chunk.metadata else None

            context_items.append(
                RAGContextItem(
                    citation_id=citation_id,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    document_title=doc_title,
                    page_number=chunk.page_number,
                    section_path=chunk.section_path,
                    text=text,
                    relevance_score=chunk.reranker_score,
                    is_table=chunk.is_table,
                )
            )

            if max_chunks is not None and len(selected_chunks) >= max_chunks:
                break

        return selected_chunks, context_items


# Global evidence selector singleton
evidence_selector = EvidenceSelector()
