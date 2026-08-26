"""
Real-model local ONNX integration tests.
Executes live inference using local cached ONNX model without network access.
Skips cleanly if model is not present in local cache.
"""
import math
import uuid
import numpy as np
import pytest
from backend.app.schemas.retrieval import ScoredChunk
from backend.app.services.cross_encoder import CrossEncoderRerankerService


def _get_local_model_and_tokenizer():
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    from tokenizers import Tokenizer

    repo_id = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    model_file = "onnx/model.onnx"

    try:
        model_path = hf_hub_download(repo_id=repo_id, filename=model_file, local_files_only=True)
        tok_path = hf_hub_download(repo_id=repo_id, filename="tokenizer.json", local_files_only=True)
    except (LocalEntryNotFoundError, Exception) as e:
        pytest.skip(f"Local ONNX model/tokenizer not cached ({str(e)}). Skipping real inference test.")

    tok = Tokenizer.from_file(tok_path)
    tok.enable_truncation(max_length=512)
    tok.enable_padding(direction="right", pad_id=0, pad_token="[PAD]")

    sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    return tok, sess


def test_real_local_onnx_cross_encoder_inference():
    """
    Verifies real ONNX Runtime inference using local cached model artifact with CPUExecutionProvider.
    """
    tok, sess = _get_local_model_and_tokenizer()
    assert "CPUExecutionProvider" in sess.get_providers()

    query = "What is the password policy?"
    passage = "The enterprise password policy mandates at least 12 characters and quarterly rotation."
    enc = tok.encode(query, passage)

    input_ids = np.array([enc.ids], dtype=np.int64)
    attention_mask = np.array([enc.attention_mask], dtype=np.int64)
    token_type_ids = np.array([enc.type_ids], dtype=np.int64)

    assert input_ids.shape[1] <= 512

    ort_inputs = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "token_type_ids": token_type_ids,
    }
    raw_outputs = sess.run(None, ort_inputs)
    logits = raw_outputs[0]

    assert logits.shape == (1, 1)
    raw_score = float(logits[0][0])
    assert not math.isnan(raw_score)
    assert not math.isinf(raw_score)

    reranker = CrossEncoderRerankerService()
    reranker.warmup_sync()

    test_chunk = ScoredChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=passage,
        final_score=0.75,
        section_path="Security > Password Policy",
        explanation="Real ONNX integration test candidate",
    )

    reranked_chunks = reranker.rerank_sync(
        query=query,
        candidates=[test_chunk],
        top_k=1,
    )

    assert len(reranked_chunks) == 1
    res = reranked_chunks[0]
    assert res.chunk_id == test_chunk.chunk_id
    assert not math.isnan(res.reranker_raw_score)
    assert not math.isnan(res.reranker_score)
    assert 0.0 <= res.reranker_score <= 1.0
    assert res.rank_delta == 0


def test_real_local_onnx_batch_and_truncation():
    """
    Verifies batch inference, sequence truncation at 512 tokens, and deterministic tie-breaking on live model.
    """
    tok, sess = _get_local_model_and_tokenizer()

    query = "Enterprise cloud security architecture " * 10  # Long query
    long_passage = "Security guidelines and database compliance rules. " * 80  # Long passage > 512 tokens
    short_passage = "Incident response SLA requires 15 minutes."

    # Truncation verification
    enc = tok.encode(query, long_passage)
    assert len(enc.ids) <= 512
    assert len(enc.attention_mask) <= 512

    reranker = CrossEncoderRerankerService()
    reranker.warmup_sync()

    chunk_long = ScoredChunk(
        chunk_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        document_id=uuid.uuid4(),
        content=long_passage,
        final_score=0.80,
        section_path="Security > Long Doc",
        explanation="Long test chunk",
    )
    chunk_short = ScoredChunk(
        chunk_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        document_id=uuid.uuid4(),
        content=short_passage,
        final_score=0.70,
        section_path="Security > Short Doc",
        explanation="Short test chunk",
    )

    # Batch rerank
    reranked = reranker.rerank_sync(
        query=query,
        candidates=[chunk_long, chunk_short],
        top_k=2,
        batch_size=2,
    )

    assert len(reranked) == 2
    for r in reranked:
        assert not math.isnan(r.reranker_raw_score)
        assert 0.0 <= r.reranker_score <= 1.0


def test_real_local_onnx_deterministic_tie_breaking():
    """
    Verifies that identical scores break ties deterministically by initial score DESC and chunk_id ASC.
    """
    _get_local_model_and_tokenizer()
    reranker = CrossEncoderRerankerService()

    content = "Identical content to produce equal raw logits."
    uuid_smaller = uuid.UUID("11111111-0000-0000-0000-000000000001")
    uuid_larger = uuid.UUID("99999999-0000-0000-0000-000000000009")

    # Case A: Same raw logits, different initial scores
    c1 = ScoredChunk(
        chunk_id=uuid_larger,
        document_id=uuid.uuid4(),
        content=content,
        final_score=0.90,
        section_path="Sec > A",
        explanation="Higher initial score",
    )
    c2 = ScoredChunk(
        chunk_id=uuid_smaller,
        document_id=uuid.uuid4(),
        content=content,
        final_score=0.50,
        section_path="Sec > B",
        explanation="Lower initial score",
    )

    results = reranker.rerank_sync(query="test query", candidates=[c2, c1], top_k=2)
    assert results[0].chunk_id == uuid_larger  # higher initial score wins

    # Case B: Same raw logits, same initial scores -> smaller chunk_id wins (ASC)
    c3 = ScoredChunk(
        chunk_id=uuid_smaller,
        document_id=uuid.uuid4(),
        content=content,
        final_score=0.80,
        section_path="Sec > A",
        explanation="Smaller UUID",
    )
    c4 = ScoredChunk(
        chunk_id=uuid_larger,
        document_id=uuid.uuid4(),
        content=content,
        final_score=0.80,
        section_path="Sec > B",
        explanation="Larger UUID",
    )

    results_tie = reranker.rerank_sync(query="test query", candidates=[c4, c3], top_k=2)
    assert results_tie[0].chunk_id == uuid_smaller  # smaller chunk_id wins
