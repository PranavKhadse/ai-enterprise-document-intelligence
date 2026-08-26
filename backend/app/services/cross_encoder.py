"""
Cross-Encoder Reranker Service using Native ONNX Runtime.
Computes fine-grained query-passage relevance scores using full cross-attention.
"""
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import onnxruntime as ort
import tiktoken
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer
from backend.app.core.config import settings
from backend.app.schemas.reranking import RerankerConfig, RerankedChunk
from backend.app.schemas.retrieval import ScoredChunk


class RerankerError(Exception):
    """Base exception for Cross-Encoder reranking operations."""
    pass


class ModelInitializationError(RerankerError):
    """Raised when the ONNX model or tokenizer fails to load."""
    pass


class CrossEncoderRerankerService:
    """
    Production-grade Cross-Encoder reranking engine powered by ONNX Runtime.
    Performs joint all-to-all token attention between query and candidate passages.
    """

    def __init__(
        self,
        config: Optional[RerankerConfig] = None,
        custom_inference_fn: Optional[Callable[[str, List[str]], List[float]]] = None,
    ):
        self.config = config or RerankerConfig(
            enabled=settings.RERANKER_ENABLED,
            model_name=settings.RERANKER_MODEL_NAME,
            onnx_filename=settings.RERANKER_ONNX_FILENAME,
            top_k=settings.RERANKER_TOP_K,
            candidate_window_size=settings.RERANKER_CANDIDATE_WINDOW,
            batch_size=settings.RERANKER_BATCH_SIZE,
            max_length=settings.RERANKER_MAX_LENGTH,
            query_max_tokens=settings.RERANKER_QUERY_MAX_TOKENS,
            timeout_seconds=settings.RERANKER_TIMEOUT_SECONDS,
        )
        self._session: Optional[ort.InferenceSession] = None
        self._tokenizer: Optional[Tokenizer] = None
        self._custom_inference_fn = custom_inference_fn

    def _get_tokenizer(self) -> Tokenizer:
        """
        Lazily loads and caches the Hugging Face Fast Tokenizer.
        """
        if self._tokenizer is None:
            try:
                self._tokenizer = Tokenizer.from_pretrained(self.config.model_name)
                self._tokenizer.enable_truncation(max_length=self.config.max_length)
                self._tokenizer.enable_padding(direction="right", pad_id=0, pad_token="[PAD]")
            except Exception as e:
                raise ModelInitializationError(
                    f"Failed to load tokenizer for '{self.config.model_name}': {str(e)}"
                )
        return self._tokenizer

    def _get_session(self) -> ort.InferenceSession:
        """
        Lazily loads and caches the ONNX Runtime InferenceSession with CPU execution provider.
        """
        if self._session is None:
            try:
                # Check if model is a local file or HF repo
                if os.path.exists(self.config.model_name):
                    model_path = self.config.model_name
                else:
                    model_path = hf_hub_download(
                        repo_id=self.config.model_name,
                        filename=self.config.onnx_filename,
                    )

                session_options = ort.SessionOptions()
                session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                session_options.intra_op_num_threads = 4

                self._session = ort.InferenceSession(
                    model_path,
                    sess_options=session_options,
                    providers=["CPUExecutionProvider"],
                )
            except Exception as e:
                raise ModelInitializationError(
                    f"Failed to initialize ONNX session for '{self.config.model_name}': {str(e)}"
                )
        return self._session

    def warmup_sync(self) -> None:
        """
        Synchronously loads the ONNX model, initializes tokenizer and session,
        and runs a minimal warm-up inference without altering ranking state.
        Safe for production pre-warming before serving live traffic.
        """
        if self._custom_inference_fn is not None:
            return
        self._get_tokenizer()
        self._get_session()
        self._predict_raw_logits(query="warmup", passages=["warmup query passage"], batch_size=1)

    async def warmup(self) -> None:
        """
        Asynchronous non-blocking model warmup executed in a background worker thread.
        """
        import asyncio
        await asyncio.to_thread(self.warmup_sync)

    def _predict_raw_logits(self, query: str, passages: List[str], batch_size: int) -> List[float]:
        """
        Executes synchronous batch inference through the ONNX Runtime engine.
        """
        if not passages:
            return []

        # If a custom inference function is provided (e.g. for offline unit testing), use it
        if self._custom_inference_fn is not None:
            return self._custom_inference_fn(query, passages)

        tok = self._get_tokenizer()
        sess = self._get_session()

        all_logits: List[float] = []

        for i in range(0, len(passages), batch_size):
            batch_passages = passages[i : i + batch_size]
            pairs = [(query, p) for p in batch_passages]

            # Batch encode pairs
            encodings = tok.encode_batch(pairs)

            input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
            token_type_ids = np.array([e.type_ids for e in encodings], dtype=np.int64)

            ort_inputs = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            }

            outputs = sess.run(None, ort_inputs)
            logits = outputs[0]  # Shape: (batch_size, 1)

            for item in logits:
                all_logits.append(float(item[0]))

        return all_logits

    def rerank_sync(
        self,
        query: str,
        candidates: List[ScoredChunk],
        top_k: Optional[int] = None,
        candidate_window_size: Optional[int] = None,
        batch_size: Optional[int] = None,
    ) -> List[RerankedChunk]:
        """
        Synchronous reranking helper.
        Slices candidate window, executes batch inference, applies 3-level deterministic tie-breaking,
        and constructs RerankedChunk instances with rank deltas.
        """
        if not candidates:
            return []

        window_size = candidate_window_size or self.config.candidate_window_size
        k = top_k or self.config.top_k
        bs = batch_size or self.config.batch_size

        # 1. Candidate Window Slicing (Top-N from Phase 6)
        sliced_candidates = candidates[:window_size]
        passages = [chunk.content for chunk in sliced_candidates]

        # 2. Batch Cross-Encoder Inference
        raw_logits = self._predict_raw_logits(query, passages, batch_size=bs)

        # 3. Associate and Compute Sigmoid Normalized Scores
        scored_candidates: List[Tuple[float, float, int, ScoredChunk]] = []
        for idx, (chunk, raw_logit) in enumerate(zip(sliced_candidates, raw_logits)):
            # Monotonic sigmoid normalization: 1 / (1 + e^-z)
            sigmoid_score = float(1.0 / (1.0 + np.exp(-raw_logit)))
            initial_rank = idx + 1
            scored_candidates.append((raw_logit, sigmoid_score, initial_rank, chunk))

        # 4. Deterministic 3-Level Tie-Breaking:
        # 1. reranker_raw_score DESC
        # 2. initial_retrieval_score DESC
        # 3. chunk_id UUID ASC
        scored_candidates.sort(
            key=lambda item: (
                item[0],  # raw logit DESC
                item[3].final_score,  # Phase 6 score DESC
                -int(item[3].chunk_id.int),  # chunk_id ASC (negated for reverse sort)
            ),
            reverse=True,
        )

        # 5. Build RerankedChunk Output List
        tok_encoder = tiktoken.get_encoding("cl100k_base")
        reranked_results: List[RerankedChunk] = []
        for new_rank, (raw_score, norm_score, init_rank, chunk) in enumerate(scored_candidates[:k], start=1):
            rank_delta = init_rank - new_rank
            orig_tokens = len(tok_encoder.encode(chunk.content, disallowed_special=()))

            reranked_results.append(
                RerankedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    version_id=chunk.version_id,
                    department_id=chunk.department_id,
                    content=chunk.content,
                    compressed_content=chunk.content,  # default to uncompressed
                    page_number=chunk.page_number,
                    section_path=chunk.section_path,
                    is_table=chunk.metadata.get("is_table", False),
                    reranker_raw_score=raw_score,
                    reranker_score=norm_score,
                    reranker_rank=new_rank,
                    rank_delta=rank_delta,
                    initial_retrieval_score=chunk.final_score,
                    initial_retrieval_rank=init_rank,
                    dense_score=chunk.dense_score,
                    sparse_score=chunk.sparse_score,
                    dense_rank=chunk.dense_rank,
                    sparse_rank=chunk.sparse_rank,
                    rrf_score=chunk.rrf_score,
                    retrieval_methods=chunk.retrieval_methods,
                    original_token_count=orig_tokens,
                    compressed_token_count=orig_tokens,
                    compression_ratio=1.0,
                    metadata=chunk.metadata,
                )
            )

        return reranked_results


# Global Cross-Encoder service singleton
cross_encoder_service = CrossEncoderRerankerService()
