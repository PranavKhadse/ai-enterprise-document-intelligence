# Technology Stack & Tooling Decisions

> **Current Status: Planning & Architecture Phase**  
> *Notice: This document defines the planned technology stack for the project. No packages or dependencies have been installed yet.*

---

## 1. Planned Technology Stack Overview

| Component | Technology Selected | Primary Purpose | Why Selected | Possible Alternatives Considered |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Framework** | **Python 3.11+ / FastAPI** | Core REST & streaming API gateway; pipeline orchestration | Native async/await concurrency for I/O-bound LLM calls; automatic OpenAPI/Swagger docs; type validation via Pydantic; rich AI/ML ecosystem. | Django Ninja, Flask, Go (Gin/Fiber), Node.js (Express/Fastify) |
| **Frontend Framework** | **React (Vite) + Vanilla CSS** | Web UI for document upload, streaming Q&A, citation viewer, diff viewer, eval dashboard | High responsiveness, fast component state updates for token streaming, zero bloated CSS overhead, full design flexibility with custom tokens. | Next.js, Vue.js, SvelteKit, Streamlit |
| **Vector Database** | **Qdrant** | Dense vector storage and approximate nearest neighbor (ANN) retrieval | Written in Rust (high performance/low memory); native payload indexing; first-class support for pre-retrieval metadata filtering (crucial for RBAC). | Milvus, Pinecone, Weaviate, pgvector, ChromaDB |
| **Relational Database** | **PostgreSQL 16+** | Persistent store for users, RBAC roles, document metadata, version history, query logs, evaluations | ACID compliance; robust relational constraints; structured JSONB support; battle-tested enterprise standard. | MySQL, SQLite, MongoDB |
| **Sparse Retrieval Engine** | **BM25 (`rank-bm25` / Tantivy)** | Exact keyword, acronym, clause code, and error-code search | Deterministic lexical scoring based on TF-IDF principles with document length normalization; negligible index computation cost. | Elasticsearch, OpenSearch, Whoosh |
| **Dense Embedding Model** | **Sentence Transformers (`BAAI/bge-large-en-v1.5`)** | High-dimensional semantic text representation (1024-dim) | State-of-the-art MTEB benchmark performance; strong semantic retrieval across general and domain-specific enterprise texts; open weights. | `text-embedding-3-large`, `gte-large`, `e5-mistral-7b` |
| **Reranking Engine** | **Cross-Encoder (`BAAI/bge-reranker-large`)** | Deep token-to-token cross-attention scoring on candidate passages | Significantly higher precision than bi-encoders; eliminates false positives from initial candidate retrieval pool. | `ms-marco-MiniLM-L-6-v2`, Cohere Rerank API, ColBERTv2 |
| **LLM Gateway Layer** | **Swappable Client (OpenAI / Anthropic / Gemini / Local)** | Reasoning, synthesis, grounded generation, and query rewriting | Provider-agnostic abstraction; allows seamless switching between hosted frontier APIs and self-hosted models (via Ollama/vLLM) without application code refactoring. | Hardcoded OpenAI SDK, LangChain, LlamaIndex |
| **Testing Framework** | **Pytest + Pytest-Asyncio** | Automated unit, integration, and evaluation benchmark tests | Standard Python testing framework; rich fixture ecosystem; native async test support; parameterized test cases. | Unittest, Nose2 |
| **Containerization & Orchestration** | **Docker & Docker Compose** | Reproducible multi-service local and staging deployment | Eliminates environment drift; single-command startup for FastAPI, PostgreSQL, Qdrant, and React frontend. | Kubernetes, Podman, Bare-metal VMs |
| **Version Control** | **Git & GitHub** | Source code management, issue tracking, and versioned releases | Industry standard for collaborative version control and CI/CD integration. | GitLab, Bitbucket |

---

## 2. In-Depth Rationale for Key Architectural Selections

### Why Qdrant over pgvector for Vector Search?
- While `pgvector` allows storing vectors inside PostgreSQL, **Qdrant** is dedicated to vector indexing.
- Qdrant builds and manages in-memory **Hierarchical Navigable Small World (HNSW)** graphs with custom payload indices. This guarantees sub-millisecond approximate nearest neighbor search even when applying complex pre-retrieval filters (`department_id == 'HR' AND clearance >= 2`).
- Separating vector compute (Qdrant) from relational transactions (PostgreSQL) prevents heavy vector queries from exhausting database connection pools or CPU cycles needed for CRUD operations.

### Why BM25 + Dense Vectors (Hybrid) rather than Vector Search Alone?
- Vector embeddings compress text into a fixed mathematical space. While excellent for semantic queries (*"leave benefits"* $\to$ *"parental time off"*), embeddings frequently fail on:
  - Exact error codes (e.g., `ERR_AUTH_SESSION_EXPIRED_502`)
  - Specific alphanumeric clause markers (e.g., `Section 4.1.2-B`)
  - Specialized product acronyms and SKU numbers
- BM25 calculates exact term matches weighted by inverse document frequency ($IDF$), ensuring that rare, exact keywords are never missed during retrieval.

### Why Cross-Encoder Reranking after Reciprocal Rank Fusion (RRF)?
- Bi-encoders encode queries and passages independently into vectors, meaning they cannot model interaction between individual words in the query and individual words in the passage.
- Cross-encoders take the concatenated pair `[CLS] Query [SEP] Passage [SEP]` and run full self-attention across every token.
- Running a cross-encoder over 1,000,000 chunks is too slow ($O(N)$ transformer forward passes), but running it over the **Top 30 candidates** produced by fast hybrid retrieval adds only $\sim 30\text{--}50\text{ ms}$ while boosting precision significantly.

---

## 3. Package and Dependency Status

> **Current Installation Status:** Zero packages installed.  
> *All installations, virtual environment setups, and Docker containers will be initiated sequentially starting in Phase 1 of the implementation roadmap.*
