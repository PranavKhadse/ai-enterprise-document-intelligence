"""
Deterministic Grounding & Claim Verification Service.
Executes multi-layer factual grounding validation:
1. Deterministic claim assertion extraction (sentences, bullet items, numbered lists).
2. Exact entity and numeric guard (currency, percentages, dates, version numbers, RFCs, ISOs, clauses).
3. Textual support heuristic scoring (content token overlap against cited RAGContextItems).
4. Authoritative GroundingStatus classification.
"""
import re
from typing import Dict, List, Optional, Set, Tuple
from backend.app.core.config import settings
from backend.app.schemas.rag import (
    Citation,
    ClaimStatus,
    ClaimVerification,
    GroundingStatus,
    LLMClaimProposal,
)
from backend.app.schemas.reranking import RAGContextItem
from backend.app.services.citation_verifier import citation_verifier

# Entity regex patterns
CURRENCY_PATTERN = re.compile(r"[\$€£¥]\s*\d+(?:,\d{3})*(?:\.\d+)?|\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:USD|EUR|GBP|dollars?|cents?)\b", re.IGNORECASE)
PERCENTAGE_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%", re.IGNORECASE)
VERSION_PATTERN = re.compile(r"\bv\d+(?:\.\d+)+(?:-[a-zA-Z0-9]+)?\b", re.IGNORECASE)
ENTERPRISE_ID_PATTERN = re.compile(r"\b(RFC-\d+|ISO-\d+|SOC-\d+|Clause_\d+(?:\.\d+)*|Section\s+\d+|error_\d+|ERR_\d+|Form\s+[A-Za-z0-9-]+)\b", re.IGNORECASE)
NUMBER_WORD_PATTERN = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")
DATE_PATTERN = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b", re.IGNORECASE)

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "with",
    "by", "of", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "this", "that", "these", "those",
    "it", "its", "they", "their", "them", "which", "who", "whom", "whose", "what",
    "where", "when", "why", "how", "all", "any", "both", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "can", "will", "just", "should", "now"
}


