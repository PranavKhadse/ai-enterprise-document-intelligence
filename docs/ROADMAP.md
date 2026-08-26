# Development Roadmap & Implementation Plan

> **Current Status: Planning & Architecture Phase**  
> *Development Rule: We will implement strictly ONE phase at a time. Each phase must satisfy its completion criteria and automated tests before proceeding to the next.*

---

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               15-PHASE ROADMAP OVERVIEW                                │
├────────────────────────┬────────────────────────┬──────────────────────────────────────┤
│ Phase 1: Foundation    │ Phase 2: Parser        │ Phase 3: Smart Chunker               │
│ Phase 4: Dense Vector  │ Phase 5: BM25 Sparse   │ Phase 6: Hybrid + RRF                │
│ Phase 7: Cross-Encoder │ Phase 8: RAG Generator │ Phase 9: Citations & Grounding       │
│ Phase 10: Doc Diff     │ Phase 11: RBAC & Auth  │ Phase 12: Evaluation & Benchmarks    │
│ Phase 13: React UI     │ Phase 14: Observability│ Phase 15: Dockerization & Deployment │
└────────────────────────┴────────────────────────┴──────────────────────────────────────┘
```

---

## Phase 1: Project Foundation & Domain Entities
- **Objective:** Establish the production repository structure, configuration management, database connections, and ORM domain models.
- **What We Build:**
  - Python virtual environment configuration and dependency specifications.
  - Production directory layout (`app/core`, `app/db`, `app/api`, `app/services`, `app/schemas`).
  - Configuration management using `pydantic-settings` reading from `.env`.
  - PostgreSQL database connection engine with SQLAlchemy async session maker.
  - Core database models: `User`, `Role`, `Department`, `Document`, `DocumentChunk`, `QueryLog`, `EvaluationResult`.
  - Alembic database migration scripts.
- **What to Study:**
  - SQLAlchemy 2.0 async paradigms and relationship mapping.
  - Pydantic v2 data validation and settings management.
  - Database indexing strategies for search and time-series logging.
- **Interview Readiness:**
  - How to design a normalized relational schema supporting multi-tenant document management.
  - Benefits of async database drivers (`asyncpg`) in high-concurrency Python backends.
- **Completion Criteria:**
  - Clean project layout created.
  - Database models defined and verified via initial Alembic migration test.

---

## Phase 2: Document Parsing & Ingestion Engine
- **Objective:** Build a robust, structure-aware document parsing service supporting PDFs, DOCX, and Markdown.
- **What We Build:**
  - Structure-aware parser using `PyMuPDF` (and fallback parsers).
  - Heading hierarchy detection (H1, H2, H3), table structure preservation (markdown table format), and page number mapping.
  - SHA-256 document deduplication service.
- **What to Study:**
  - PDF object tree structure (text blocks, fonts, coordinates, bounding boxes).
  - Table extraction techniques (heuristics vs. structural layout parsers).
- **Interview Readiness:**
  - Why standard `pypdf` or raw text extractors fail on multi-column layouts and tables.
  - Trade-offs between rule-based PDF extractors and vision-based layout models (LayoutLM).
- **Completion Criteria:**
  - Unit tests parsing sample PDFs containing tables, multi-column layouts, and nested headers with 100% text and page boundary fidelity.

---

## Phase 3: Structure-Aware Chunking & Metadata Enrichment
- **Objective:** Implement an intelligent, structure-aware text chunking algorithm that preserves parent context and prevents sentence fragmentation.
- **What We Build:**
  - Recursive structure-aware chunker (configurable target chunk size: 400–600 tokens, 50-token overlap).
  - Hierarchical breadcrumb injector that prepends document title and section paths (e.g., `Handbook.pdf > Section 3: Benefits > Paternity Leave`).
  - Metadata enrichment tagging each chunk with page numbers, byte offsets, and access clearance levels.
- **What to Study:**
  - Tokenization algorithms (Byte-Pair Encoding, WordPiece) and chunk size trade-offs.
  - Context loss and boundary clipping effects in information retrieval.
- **Interview Readiness:**
  - How chunk size directly affects embedding density and retrieval precision.
  - What context breadcrumbs are and why they prevent chunk orphan syndrome.
- **Completion Criteria:**
  - Chunking test suite validating that tables and sentences are never clipped mid-boundary, and breadcrumbs are correctly attached.

---

## Phase 4: Dense Vector Retrieval with Qdrant
- **Objective:** Generate high-dimensional dense embeddings and integrate with Qdrant for approximate nearest neighbor vector search.
- **What We Build:**
  - Embedding service wrapping open transformer models (e.g., `BAAI/bge-large-en-v1.5`).
  - Qdrant collection manager with distance metrics (Cosine Similarity / Dot Product).
  - Vector indexing pipeline that upserts embeddings alongside structured JSON payloads.
  - Baseline vector search service returning Top-K most similar chunks.
- **What to Study:**
  - Vector similarity math (Cosine Similarity, Dot Product, Euclidean Distance).
  - Approximate Nearest Neighbor (ANN) algorithms, specifically Hierarchical Navigable Small World (HNSW).
- **Interview Readiness:**
  - How HNSW graph construction balances search speed ($O(\log N)$) vs. index build time and memory usage.
  - Why normalizing vectors allows dot product to compute cosine similarity faster.
- **Completion Criteria:**
  - Ingestion of test documents into Qdrant and verification of semantic search queries returning relevant chunks.

---

## Phase 5: BM25 Sparse Keyword Retrieval
- **Objective:** Implement a fast, deterministic BM25 inverted index for exact keyword, error code, and acronym search.
- **What We Build:**
  - Tokenization and text normalization pipeline (lowercasing, punctuation stripping, stopword handling).
  - BM25 inverted index builder and search service (`rank-bm25` / Tantivy).
  - Lexical search interface matching the candidate output format of the vector search service.
- **What to Study:**
  - The BM25 probabilistic relevance framework: Term Frequency ($TF$) saturation ($k_1$ parameter) and Document Length normalization ($b$ parameter).
  - Differences between TF-IDF and BM25.
- **Interview Readiness:**
  - Why $TF$ saturation in BM25 prevents a word repeated 100 times from dominating search results.
  - Why dense vectors struggle with exact error codes or SKU IDs where BM25 excels.
- **Completion Criteria:**
  - Tests proving BM25 correctly matches specific alphanumeric codes and rare acronyms where vector search fails.

---

## Phase 6: Hybrid Retrieval & Reciprocal Rank Fusion (RRF)
- **Objective:** Combine dense semantic search and sparse lexical retrieval using Reciprocal Rank Fusion.
- **What We Build:**
  - Parallel query execution engine querying Qdrant and BM25 simultaneously.
  - Reciprocal Rank Fusion (RRF) ranking algorithm module ($k=60$).
  - Hybrid search service delivering unified Top-K candidate chunks.
- **What to Study:**
  - Rank fusion mathematics (RRF vs. Weighted Score Normalization).
  - Convex combination vs. rank-based fusion techniques.
- **Interview Readiness:**
  - Why combining raw cosine scores and BM25 scores directly is mathematically flawed.
  - How RRF gracefully handles outlier scoring models without hyperparameter tuning.
- **Completion Criteria:**
  - Automated tests validating that queries with both semantic concepts and exact codes score highest when present in both candidate lists.

---

## Phase 7: Cross-Encoder Reranking
- **Objective:** Implement deep cross-attention reranking to elevate the most relevant candidate passages to the Top-5 positions.
- **What We Build:**
  - Cross-Encoder scoring service utilizing `BAAI/bge-reranker-large`.
  - Batch scoring pipeline that evaluates `(query, passage)` pairs for the Top-30 fused candidates.
  - Dynamic score thresholding to filter out low-confidence candidates.
- **What to Study:**
  - Bi-Encoder (Dual-Encoder) vs. Cross-Encoder architectural differences.
  - Full self-attention mechanics between concatenated query-passage token pairs.
- **Interview Readiness:**
  - Why cross-encoders achieve higher precision than bi-encoders.
  - The computational complexity trade-off ($O(N)$ transformer passes) and why rerankers are only applied to top candidates.
- **Completion Criteria:**
  - Benchmark tests demonstrating reranking improves top-1 and top-3 accuracy over raw RRF output.

---

## Phase 8: Grounded RAG Generation & Anti-Hallucination Guardrails
- **Objective:** Build the grounded LLM synthesis engine with strict evidence boundaries and fallback mechanisms.
- **What We Build:**
  - Provider-agnostic LLM client (OpenAI, Anthropic, Gemini, local Ollama).
  - Context Assembler structuring retrieved chunks into isolated XML tags (`<evidence>`).
  - Strict system prompt with anti-hallucination constraints and mandatory fallback responses when evidence is insufficient.
  - Server-Sent Events (SSE) streaming endpoint for token delivery.
- **What to Study:**
  - In-context learning, prompt engineering, and context window attention dynamics ("Lost in the Middle").
  - Grounding techniques and temperature/top-p sampling parameters.
- **Interview Readiness:**
  - How to structure prompts to prevent LLM hallucination when retrieved context does not contain the answer.
  - How streaming responses work via HTTP Server-Sent Events (SSE) in FastAPI.
- **Completion Criteria:**
  - Unit tests verifying the LLM outputs the fallback message when presented with irrelevant context, and generates grounded answers when provided with valid context.

---

## Phase 9: Citations & Grounding Verification
- **Objective:** Implement verifiable source attribution linking generated claims to exact document names, page numbers, and section breadcrumbs.
- **What We Build:**
  - Structured citation extraction engine mapping inline reference anchors (`[[REF_X]]`) to chunk metadata.
  - Claim verification checker that validates quoted statements against source chunk text.
  - API response model returning the answer along with structured citation objects.
- **What to Study:**
  - Natural Language Inference (NLI) concepts for claim entailment.
  - Deterministic string alignment and fuzzy matching algorithms.
- **Interview Readiness:**
  - How to build an auditable citation engine that prevents hallucinated references.
  - How citation verification increases user trust in enterprise settings.
- **Completion Criteria:**
  - Verification test showing 100% of generated citations match actual ingested document chunks and page numbers.

---

## Phase 10: Document Comparison & Conflict Detection
- **Objective:** Build an intelligent document intelligence service that detects policy changes and contradictions between document versions.
- **What We Build:**
  - Clause extraction and alignment engine matching sections across two document versions.
  - Semantic contradiction and divergence detection service using NLI / LLM comparison logic.
  - Diffing API endpoint returning added, modified, deleted, and conflicting clauses.
- **What to Study:**
  - Document diffing algorithms (Myers diff algorithm vs. Semantic Clause Alignment).
  - Natural Language Inference (Entailment, Contradiction, Neutral).
- **Interview Readiness:**
  - How semantic diffing differs from raw text diffing (git diff) for unstructured policies.
- **Completion Criteria:**
  - Test verifying that uploading two conflicting policy versions correctly identifies the specific contradicting clauses.

---

## Phase 11: Authentication & Role-Based Access Control (RBAC)
- **Objective:** Implement secure user authentication and pre-retrieval access control filtering.
- **What We Build:**
  - JWT-based authentication service with password hashing (bcrypt / Argon2).
  - Role and department assignment system (`Admin`, `HR_Manager`, `Legal`, `Employee`).
  - Pre-retrieval Qdrant and BM25 payload filters enforcing document clearance levels at search time.
- **What to Study:**
  - OAuth2 password bearer flow and JWT cryptographic signatures.
  - Pre-filtering vs. post-filtering in vector databases and security implications.
- **Interview Readiness:**
  - Why checking permissions post-retrieval is a major security flaw and causes silent search failures.
  - How Qdrant payload indices execute boolean filters before traversing the HNSW graph.
- **Completion Criteria:**
  - Red-team security test proving an employee role cannot retrieve chunks or answers from confidential management documents.

---

## Phase 12: Evaluation Suite & Benchmarking Harness
- **Objective:** Build an automated evaluation framework to measure retrieval metrics and generation quality against golden datasets.
- **What We Build:**
  - Retrieval metric evaluators: Recall@K, Precision@K, Mean Reciprocal Rank (MRR), NDCG@K, Hit Rate.
  - Generation quality evaluators: Faithfulness, Answer Relevance, Context Precision (LLM-as-a-judge).
  - Benchmark runner script producing reproducible Markdown and JSON evaluation reports.
- **What to Study:**
  - Information retrieval mathematics: Discounted Cumulative Gain ($DCG$) and Ideal DCG ($IDCG$).
  - RAG Triad evaluation methodology (Ragas / TruLens principles).
- **Interview Readiness:**
  - How to explain NDCG@K vs. Recall@K in an interview.
  - How LLM-as-a-judge works to evaluate faithfulness without human labeling.
- **Completion Criteria:**
  - End-to-end evaluation run executing against a curated test dataset producing genuine, calculated scores for all metrics.

---

## Phase 13: React Web Interface
- **Objective:** Build a modern, responsive web application for interacting with the platform.
- **What We Build:**
  - Clean UI with Vanilla CSS design tokens and dark/light modes.
  - Real-time streaming chat interface with interactive citation side-drawer.
  - Document management dashboard with upload dropzones and ingestion status indicators.
  - Document comparison and conflict visualization view.
  - Evaluation and telemetry dashboard displaying latency, token costs, and accuracy benchmarks.
- **What to Study:**
  - React hooks (`useState`, `useEffect`, `useCallback`), Server-Sent Events stream consumption via `fetch` ReadableStream.
  - Modern UI design systems, typography hierarchy, and glassmorphism.
- **Interview Readiness:**
  - How to handle real-time streaming LLM responses in React without UI re-render bottlenecks.
- **Completion Criteria:**
  - Working web application allowing end-to-end document upload, streaming Q&A, citation inspection, and diff viewing.

---

## Phase 14: Observability, Cost & Latency Tracking
- **Objective:** Implement detailed telemetry logging for every pipeline stage to monitor system health and operational costs.
- **What We Build:**
  - Middleware capturing per-stage latency (rewriting, dense search, BM25, RRF, reranking, LLM TTFT, generation).
  - Token counter and cost calculator based on LLM model pricing tables.
  - Query log persistence in PostgreSQL with query analytics API endpoints.
- **What to Study:**
  - OpenTelemetry concepts, structured JSON logging, and distributed tracing.
  - P95 and P99 latency percentiles and performance profiling.
- **Interview Readiness:**
  - How you diagnose latency bottlenecks in a multi-stage RAG pipeline.
- **Completion Criteria:**
  - Telemetry tests verifying that every query records exact millisecond latencies, token counts, and dollar costs to PostgreSQL.

---

## Phase 15: Dockerization & Production Deployment
- **Objective:** Package all services into a reproducible Docker Compose environment for single-command deployment.
- **What We Build:**
  - Multi-stage Dockerfile for FastAPI backend.
  - Optimized Nginx / Vite production build container for React frontend.
  - `docker-compose.yml` orchestrating FastAPI, React, Qdrant, PostgreSQL, and volume mounts.
  - Health check scripts and environment configuration templates.
- **What to Study:**
  - Multi-stage Docker builds, container networking, and resource limits (CPU/Memory).
- **Interview Readiness:**
  - How to containerize a complex ML/AI application and manage persistent storage across volumes.
- **Completion Criteria:**
  - Successful `docker compose up` spinning up all services cleanly with working end-to-end flows.
