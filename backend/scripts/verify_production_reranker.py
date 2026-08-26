"""
Production Cross-Encoder ONNX Model Verification Script.
Strictly verifies that the required ONNX model and tokenizer exist in local cache,
can be initialized without errors, and produce valid logits.
"""
import sys
import numpy as np


def main():
    print("=== Phase 7 Production Cross-Encoder ONNX Verification ===")
    try:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
    except ImportError as e:
        print(f"[FAIL] Required library missing: {e}")
        sys.exit(1)

    repo_id = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    model_file = "onnx/model.onnx"

    print(f"1. Checking local model cache for '{repo_id}'...")
    try:
        model_path = hf_hub_download(repo_id=repo_id, filename=model_file, local_files_only=True)
        tok_path = hf_hub_download(repo_id=repo_id, filename="tokenizer.json", local_files_only=True)
        print(f"   [PASS] Found model artifact: {model_path}")
        print(f"   [PASS] Found tokenizer artifact: {tok_path}")
    except Exception as e:
        print(f"   [FAIL] Local artifacts not found in cache: {e}")
        sys.exit(1)

    print("2. Loading tokenizer and initializing ONNX Runtime session...")
    try:
        tok = Tokenizer.from_file(tok_path)
        tok.enable_truncation(max_length=512)
        tok.enable_padding(direction="right", pad_id=0, pad_token="[PAD]")

        sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        providers = sess.get_providers()
        print(f"   [PASS] Active execution providers: {providers}")
        assert "CPUExecutionProvider" in providers

        input_names = [i.name for i in sess.get_inputs()]
        input_types = [i.type for i in sess.get_inputs()]
        output_names = [o.name for o in sess.get_outputs()]
        output_types = [o.type for o in sess.get_outputs()]

        print(f"   [PASS] Model inputs: {dict(zip(input_names, input_types))}")
        print(f"   [PASS] Model outputs: {dict(zip(output_names, output_types))}")
    except Exception as e:
        print(f"   [FAIL] Model initialization failed: {e}")
        sys.exit(1)

    print("3. Executing test inference on sample enterprise query...")
    try:
        query = "What standard governs Path MTU Discovery?"
        passage = "Path MTU Discovery is specified in RFC-4821 using probe packets."
        enc = tok.encode(query, passage)

        inputs = {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
            "token_type_ids": np.array([enc.type_ids], dtype=np.int64),
        }

        outputs = sess.run(None, inputs)
        raw_logit = float(outputs[0][0][0])
        sigmoid_score = 1.0 / (1.0 + np.exp(-raw_logit))

        print(f"   [PASS] Direct ONNX output shape: {outputs[0].shape}")
        print(f"   [PASS] Output raw logit: {raw_logit:.4f}")
        print(f"   [PASS] Sigmoid relevance score: {sigmoid_score:.4f}")
    except Exception as e:
        print(f"   [FAIL] Inference execution failed: {e}")
        sys.exit(1)

    print("\n[SUCCESS] Production Cross-Encoder ONNX model verified successfully.")


if __name__ == "__main__":
    main()
