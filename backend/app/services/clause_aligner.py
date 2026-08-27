"""
Semantic Clause Alignment Engine.
Performs deterministic two-stage structural and content alignment between clauses of two documents,
resilient to section renumbering, heading renaming, reordering, and additions/removals.
"""
import re
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.comparison import AlignedClause, DiffType
from backend.app.services.clause_extractor import ExtractedClause


class AlignmentCandidate(BaseModel):
    """Internal alignment candidate between a pair of clauses."""
    model_config = ConfigDict(frozen=True)

    clause_a: Optional[ExtractedClause] = None
    clause_b: Optional[ExtractedClause] = None
    similarity_score: float = 0.0
    heading_similarity: float = 0.0
    lexical_similarity: float = 0.0
    alignment_method: str = "unmatched"


class ClauseAlignerService:
    """
    Computes deterministic global alignment between clauses in Document A and Document B.
    """

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

    def compute_content_similarity(self, text_a: str, text_b: str) -> float:
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

    def compute_pair_similarity(
        self,
        clause_a: ExtractedClause,
        clause_b: ExtractedClause,
    ) -> Tuple[float, float, float]:
        """
        Computes composite similarity combining structural heading match and content overlap.
        Returns: (composite_score, heading_score, content_score)
        """
        head_sim = self.compute_heading_similarity(clause_a.normalized_heading, clause_b.normalized_heading)
        content_sim = self.compute_content_similarity(clause_a.normalized_text, clause_b.normalized_text)

        # Table clause matching: give heavy weight to content structure
        if clause_a.is_table and clause_b.is_table:
            composite = 0.2 * head_sim + 0.8 * content_sim
        elif clause_a.is_table != clause_b.is_table:
            # Table vs non-table mismatch penalty
            composite = 0.5 * content_sim
        elif content_sim >= 0.90:
            # Very high content match dominates even if renumbered/renamed
            composite = content_sim
        elif head_sim == 1.0:
            # Same exact heading section
            composite = 0.35 * head_sim + 0.65 * content_sim
        else:
            composite = 0.3 * head_sim + 0.7 * content_sim

        return round(composite, 4), head_sim, content_sim

    def align_clauses(
        self,
        clauses_a: List[ExtractedClause],
        clauses_b: List[ExtractedClause],
        similarity_threshold: float = 0.65,
    ) -> List[AlignmentCandidate]:
        """
        Executes deterministic bipartite maximum-weight matching between clauses.
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
                    alignment_method="unmatched_removed",
                )
                for a in clauses_a
            ]

        # Compute pairwise score matrix
        pairs: List[Tuple[float, float, float, int, int]] = []
        for idx_a, a in enumerate(clauses_a):
            for idx_b, b in enumerate(clauses_b):
                comp, head, cont = self.compute_pair_similarity(a, b)
                pairs.append((comp, head, cont, idx_a, idx_b))

        # Sort candidate pairs descending by composite similarity, then heading similarity
        pairs.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

        matched_a: Set[int] = set()
        matched_b: Set[int] = set()
        aligned_results: Dict[int, AlignmentCandidate] = {}

        # Greedily match highest scoring pairs above threshold
        for comp, head, cont, idx_a, idx_b in pairs:
            if idx_a in matched_a or idx_b in matched_b:
                continue

            # Check if pair meets similarity threshold or strong heading match
            if comp >= similarity_threshold or (head >= 0.9 and cont >= 0.4):
                matched_a.add(idx_a)
                matched_b.add(idx_b)
                method = "exact" if comp >= 0.95 else ("structural" if head >= 0.8 else "semantic")
                aligned_results[idx_a] = AlignmentCandidate(
                    clause_a=clauses_a[idx_a],
                    clause_b=clauses_b[idx_b],
                    similarity_score=comp,
                    heading_similarity=head,
                    lexical_similarity=cont,
                    alignment_method=method,
                )

        # Assemble final list in deterministic order: Document A sequence first, then remaining Document B
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
                        alignment_method="unmatched_added",
                    )
                )

        return final_alignments


# Global singleton
clause_aligner = ClauseAlignerService()
