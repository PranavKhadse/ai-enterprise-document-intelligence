"""
Phase 8 Grounded RAG Synthesis Service.
Coordinates prompt construction, LLM generation, deterministic citation verification,
claim-level grounding verification, conflict detection, and structured RAGAnswer construction.
"""
import re
import time
from typing import Dict, List, Optional, Set, Tuple
from backend.app.core.config import settings
from backend.app.schemas.rag import (
    Citation,
    ClaimStatus,
    ClaimVerification,
    GroundingStatus,
    LLMAnswerProposal,
    LLMClaimProposal,
    RAGAnswer,
    RAGDiagnostics,
)
from backend.app.schemas.reranking import RAGContextItem, RerankingDiagnostics
from backend.app.services.citation_verifier import CitationVerifierService, citation_verifier
from backend.app.services.grounding_verifier import GroundingVerifierService, grounding_verifier
from backend.app.services.llm_provider import (
    BaseLLMProvider,
    LLMProviderError,
    get_llm_provider,
    llm_provider as default_llm_provider,
)
from backend.app.services.prompt_builder import RAGPromptBuilder, prompt_builder


class RAGSynthesisService:
    """
    Core RAG answer synthesis engine enforcing the architectural principle:
    THE LLM PROPOSES. PYTHON DETERMINISTIC VERIFICATION IS THE SOLE AUTHORITY.
    """

    def __init__(
        self,
        provider: Optional[BaseLLMProvider] = None,
        builder: Optional[RAGPromptBuilder] = None,
        cit_verifier: Optional[CitationVerifierService] = None,
        grd_verifier: Optional[GroundingVerifierService] = None,
    ):
        self.provider = provider or default_llm_provider
        self.builder = builder or prompt_builder
        self.cit_verifier = cit_verifier or citation_verifier
        self.grd_verifier = grd_verifier or grounding_verifier

    def _detect_conflicting_evidence(
        self,
        context_items: List[RAGContextItem],
        proposed: Optional[LLMAnswerProposal] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Detects evidence contradictions across retrieved passages (different policies, versions, or opposing values).
        """
        if not context_items or len(context_items) < 2:
            return False, None

        # Check for opposing polarity terms across different documents/passages
        has_mandatory = any("mandatory" in item.text.lower() or "required" in item.text.lower() for item in context_items)
        has_optional = any("optional" in item.text.lower() or "discretionary" in item.text.lower() for item in context_items)
        has_prohibited = any("prohibited" in item.text.lower() or "forbidden" in item.text.lower() for item in context_items)
        has_permitted = any("permitted" in item.text.lower() or "allowed" in item.text.lower() for item in context_items)

        # Check for differing numbers under same keyword e.g. "retention" or "days"
        retention_days: Set[int] = set()
        for item in context_items:
            m = re.search(r"(\d+)\s*days?", item.text.lower())
            if m and ("retention" in item.text.lower() or "backup" in item.text.lower()):
                retention_days.add(int(m.group(1)))

        has_polarity_conflict = (has_mandatory and has_optional) or (has_prohibited and has_permitted)
        has_number_conflict = len(retention_days) > 1

        if has_polarity_conflict or has_number_conflict or (proposed and proposed.conflicts_detected):
            details = []
            if has_number_conflict:
                details.append(f"Contradictory retention periods found: {sorted(retention_days)} days.")
            if has_polarity_conflict:
                details.append("Contradictory policy terms (mandatory vs. optional/prohibited vs. permitted) detected across sources.")
            if proposed and proposed.conflict_details:
                details.append(proposed.conflict_details)
            return True, " ".join(details)

        return False, None

    async def synthesize(
        self,
        query: str,
        context_items: List[RAGContextItem],
        temperature: float = 0.0,
        enable_verification: bool = True,
        phase7_diagnostics: Optional[RerankingDiagnostics] = None,
    ) -> RAGAnswer:
        """
        Executes end-to-end grounded RAG synthesis with strict deterministic verification.
        """
        start_total = time.perf_counter()
        warnings: List[str] = []
        degraded_mode = False

        # 0. Early Deterministic Guard: Zero Evidence
        if not context_items or not query or not query.strip():
            tot_lat = (time.perf_counter() - start_total) * 1000.0
            return RAGAnswer(
                query=query or "",
                answer="I don't have sufficient evidence in the provided documents to answer this confidently.",
                grounding_status=GroundingStatus.INSUFFICIENT_EVIDENCE,
                citations=[],
                claims=[],
                insufficient_evidence=True,
                conflicts_detected=False,
                conflict_details=None,
                warnings=["No relevant evidence context was retrieved from documents."] if not context_items else ["Empty query provided."],
                diagnostics=RAGDiagnostics(
                    query=query or "",
                    provider="early_guard",
                    model="none",
                    total_rag_latency_ms=round(tot_lat, 2),
                    evidence_count=0,
                    citation_count=0,
                    phase7_diagnostics=phase7_diagnostics,
                ),
            )

        # 1. Step 1: Prompt Construction
        t_prompt_start = time.perf_counter()
        prompt_payload = self.builder.build_full_prompt_payload(query, context_items)
        prompt_builder_latency = (time.perf_counter() - t_prompt_start) * 1000.0

        # 2. Step 2: LLM Provider Execution
        t_llm_start = time.perf_counter()
        proposed: Optional[LLMAnswerProposal] = None

        try:
            proposed = await self.provider.generate_structured(
                prompt=prompt_payload["user_prompt"],
                response_schema=LLMAnswerProposal,
                system_prompt=prompt_payload["system_prompt"],
                temperature=temperature,
                max_tokens=settings.LLM_MAX_TOKENS,
            )
        except LLMProviderError as pe:
            degraded_mode = True
            warnings.append(f"LLM provider error ({str(pe)}). Falling back to evidence summary.")
        except Exception as ex:
            degraded_mode = True
            warnings.append(f"Unexpected LLM generation error ({str(ex)}). Falling back to degraded mode.")

        llm_latency = (time.perf_counter() - t_llm_start) * 1000.0

        # Degraded fallback if LLM failed
        if degraded_mode or proposed is None:
            top_item = context_items[0]
            fallback_answer = f"Based on retrieved document '{top_item.document_title or 'Evidence'}': {top_item.text} [1]"
            proposed = LLMAnswerProposal(
                answer=fallback_answer,
                claims=[
                    LLMClaimProposal(
                        claim_text=f"Based on retrieved document '{top_item.document_title or 'Evidence'}': {top_item.text}",
                        citation_ids=[1],
                    )
                ],
                citation_ids=[1],
                insufficient_evidence=False,
                conflicts_detected=False,
            )
        else:
            # Deterministic post-processing repair: sync claim citation_ids if omitted by LLM but present in answer
            if proposed.claims:
                ans_cids = self.cit_verifier.extract_inline_citation_ids(proposed.answer)
                ans_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", proposed.answer) if s.strip()]
                for clm in proposed.claims:
                    if not clm.citation_ids:
                        inline_in_claim = self.cit_verifier.extract_inline_citation_ids(clm.claim_text)
                        if inline_in_claim:
                            clm.citation_ids = inline_in_claim
                        else:
                            clean_c = re.sub(r"\[[\d\s,;\-]+\]", "", clm.claim_text).strip().lower()
                            for sent in ans_sentences:
                                s_cids = self.cit_verifier.extract_inline_citation_ids(sent)
                                if not s_cids:
                                    continue
                                clean_s = re.sub(r"\[[\d\s,;\-]+\]", "", sent).strip().lower()
                                if clean_c == clean_s or clean_c in clean_s or clean_s in clean_c:
                                    clm.citation_ids = s_cids
                                    break
                            if not clm.citation_ids and len(proposed.claims) == 1 and ans_cids:
                                if clean_c in proposed.answer.lower():
                                    clm.citation_ids = list(ans_cids)

        # 3. Step 3: Deterministic Citation Verification
        t_cit_start = time.perf_counter()
        verified_citations, cit_warnings, invalid_cids = self.cit_verifier.verify_and_reconstruct(
            answer_text=proposed.answer,
            proposed_citation_ids=proposed.citation_ids,
            context_items=context_items,
        )
        citation_verifier_latency = (time.perf_counter() - t_cit_start) * 1000.0
        warnings.extend(cit_warnings)

        # 4. Step 4: Deterministic Conflict Detection
        t_conf_start = time.perf_counter()
        conflicts_detected, conflict_details = self._detect_conflicting_evidence(context_items, proposed)
        conflict_detector_latency = (time.perf_counter() - t_conf_start) * 1000.0

        # 5. Step 5: Deterministic Grounding & Claim Verification
        t_grd_start = time.perf_counter()
        if enable_verification:
            grounding_status, verified_claims, grd_warnings = self.grd_verifier.verify_grounding(
                answer_text=proposed.answer,
                context_items=context_items,
                proposed_claims=proposed.claims,
                insufficient_evidence_flag=proposed.insufficient_evidence,
            )
            warnings.extend(grd_warnings)
        else:
            grounding_status = GroundingStatus.FULLY_GROUNDED if verified_citations else GroundingStatus.UNSUPPORTED
            verified_claims = []

        # If fabricated citations were detected, grounding cannot be fully grounded
        if invalid_cids and grounding_status == GroundingStatus.FULLY_GROUNDED:
            grounding_status = GroundingStatus.PARTIALLY_GROUNDED

        grounding_verifier_latency = (time.perf_counter() - t_grd_start) * 1000.0

        total_rag_latency = (time.perf_counter() - start_total) * 1000.0

        # Token counting for telemetry
        comp_tokens = self.builder.count_tokens(proposed.answer)

        diagnostics = RAGDiagnostics(
            query=query,
            provider=settings.LLM_PROVIDER,
            model=settings.LLM_MODEL_NAME,
            llm_latency_ms=round(llm_latency, 2),
            prompt_builder_latency_ms=round(prompt_builder_latency, 2),
            citation_verifier_latency_ms=round(citation_verifier_latency, 2),
            grounding_verifier_latency_ms=round(grounding_verifier_latency, 2),
            conflict_detector_latency_ms=round(conflict_detector_latency, 2),
            total_rag_latency_ms=round(total_rag_latency, 2),
            prompt_tokens=prompt_payload["prompt_tokens"],
            completion_tokens=comp_tokens,
            evidence_count=len(context_items),
            citation_count=len(verified_citations),
            total_claims_count=len(verified_claims),
            supported_claims_count=sum(1 for c in verified_claims if c.status == ClaimStatus.SUPPORTED),
            unsupported_claims_count=sum(1 for c in verified_claims if c.status == ClaimStatus.UNSUPPORTED),
            degraded_mode=degraded_mode,
            warnings=warnings,
            phase7_diagnostics=phase7_diagnostics,
        )

        return RAGAnswer(
            query=query,
            answer=proposed.answer,
            grounding_status=grounding_status,
            citations=verified_citations,
            claims=verified_claims,
            insufficient_evidence=proposed.insufficient_evidence or (grounding_status == GroundingStatus.INSUFFICIENT_EVIDENCE),
            conflicts_detected=conflicts_detected,
            conflict_details=conflict_details,
            warnings=warnings,
            diagnostics=diagnostics,
        )


# Global synthesis service singleton
rag_synthesis_service = RAGSynthesisService()
