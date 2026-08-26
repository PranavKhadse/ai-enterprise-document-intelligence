"""
Deterministic Context Compression Service.
Extracts verbatim high-utility sentences from reranked passages while protecting
tables, numeric precision, and enterprise identifiers without generative LLM rewriting.
"""
import re
from typing import List, Optional, Set, Tuple
import tiktoken
from backend.app.core.config import settings
from backend.app.schemas.reranking import CompressionConfig, RerankedChunk


# Enterprise identifier regex pattern
ENTERPRISE_IDENTIFIER_PATTERN = re.compile(
    r"\b(RFC-\d+|ISO-\d+|SOC-\d+|v\d+\.\d+(?:\.\d+)*|error_\d+|Clause_\d+(?:\.\d+)*|Section\s+\d+|Form\s+[A-Za-z0-9-]+)\b",
    re.IGNORECASE,
)

# Common abbreviation protection pattern
ABBREVIATION_PATTERN = re.compile(
    r"\b(e\.g\.|i\.e\.|etc\.|vs\.|fig\.|dr\.|mr\.|ms\.|prof\.|inc\.|corp\.|co\.|ltd\.|dept\.)",
    re.IGNORECASE,
)


class ContextCompressionService:
    """
    Deterministic context compressor that extracts salient verbatim sentences
    matching query intent and enterprise entities while maintaining strict token ceilings.
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

    def _split_sentences_safely(self, text: str) -> List[str]:
        """
        Splits text into sentences while safely preserving abbreviations, decimals, and versions.
        """
        # Protect decimal numbers and versions temporarily
        protected_text = re.sub(r"(\d+)\.(\d+)", r"\1__DECIMAL__\2", text)
        protected_text = re.sub(
            r"\b(e\.g\.|i\.e\.|etc\.|vs\.|fig\.|dr\.|mr\.|ms\.|prof\.|inc\.|corp\.|co\.|ltd\.)",
            lambda m: m.group(0).replace(".", "__DOT__"),
            protected_text,
            flags=re.IGNORECASE,
        )

        raw_sentences = re.split(r"(?<=[.!?])\s+", protected_text)

        cleaned_sentences: List[str] = []
        for s in raw_sentences:
            s_clean = s.replace("__DECIMAL__", ".").replace("__DOT__", ".").strip()
            if s_clean:
                cleaned_sentences.append(s_clean)

        return cleaned_sentences

    def _extract_query_keywords(self, query: str) -> Set[str]:
        """
        Extracts salient keywords and enterprise tokens from the query.
        """
        raw_words = re.findall(r"\b[A-Za-z0-9_\-\.]+\b", query.lower())
        stopwords = {
            "what", "is", "the", "for", "in", "how", "are", "do", "does", "to",
            "a", "an", "and", "or", "of", "with", "on", "at", "by", "from", "when"
        }
        return {w for w in raw_words if len(w) > 1 and w not in stopwords}

    def compress_chunk(self, query: str, chunk: RerankedChunk) -> RerankedChunk:
        """
        Compresses a single chunk passage to its salient core while preserving tables and identifiers.
        """
        if not self.config.enabled:
            return chunk

        content = chunk.content.strip()

        # 1. Table Protection: Pass tables verbatim if detected
        is_table = chunk.is_table or ("|---" in content) or ("|:--" in content)
        if is_table and self.config.preserve_tables:
            chunk.compressed_content = content
            chunk.compressed_token_count = self.count_tokens(content)
            chunk.compression_ratio = 1.0
            return chunk

        # 2. Extract breadcrumb context header if present
        breadcrumb_prefix = ""
        body_text = content
        if content.startswith("[Context:"):
            parts = content.split("]\n\n", 1)
            if len(parts) == 2:
                breadcrumb_prefix = parts[0] + "]\n\n"
                body_text = parts[1]

        sentences = self._split_sentences_safely(body_text)
        if len(sentences) <= 1:
            chunk.compressed_content = content
            chunk.compressed_token_count = self.count_tokens(content)
            chunk.compression_ratio = 1.0
            return chunk

        # 3. Score sentences based on entity match, query keyword overlap, and numerical data
        query_keywords = self._extract_query_keywords(query)
        query_entities = set(re.findall(ENTERPRISE_IDENTIFIER_PATTERN, query))

        scored_sentences: List[Tuple[float, int, str]] = []
        for idx, s in enumerate(sentences):
            score = 0.0
            s_lower = s.lower()

            # Enterprise identifier exact match
            s_entities = set(re.findall(ENTERPRISE_IDENTIFIER_PATTERN, s))
            if query_entities & s_entities:
                score += 10.0
            elif s_entities:
                score += 3.0

            # Query keyword overlap
            matched_keywords = sum(1 for kw in query_keywords if kw in s_lower)
            score += matched_keywords * 2.0

            # Numbers / dates / amounts
            if re.search(r"\b\d+(\.\d+)?\b", s):
                score += 1.0

            # Penalize filler / transition sentences
            if re.match(r"^(however|furthermore|additionally|moreover|in addition),", s_lower):
                score += 0.2

            scored_sentences.append((score, idx, s))

        # 4. Sort sentences by score DESC and select within target token budget
        scored_sentences.sort(key=lambda item: (item[0], -item[1]), reverse=True)

        target_budget = self.config.target_tokens_per_chunk
        selected_indices: Set[int] = set()
        accumulated_tokens = self.count_tokens(breadcrumb_prefix)

        for score, idx, s in scored_sentences:
            # If we already have relevant sentences, skip completely uninformative sentences (score <= 0.0)
            if score <= 0.0 and selected_indices:
                continue

            s_tokens = self.count_tokens(s)
            if accumulated_tokens + s_tokens <= target_budget or not selected_indices:
                selected_indices.add(idx)
                accumulated_tokens += s_tokens

                # Anaphora resolution: If sentence starts with pronoun, include previous sentence if available
                if idx > 0 and (idx - 1) not in selected_indices:
                    first_word = s.split()[0].lower() if s.split() else ""
                    if first_word in {"it", "this", "these", "they", "such"}:
                        prev_tokens = self.count_tokens(sentences[idx - 1])
                        if accumulated_tokens + prev_tokens <= target_budget + 30:
                            selected_indices.add(idx - 1)
                            accumulated_tokens += prev_tokens

            if accumulated_tokens >= target_budget:
                break

        # 5. Reconstruct compressed text in original chronological sequence
        ordered_sentences = [sentences[i] for i in sorted(selected_indices)]
        compressed_text = breadcrumb_prefix + " ".join(ordered_sentences)

        # Fallback to original text if compression removed everything
        if not ordered_sentences or self.count_tokens(compressed_text) < 15:
            compressed_text = content

        compressed_tokens = self.count_tokens(compressed_text)
        orig_tokens = chunk.original_token_count or self.count_tokens(content)

        chunk.compressed_content = compressed_text
        chunk.compressed_token_count = compressed_tokens
        chunk.compression_ratio = round(float(compressed_tokens / max(orig_tokens, 1)), 3)

        return chunk

    def compress_all(self, query: str, chunks: List[RerankedChunk]) -> List[RerankedChunk]:
        """
        Compresses a list of reranked candidate chunks.
        """
        return [self.compress_chunk(query, chunk) for chunk in chunks]


# Global context compression service singleton
context_compressor = ContextCompressionService()