class GroundingVerifierService:
    """
    Evaluates factual support and claim-level grounding deterministically in Python.
    """

    def __init__(self, lexical_support_threshold: Optional[float] = None):
        self.support_threshold = (
            lexical_support_threshold
            if lexical_support_threshold is not None
            else settings.RAG_LEXICAL_SUPPORT_THRESHOLD
        )

    def extract_claims(
        self,
        answer_text: str,
        proposed_claims: Optional[List[LLMClaimProposal]] = None,
    ) -> List[Tuple[str, List[int]]]:
        """
        Extracts factual claim assertions and their associated inline citation IDs.
        Uses proposed claims if provided, or splits sentences/bullets deterministically.
        """
        if not answer_text or not answer_text.strip():
            return []

        # If answer is an explicit refusal, return empty claims
        clean_text = answer_text.strip()
        if clean_text.startswith("I don't have sufficient evidence"):
            return []

        extracted: List[Tuple[str, List[int]]] = []

        if proposed_claims:
            for p in proposed_claims:
                claim_text = p.claim_text.strip()
                if len(claim_text) > 5 and not claim_text.lower().startswith(("hello", "hi", "sure", "here is")):
                    inline_ids = citation_verifier.extract_inline_citation_ids(claim_text)
                    merged_ids = sorted(set(p.citation_ids) | set(inline_ids))
                    extracted.append((claim_text, merged_ids))
            if extracted:
                return extracted

        # Fallback: Deterministic sentence and list splitting
        lines = [line.strip() for line in clean_text.split("\n") if line.strip()]
        for line in lines:
            # Check for bullet points or numbered lists
            list_match = re.match(r"^(?:[\*\-\•]|\d+[\.\)])\s*(.*)", line)
            item_text = list_match.group(1) if list_match else line

            # Split into sentences safely
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", item_text) if s.strip()]
            for sentence in sentences:
                if len(sentence) <= 8:
                    continue
                # Skip greetings or generic conversational fillers
                if re.match(r"^(hello|hi|greetings|in conclusion|summary:|note:)", sentence.lower()):
                    continue
                cids = citation_verifier.extract_inline_citation_ids(sentence)
                # Remove citation brackets from clean claim text
                clean_claim = re.sub(r"\[[\d\s,;\-]+\]", "", sentence).strip()
                if len(clean_claim) > 5:
                    extracted.append((clean_claim, cids))

        return extracted

    @staticmethod
    def extract_critical_entities(text: str) -> Dict[str, Set[str]]:
        """
        Extracts numbers, currency, percentages, versions, enterprise IDs, and dates.
        """
        return {
            "currency": set(CURRENCY_PATTERN.findall(text)),
            "percentages": set(PERCENTAGE_PATTERN.findall(text)),
            "versions": set(VERSION_PATTERN.findall(text)),
            "enterprise_ids": set(ENTERPRISE_ID_PATTERN.findall(text)),
            "dates": set(DATE_PATTERN.findall(text)),
            "numbers": set(NUMBER_WORD_PATTERN.findall(text)),
        }

    @staticmethod
    def _tokenize_content_words(text: str) -> Set[str]:
        """Extracts normalized alphanumeric content words excluding stopwords."""
        words = re.findall(r"\b[A-Za-z0-9_\-\.]+\b", text.lower())
        return {w for w in words if len(w) > 1 and w not in STOPWORDS}

    def verify_single_claim(
        self,
        claim_text: str,
        citation_ids: List[int],
        context_map: Dict[int, RAGContextItem],
    ) -> ClaimVerification:
        """
        Validates an individual claim against its cited evidence passages.
        """
        if not citation_ids:
            return ClaimVerification(
                claim_text=claim_text,
                citation_ids=[],
                status=ClaimStatus.UNSUPPORTED,
                entailment_score=0.0,
                unsupported_entities=[],
                explanation="No citations provided to support this claim.",
            )

        # Retrieve text from all cited context items
        cited_passages = [context_map[cid].text for cid in citation_ids if cid in context_map]
        if not cited_passages:
            return ClaimVerification(
                claim_text=claim_text,
                citation_ids=citation_ids,
                status=ClaimStatus.UNSUPPORTED,
                entailment_score=0.0,
                unsupported_entities=[],
                explanation=f"Referenced citation IDs {citation_ids} do not exist in provided evidence.",
            )

        combined_evidence = " ".join(cited_passages)

        # 1. Exact Entity & Numeric Guard
        claim_entities = self.extract_critical_entities(claim_text)
        evidence_entities = self.extract_critical_entities(combined_evidence)

        unsupported_entities: List[str] = []

        # Check currency
        for curr in claim_entities["currency"]:
            if curr.lower() not in combined_evidence.lower():
                unsupported_entities.append(f"Currency: {curr}")

        # Check percentages
        for pct in claim_entities["percentages"]:
            if pct not in combined_evidence:
                unsupported_entities.append(f"Percentage: {pct}")

        # Check versions
        for ver in claim_entities["versions"]:
            if ver.lower() not in combined_evidence.lower():
                unsupported_entities.append(f"Version: {ver}")

        # Check enterprise IDs
        for eid in claim_entities["enterprise_ids"]:
            if eid.lower() not in combined_evidence.lower():
                unsupported_entities.append(f"Identifier: {eid}")

        # Check raw numbers
        for num in claim_entities["numbers"]:
            if num not in combined_evidence:
                unsupported_entities.append(f"Number: {num}")

        # If any critical numbers, versions, or IDs are fabricated -> Claim is UNSUPPORTED
        if unsupported_entities:
            return ClaimVerification(
                claim_text=claim_text,
                citation_ids=citation_ids,
                status=ClaimStatus.UNSUPPORTED,
                entailment_score=0.0,
                unsupported_entities=unsupported_entities,
                explanation=f"Claim contains unsupported entities: {', '.join(unsupported_entities)}",
            )

        # 2. Lexical Support & Content Word Overlap Heuristic
        claim_words = self._tokenize_content_words(claim_text)
        evidence_words = self._tokenize_content_words(combined_evidence)

        if not claim_words:
            overlap_score = 1.0
        else:
            intersection = claim_words & evidence_words
            overlap_score = float(len(intersection) / len(claim_words))

        overlap_score = round(min(max(overlap_score, 0.0), 1.0), 3)

        if overlap_score >= self.support_threshold:
            status = ClaimStatus.SUPPORTED
            explanation = f"Supported by citation(s) {citation_ids} (lexical support score: {overlap_score:.2f})."
        elif overlap_score >= self.support_threshold * 0.5:
            status = ClaimStatus.PARTIALLY_SUPPORTED
            explanation = f"Partially supported (lexical support score: {overlap_score:.2f} < {self.support_threshold})."
        else:
            status = ClaimStatus.UNSUPPORTED
            explanation = f"Insufficient lexical overlap ({overlap_score:.2f} < {self.support_threshold}) with cited evidence."

        return ClaimVerification(
            claim_text=claim_text,
            citation_ids=citation_ids,
            status=status,
            entailment_score=overlap_score,
            unsupported_entities=[],
            explanation=explanation,
        )

    def verify_grounding(
        self,
        answer_text: str,
        context_items: List[RAGContextItem],
        proposed_claims: Optional[List[LLMClaimProposal]] = None,
        insufficient_evidence_flag: bool = False,
    ) -> Tuple[GroundingStatus, List[ClaimVerification], List[str]]:
        """
        Evaluates overall factual grounding across all extracted claims.
        Returns:
            - GroundingStatus classification
            - List of verified ClaimVerification objects
            - Operational warnings
        """
        warnings: List[str] = []

        if not context_items or insufficient_evidence_flag:
            return GroundingStatus.INSUFFICIENT_EVIDENCE, [], warnings

        context_map: Dict[int, RAGContextItem] = {item.citation_id: item for item in context_items}
        extracted_claims = self.extract_claims(answer_text, proposed_claims)

        if not extracted_claims:
            if "insufficient evidence" in answer_text.lower():
                return GroundingStatus.INSUFFICIENT_EVIDENCE, [], warnings
            return GroundingStatus.UNSUPPORTED, [], ["No verifiable claims could be extracted from answer."]

        verified_claims: List[ClaimVerification] = []
        for claim_text, cids in extracted_claims:
            res = self.verify_single_claim(claim_text, cids, context_map)
            verified_claims.append(res)
            if res.status == ClaimStatus.UNSUPPORTED:
                warnings.append(f"Unsupported claim: '{claim_text}' ({res.explanation})")

        # Classify overall grounding
        total = len(verified_claims)
        supported_count = sum(1 for c in verified_claims if c.status == ClaimStatus.SUPPORTED)
        partially_count = sum(1 for c in verified_claims if c.status == ClaimStatus.PARTIALLY_SUPPORTED)
        unsupported_count = sum(1 for c in verified_claims if c.status == ClaimStatus.UNSUPPORTED)

        if supported_count == total and total > 0:
            status = GroundingStatus.FULLY_GROUNDED
        elif supported_count > 0 and unsupported_count == 0:
            status = GroundingStatus.PARTIALLY_GROUNDED
        elif supported_count >= (total / 2.0):
            status = GroundingStatus.PARTIALLY_GROUNDED
        else:
            status = GroundingStatus.UNSUPPORTED

        return status, verified_claims, warnings


# Global grounding verifier singleton
grounding_verifier = GroundingVerifierService()
