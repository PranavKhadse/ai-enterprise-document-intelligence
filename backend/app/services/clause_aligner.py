"""
Semantic Clause Alignment Engine.
Performs deterministic layered structural, lexical, and semantic embedding alignment between clauses of two documents,
resilient to section renumbering, heading renaming, reordering, and additions/removals.
"""
import re
from typing import Dict, List, Optional, Set, Tuple
import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.comparison import AlignedClause, DiffType
from backend.app.services.clause_extractor import ExtractedClause
from backend.app.services.embedding import EmbeddingService, embedding_service

# Domain keywords for policy / security contexts that provide strong topic grounding
SECURITY_POLICY_KEYWORDS: Set[str] = {
    "security", "authentication", "password", "passwords", "mfa", "multi-factor",
    "token", "tokens", "encryption", "encrypted", "decrypt", "clearance", "confidential",
    "restricted", "public", "incident", "audit", "monitoring", "retention", "backup",
    "backups", "access", "login", "authorization", "privilege", "compliance",
    "repository", "repositories", "breach", "lockout", "policy", "identity"
}


class AlignmentCandidate(BaseModel):
    """Internal alignment candidate between a pair of clauses."""
    model_config = ConfigDict(frozen=True)

    clause_a: Optional[ExtractedClause] = None
    clause_b: Optional[ExtractedClause] = None
    similarity_score: float = 0.0
    heading_similarity: float = 0.0
    lexical_similarity: float = 0.0
    semantic_similarity: float = 0.0
    alignment_method: str = "unmatched"


