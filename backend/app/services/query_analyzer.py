"""
Query Analysis & Heuristic Intent Classification Service.
Analyzes user queries to classify search intent and dynamically tune
dense/sparse weights and over-retrieval candidate depths without LLM overhead.
"""
import re
from typing import List, Tuple
from backend.app.schemas.retrieval import QueryType


class QueryAnalyzer:
    """
    Fast, deterministic query intent classifier.
    """

    def __init__(self):
        # Precise regex patterns for technical codes, part numbers, version numbers, and enterprise identifiers
        self._exact_patterns: List[re.Pattern] = [
            re.compile(r"\brfc-\d+\b", re.IGNORECASE),
            re.compile(r"\biso-\d+\b", re.IGNORECASE),
            re.compile(r"\berror_\d+\b", re.IGNORECASE),
            re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b", re.IGNORECASE),
            re.compile(r"(?:^|\s|[.,;!?])c\+\+(?:\s|$|[.,;!?])", re.IGNORECASE),
            re.compile(r"\bform\s+[a-zA-Z0-9\-]+\b", re.IGNORECASE),
            re.compile(r"\bclause[_\s]+\d+(?:\.\d+)*\b", re.IGNORECASE),
            re.compile(r"\bsection[_\s]+\d+(?:\.\d+)*\b", re.IGNORECASE),
            # Alphanumeric codes containing both letters and numbers with hyphens or underscores (e.g., CVE-2024, Policy_101, W-2)
            re.compile(r"\b[a-zA-Z]+[_\-]\d+\b", re.IGNORECASE),
            re.compile(r"\b\d+[_\-][a-zA-Z]+\b", re.IGNORECASE),
            re.compile(r"\b[a-zA-Z]+\d+[a-zA-Z0-9_\-]*\b", re.IGNORECASE),
        ]

        # Interrogatives and question indicators
        self._question_keywords = {
            "how", "why", "what", "when", "where", "which", "who", "whom", "whose",
            "explain", "describe", "compare", "summarize", "define", "outline", "list",
            "can", "could", "should", "would", "is", "are", "does", "do",
        }

    def analyze_query(
        self, query: str
    ) -> Tuple[QueryType, float, float, float]:
        """
        Classifies query intent and returns (QueryType, dense_weight, sparse_weight, pool_multiplier).
        """
        if not query or not query.strip():
            return QueryType.KEYWORD_SEARCH, 0.5, 0.5, 1.0

        cleaned_query = query.strip()
        words = cleaned_query.split()
        num_words = len(words)

        # Check if query has question structure
        first_word = words[0].lower().strip("?,.!")
        has_question_word = first_word in self._question_keywords or any(w.lower() in self._question_keywords for w in words[:2])
        is_question = cleaned_query.endswith("?") or (has_question_word and num_words >= 3)

        # Check for specific technical code/identifier patterns
        has_exact_identifier = any(pattern.search(cleaned_query) for pattern in self._exact_patterns)

        # 1. Exact Identifier takes priority when code pattern is detected
        if has_exact_identifier:
            return QueryType.EXACT_IDENTIFIER, 0.25, 0.75, 1.5

        # 2. Natural Language Questions
        if is_question:
            return QueryType.SEMANTIC_QUESTION, 0.75, 0.25, 1.2

        # 3. Short Keyword Searches (<= 3 words without question syntax)
        if num_words <= 3:
            return QueryType.KEYWORD_SEARCH, 0.40, 0.60, 1.0

        # 4. Fallback to Mixed / Balanced Query
        return QueryType.MIXED, 0.60, 0.40, 1.0


# Global query analyzer singleton
query_analyzer = QueryAnalyzer()
