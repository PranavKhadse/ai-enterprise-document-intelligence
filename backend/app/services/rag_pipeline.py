"""
End-to-End Grounded RAG Pipeline Orchestrator.
Coordinates Phase 6 Hybrid Retrieval -> Phase 7 Cross-Encoder Reranking & Compression -> Phase 8 Grounded Synthesis & Verification.
"""
from typing import Optional
from backend.app.schemas.rag import RAGAnswer, RAGQueryRequest
from backend.app.schemas.reranking import RerankedRetrievalResponse
from backend.app.schemas.retrieval import HybridRetrievalResponse
from backend.app.services.hybrid_retriever import HybridRetrievalService, hybrid_retriever
from backend.app.services.rag_synthesis import RAGSynthesisService, rag_synthesis_service
from backend.app.services.reranking_pipeline import RerankingPipelineService, reranking_pipeline


class RAGPipelineService:
    """
    Unified enterprise RAG pipeline orchestrator executing:
    Hybrid Retrieval -> ONNX Reranking & Evidence Packing -> Grounded Synthesis & Verification.
    """

    def __init__(
        self,
        retriever: Optional[HybridRetrievalService] = None,
        reranker: Optional[RerankingPipelineService] = None,
        synthesis: Optional[RAGSynthesisService] = None,
    ):
        self.retriever = retriever or hybrid_retriever
        self.reranker = reranker or reranking_pipeline
        self.synthesis = synthesis or rag_synthesis_service

    async def query(self, request: RAGQueryRequest) -> RAGAnswer:
        """
        Executes the complete multi-phase RAG pipeline on the user query request.
        """
        query_str = request.query.strip()
        if not query_str:
            return await self.synthesis.synthesize(
                query="",
                context_items=[],
                enable_verification=request.enable_verification,
            )

        # 1. Phase 6: Hybrid Retrieval (Dense Vector + BM25 Lexical Search + RRF Fusion)
        retrieval_response: HybridRetrievalResponse = await self.retriever.retrieve(
            query=query_str,
            filter=request.filter,
            final_top_k=request.top_k,
        )

        # 2. Phase 7: Cross-Encoder Reranking, Context Compression & Evidence Selection
        reranked_response: RerankedRetrievalResponse = await self.reranker.process(
            query=query_str,
            retrieval_response=retrieval_response,
            top_k=request.top_k,
            max_context_tokens=request.max_context_tokens,
        )

        # 3. Phase 8: Grounded Synthesis, Prompt Sandboxing & Dual-Layer Verification
        answer: RAGAnswer = await self.synthesis.synthesize(
            query=query_str,
            context_items=reranked_response.context_items,
            temperature=request.temperature or 0.0,
            enable_verification=request.enable_verification,
            phase7_diagnostics=reranked_response.diagnostics,
        )

        return answer


# Global RAG pipeline service singleton
rag_pipeline_service = RAGPipelineService()