class ClauseAlignerService:
    """
    Computes deterministic global alignment between clauses in Document A and Document B
    using layered lexical, semantic embedding, section hierarchy, and domain signals.
    """

    def __init__(self, embedding_svc: Optional[EmbeddingService] = None):
        self._embedding_service = embedding_svc or embedding_service

    @staticmethod
    def _tokenize_words(text: str) -> Set[str]:
        """Tokenizes text into alphanumeric tokens."""
        return set(re.findall(r"\b[a-zA-Z0-9_\-\.]+\b", text.lower()))

    def compute_heading_similarity(self, heading_a: str, heading_b: str) -> float:
        """Computes Jaccard token overlap between normalized section breadcrumb paths."""
        if not heading_a or not heading_b:
            return 0.0
        if heading_a == heading_b:
            return 1.0
        tokens_a = self._tokenize_words(heading_a)
        tokens_b = self._tokenize_words(heading_b)
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return round(float(len(intersection) / len(union)), 4)

    def compute_lexical_similarity(self, text_a: str, text_b: str) -> float:
        """Computes token and character n-gram lexical Jaccard similarity."""
        if not text_a or not text_b:
            return 0.0
        if text_a.strip() == text_b.strip():
            return 1.0

        tokens_a = self._tokenize_words(text_a)
        tokens_b = self._tokenize_words(text_b)
        if not tokens_a or not tokens_b:
            return 0.0

        token_intersection = tokens_a & tokens_b
        token_union = tokens_a | tokens_b
        word_jaccard = len(token_intersection) / len(token_union)

        # Character 3-gram similarity for morphological and small edit resilience
        def get_3grams(s: str) -> Set[str]:
            clean = re.sub(r"\s+", " ", s)
            return {clean[i:i+3] for i in range(len(clean) - 2)} if len(clean) >= 3 else {clean}

        grams_a = get_3grams(text_a)
        grams_b = get_3grams(text_b)
        gram_jaccard = len(grams_a & grams_b) / len(grams_a | grams_b) if (grams_a and grams_b) else 0.0

        combined = 0.7 * word_jaccard + 0.3 * gram_jaccard
        return round(min(max(combined, 0.0), 1.0), 4)

    def compute_content_similarity(self, text_a: str, text_b: str) -> float:
        """Backward-compatible alias for lexical similarity."""
        return self.compute_lexical_similarity(text_a, text_b)

    def compute_semantic_similarity(
        self,
        text_a: str,
        text_b: str,
        vec_a: Optional[List[float]] = None,
        vec_b: Optional[List[float]] = None,
    ) -> float:
        """Computes cosine similarity between dense embeddings of two texts."""
        if not text_a or not text_b:
            return 0.0
        if text_a.strip() == text_b.strip():
            return 1.0

        try:
            if vec_a is None or vec_b is None:
                vecs = self._embedding_service.embed_batch([text_a, text_b])
                vec_a, vec_b = vecs[0], vecs[1]

            va = np.array(vec_a, dtype=np.float32)
            vb = np.array(vec_b, dtype=np.float32)
            norm_a = np.linalg.norm(va)
            norm_b = np.linalg.norm(vb)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            cosine = float(np.dot(va, vb) / (norm_a * norm_b))
            return round(float(min(max(cosine, 0.0), 1.0)), 4)
        except Exception:
            return self.compute_lexical_similarity(text_a, text_b)

    def compute_keyword_similarity(self, text_a: str, text_b: str) -> float:
        """Computes overlap of domain & policy terminology."""
        if not text_a or not text_b:
            return 0.0
        kw_a = self._tokenize_words(text_a) & SECURITY_POLICY_KEYWORDS
        kw_b = self._tokenize_words(text_b) & SECURITY_POLICY_KEYWORDS
        if not kw_a or not kw_b:
            return 0.0
        return round(float(len(kw_a & kw_b) / len(kw_a | kw_b)), 4)

    def compute_pair_similarity(
        self,
        clause_a: ExtractedClause,
        clause_b: ExtractedClause,
        vec_a: Optional[List[float]] = None,
        vec_b: Optional[List[float]] = None,
    ) -> Tuple[float, float, float, float]:
        """
        Computes composite similarity combining structural heading match, lexical overlap, and semantic embedding similarity.
        Returns: (composite_score, heading_score, lexical_score, semantic_score)
        """
        head_sim = self.compute_heading_similarity(clause_a.normalized_heading, clause_b.normalized_heading)
        lex_sim = self.compute_lexical_similarity(clause_a.normalized_text, clause_b.normalized_text)
        sem_sim = self.compute_semantic_similarity(clause_a.raw_text, clause_b.raw_text, vec_a, vec_b)
        kw_sim = self.compute_keyword_similarity(clause_a.raw_text, clause_b.raw_text)

        # Table clause matching: give heavy weight to content structure
        if clause_a.is_table and clause_b.is_table:
            composite = 0.30 * head_sim + 0.70 * lex_sim
        elif clause_a.is_table != clause_b.is_table:
            # Table vs non-table mismatch penalty
            composite = 0.40 * lex_sim + 0.10 * sem_sim
        elif lex_sim >= 0.95:
            # Very high lexical match (identical or punctuation-only difference)
            composite = lex_sim
        elif sem_sim >= 0.85:
            # Very high semantic similarity
            composite = 0.65 * sem_sim + 0.25 * lex_sim + 0.10 * head_sim
        elif head_sim >= 0.80 and (sem_sim >= 0.45 or lex_sim >= 0.35):
            # Strong structural match under same section heading
            composite = 0.35 * head_sim + 0.40 * sem_sim + 0.25 * lex_sim
        else:
            # Balanced semantic, lexical, domain-keyword and structural context
            content_sim = 0.50 * sem_sim + 0.30 * lex_sim + 0.20 * kw_sim
            composite = 0.20 * head_sim + 0.80 * content_sim

        return round(float(min(max(composite, 0.0), 1.0)), 4), head_sim, lex_sim, sem_sim

    def align_clauses(
        self,
        clauses_a: List[ExtractedClause],
        clauses_b: List[ExtractedClause],
        similarity_threshold: float = 0.65,
    ) -> List[AlignmentCandidate]:
        """
        Executes deterministic bipartite maximum-weight matching between clauses using layered similarity.
        """
        if not clauses_a and not clauses_b:
            return []

        # Handle empty side cases
        if not clauses_a:
            return [
                AlignmentCandidate(
                    clause_a=None,
                    clause_b=b,
                    similarity_score=0.0,
                    heading_similarity=0.0,
                    lexical_similarity=0.0,
                    semantic_similarity=0.0,
                    alignment_method="unmatched_added",
                )
                for b in clauses_b
            ]

        if not clauses_b:
            return [
                AlignmentCandidate(
                    clause_a=a,
                    clause_b=None,
                    similarity_score=0.0,
                    heading_similarity=0.0,
                    lexical_similarity=0.0,
                    semantic_similarity=0.0,
                    alignment_method="unmatched_removed",
                )
                for a in clauses_a
            ]

        # 1. Batch generate embeddings for both clause sets for high efficiency
        vecs_a: List[List[float]] = []
        vecs_b: List[List[float]] = []
        try:
            vecs_a = self._embedding_service.embed_batch([c.raw_text for c in clauses_a])
            vecs_b = self._embedding_service.embed_batch([c.raw_text for c in clauses_b])
        except Exception:
            vecs_a = []
            vecs_b = []

        # 2. Compute pairwise similarity matrix
        pairs: List[Tuple[float, float, float, float, int, int]] = []
        for idx_a, a in enumerate(clauses_a):
            va = vecs_a[idx_a] if idx_a < len(vecs_a) else None
            for idx_b, b in enumerate(clauses_b):
                vb = vecs_b[idx_b] if idx_b < len(vecs_b) else None
                comp, head, lex, sem = self.compute_pair_similarity(a, b, va, vb)
                pairs.append((comp, head, lex, sem, idx_a, idx_b))

        # Sort candidate pairs descending by composite similarity, then heading, then lexical
        pairs.sort(key=lambda x: (x[0], x[1], x[2], x[3]), reverse=True)

        matched_a: Set[int] = set()
        matched_b: Set[int] = set()
        aligned_results: Dict[int, AlignmentCandidate] = {}

        # 3. Greedily match highest scoring pairs using layered alignment criteria
        for comp, head, lex, sem, idx_a, idx_b in pairs:
            if idx_a in matched_a or idx_b in matched_b:
                continue

            # Layered candidate acceptance criteria:
            # A. Meets direct similarity threshold
            # B. Strong heading match with moderate semantic/lexical overlap
            # C. Strong semantic topic match with contextual/keyword overlap
            is_match = False
            if comp >= similarity_threshold:
                is_match = True
            elif head >= 0.80 and (sem >= 0.45 or lex >= 0.35):
                is_match = True
            elif sem >= 0.60 and (comp >= 0.40 or head >= 0.30 or lex >= 0.10):
                is_match = True

            if is_match:
                matched_a.add(idx_a)
                matched_b.add(idx_b)
                method = "exact" if comp >= 0.95 else ("structural" if head >= 0.80 else "semantic")
                aligned_results[idx_a] = AlignmentCandidate(
                    clause_a=clauses_a[idx_a],
                    clause_b=clauses_b[idx_b],
                    similarity_score=comp,
                    heading_similarity=head,
                    lexical_similarity=lex,
                    semantic_similarity=sem,
                    alignment_method=method,
                )

        # 4. Assemble final list in deterministic order: Document A sequence first, then remaining Document B
        final_alignments: List[AlignmentCandidate] = []
        for idx_a, a in enumerate(clauses_a):
            if idx_a in aligned_results:
                final_alignments.append(aligned_results[idx_a])
            else:
                final_alignments.append(
                    AlignmentCandidate(
                        clause_a=a,
                        clause_b=None,
                        similarity_score=0.0,
                        heading_similarity=0.0,
                        lexical_similarity=0.0,
                        semantic_similarity=0.0,
                        alignment_method="unmatched_removed",
                    )
                )

        # Append unmatched clauses from Document B (ADDED)
        for idx_b, b in enumerate(clauses_b):
            if idx_b not in matched_b:
                final_alignments.append(
                    AlignmentCandidate(
                        clause_a=None,
                        clause_b=b,
                        similarity_score=0.0,
                        heading_similarity=0.0,
                        lexical_similarity=0.0,
                        semantic_similarity=0.0,
                        alignment_method="unmatched_added",
                    )
                )

        return final_alignments


# Global singleton
clause_aligner = ClauseAlignerService()

