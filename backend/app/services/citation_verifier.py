"""
Deterministic Citation Verification Service.
Enforces the 8-point citation validation pipeline:
1. Citation ID validity (1 <= id <= N)
2. Rejection of fabricated citation IDs (e.g. [99])
3. Deterministic 1-to-1 mapping to RAGContextItem
4. Provenance reconstruction from source chunks (never trusting LLM metadata)
5. Canonicalization of diverse citation formats ([1], [1, 2], [1][2], [1-3])
6. Deduplication of citation records
7. Detection of missing or empty citations
8. Clean isolation of valid vs. invalid citations with warning generation
"""
import re
from typing import Dict, List, Set, Tuple
from backend.app.schemas.rag import Citation
from backend.app.schemas.reranking import RAGContextItem


class CitationVerifierService:
    """
    Authoritative server-side citation verification engine.
    The LLM proposes citations; this service verifies validity against RAGContextItem objects.
    """

    @staticmethod
    def extract_inline_citation_ids(text: str) -> List[int]:
        """
        Extracts and canonicalizes inline citation reference IDs from answer text.
        Handles:
        - Single: [1], [2]
        - Multiple: [1, 2], [1,2], [1; 2]
        - Consecutive: [1][2]
        - Ranges: [1-3], [1 - 3]
        """
        if not text:
            return []

        found_ids: Set[int] = set()

        # Match all bracketed sequences e.g., [1], [1, 2], [1-3], [1][2]
        matches = re.findall(r"\[([\d\s,;\-]+)\]", text)
        for group in matches:
            # Handle ranges e.g. 1-3
            range_match = re.match(r"^\s*(\d+)\s*[\-–]\s*(\d+)\s*$", group)
            if range_match:
                start, end = int(range_match.group(1)), int(range_match.group(2))
                if 0 < start <= end <= start + 20:  # Bound range to reasonable length
                    for i in range(start, end + 1):
                        found_ids.add(i)
                continue

            # Split comma/semicolon/space separated numbers
            parts = re.split(r"[,;\s]+", group.strip())
            for part in parts:
                if part.isdigit():
                    found_ids.add(int(part))

        return sorted(found_ids)

    def verify_and_reconstruct(
        self,
        answer_text: str,
        proposed_citation_ids: List[int],
        context_items: List[RAGContextItem],
    ) -> Tuple[List[Citation], List[str], List[int]]:
        """
        Validates proposed and inline citation IDs against provided RAGContextItems.
        Returns:
            - List of authoritative, verified Citation objects reconstructed from RAGContextItem
            - List of operational warnings encountered
            - List of fabricated or out-of-bounds citation IDs rejected
        """
        warnings: List[str] = []
        invalid_ids: List[int] = []
        verified_citations: List[Citation] = []

        if not context_items:
            # If no context was provided, any citation is invalid
            all_referenced = set(proposed_citation_ids) | set(self.extract_inline_citation_ids(answer_text))
            if all_referenced:
                invalid_ids = sorted(all_referenced)
                warnings.append(
                    f"Citations {invalid_ids} referenced when no evidence context was provided."
                )
            return [], warnings, invalid_ids

        # Map context items by their 1-based citation_id
        context_map: Dict[int, RAGContextItem] = {item.citation_id: item for item in context_items}
        max_valid_id = len(context_items)

        # Merge proposed citation IDs and inline citation IDs
        inline_ids = self.extract_inline_citation_ids(answer_text)
        combined_ids = sorted(set(proposed_citation_ids) | set(inline_ids))

        if not combined_ids and answer_text.strip() and not answer_text.startswith("I don't have sufficient evidence"):
            warnings.append("Answer contains factual text but no citations were detected.")

        for cid in combined_ids:
            if cid in context_map:
                item = context_map[cid]
                # Reconstruct authoritative Citation from verified Phase 7 RAGContextItem
                verified_citations.append(
                    Citation(
                        citation_id=item.citation_id,
                        chunk_id=item.chunk_id,
                        document_id=item.document_id,
                        document_title=item.document_title,
                        page_number=item.page_number,
                        section_path=item.section_path,
                        quoted_or_supported_text=item.text,
                        relevance_score=item.relevance_score,
                        is_table=item.is_table,
                    )
                )
            else:
                invalid_ids.append(cid)
                warnings.append(
                    f"Fabricated or out-of-bounds citation [{cid}] rejected (valid range: 1..{max_valid_id})."
                )

        return verified_citations, warnings, invalid_ids


# Global citation verifier singleton
citation_verifier = CitationVerifierService()
