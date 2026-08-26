"""
BM25 Sparse Lexical Search Engine with Inverted Indexing.
Implements BM25Okapi scoring, enterprise tokenization, payload filtering,
stale posting purging, snapshot rollback on failure, and atomic disk persistence.
"""
import copy
import math
import os
import pickle
import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from backend.app.core.config import settings
from backend.app.db.models.document import Document
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.schemas.bm25 import BM25Config, BM25SearchResult


class BM25Error(Exception):
    """Base exception for BM25 indexing and search operations."""
    pass


class IndexCorruptedError(BM25Error):
    """Raised when persisted index file on disk cannot be unpickled or is malformed."""
    pass


class BM25IndexService:
    """
    High-performance in-memory inverted index with BM25Okapi scoring,
    atomic persistence, and metadata filtering.
    """

    def __init__(self, config: Optional[BM25Config] = None, auto_load: bool = False):
        self.config = config or BM25Config(
            k1=settings.BM25_K1,
            b=settings.BM25_B,
            index_path=settings.BM25_INDEX_PATH,
            auto_persist=settings.BM25_AUTO_PERSIST,
        )

        # In-memory index structures
        self.corpus_size: int = 0  # N
        self.total_tokens: int = 0
        self.avg_doc_length: float = 0.0  # avgdl
        self.doc_lengths: Dict[str, int] = {}  # chunk_id -> int
        self.doc_metadata: Dict[str, Dict[str, Any]] = {}  # chunk_id -> payload dict
        self.postings: Dict[str, Dict[str, int]] = {}  # term -> {chunk_id: tf}

        # Tokenizer regex: matches c++, then alphanumeric compound tokens with internal hyphens, underscores, dots, or plus signs (e.g. RFC-4821, v2.1.0, error_500, w-2)
        self._token_pattern = re.compile(r"\bc\+\+|\b[a-zA-Z0-9]+(?:[-_.+][a-zA-Z0-9]+)*\b|\b\w+\b", re.IGNORECASE)

        if auto_load:
            self.load_from_disk()

    def tokenize(self, text: str) -> List[str]:
        """
        Tokenizes text while preserving enterprise identifiers, version tags, and codes.
        """
        if not text:
            return []
        matches = self._token_pattern.findall(text.lower())
        min_len = self.config.min_token_length
        return [m for m in matches if len(m) >= min_len]

    def _create_snapshot(self) -> Dict[str, Any]:
        """
        Creates a deep snapshot of the in-memory index state for transactional rollback.
        """
        return {
            "corpus_size": self.corpus_size,
            "total_tokens": self.total_tokens,
            "avg_doc_length": self.avg_doc_length,
            "doc_lengths": copy.deepcopy(self.doc_lengths),
            "doc_metadata": copy.deepcopy(self.doc_metadata),
            "postings": copy.deepcopy(self.postings),
        }

    def _restore_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Restores index state from a snapshot.
        """
        self.corpus_size = snapshot["corpus_size"]
        self.total_tokens = snapshot["total_tokens"]
        self.avg_doc_length = snapshot["avg_doc_length"]
        self.doc_lengths = snapshot["doc_lengths"]
        self.doc_metadata = snapshot["doc_metadata"]
        self.postings = snapshot["postings"]

    def _purge_document_version_internal(
        self, document_id: uuid.UUID, version_id: Optional[uuid.UUID]
    ) -> Set[str]:
        """
        Internal helper: removes all chunks belonging to (document_id, version_id)
        from inverted lists without triggering auto-persistence.
        """
        doc_id_str = str(document_id)
        ver_id_str = str(version_id) if version_id else None

        target_chunk_ids: Set[str] = set()
        for chunk_id, meta in list(self.doc_metadata.items()):
            if meta.get("document_id") == doc_id_str and meta.get("version_id") == ver_id_str:
                target_chunk_ids.add(chunk_id)

        if not target_chunk_ids:
            return set()

        # Remove from postings
        for term in list(self.postings.keys()):
            term_postings = self.postings[term]
            for cid in target_chunk_ids:
                term_postings.pop(cid, None)
            if not term_postings:
                del self.postings[term]

        # Remove from lengths and metadata
        for cid in target_chunk_ids:
            self.doc_lengths.pop(cid, None)
            self.doc_metadata.pop(cid, None)

        # Recompute corpus statistics
        self.corpus_size = len(self.doc_lengths)
        self.total_tokens = sum(self.doc_lengths.values())
        self.avg_doc_length = (
            (self.total_tokens / self.corpus_size) if self.corpus_size > 0 else 0.0
        )

        return target_chunk_ids

    def index_chunks(
        self,
        chunks: List[DocumentChunk],
        document: Document,
        auto_persist: Optional[bool] = None,
    ) -> int:
        """
        Indexes a batch of chunks for a given Document and version.
        Batches the operation: purges stale postings, inserts new chunks,
        recomputes statistics, and performs ONE atomic disk save on complete success.
        Rolls back in-memory state if an exception occurs.
        """
        if not chunks:
            return 0

        # Snapshot state for rollback safety
        snapshot = self._create_snapshot()

        try:
            doc_id = document.id
            ver_id = chunks[0].version_id if chunks else None

            # 1. Purge stale postings for this specific (document_id, version_id) pair
            self._purge_document_version_internal(doc_id, ver_id)

            # 2. Index new chunks
            for chunk in chunks:
                chunk_id = str(chunk.id)
                tokens = self.tokenize(chunk.content)
                doc_len = len(tokens)
                self.doc_lengths[chunk_id] = doc_len

                meta = chunk.metadata_json or {}
                payload = {
                    "document_id": str(document.id),
                    "version_id": str(chunk.version_id) if chunk.version_id else None,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "page_number": chunk.page_number,
                    "page_numbers": meta.get("page_numbers", [chunk.page_number] if chunk.page_number else []),
                    "section_path": chunk.section_path,
                    "document_title": document.title,
                    "department_id": str(document.department_id) if document.department_id else None,
                    "is_table": meta.get("is_table", False),
                    "token_count": chunk.token_count or doc_len,
                }
                self.doc_metadata[chunk_id] = payload

                # Term frequency accumulation
                tf_counts = Counter(tokens)
                for term, tf in tf_counts.items():
                    if term not in self.postings:
                        self.postings[term] = {}
                    self.postings[term][chunk_id] = tf

            # 3. Recompute corpus statistics
            self.corpus_size = len(self.doc_lengths)
            self.total_tokens = sum(self.doc_lengths.values())
            self.avg_doc_length = (
                (self.total_tokens / self.corpus_size) if self.corpus_size > 0 else 0.0
            )

            # 4. Operation-level atomic disk save
            should_persist = auto_persist if auto_persist is not None else self.config.auto_persist
            if should_persist:
                self.save_to_disk()

            return len(chunks)

        except Exception as e:
            # Transactional rollback to snapshot
            self._restore_snapshot(snapshot)
            raise BM25Error(f"BM25 indexing failed for document {document.id}: {str(e)}")

    def search(
        self,
        query: str,
        limit: int = 10,
        document_id: Optional[uuid.UUID] = None,
        version_id: Optional[uuid.UUID] = None,
        department_id: Optional[uuid.UUID] = None,
    ) -> List[BM25SearchResult]:
        """
        Executes BM25Okapi scoring across matching postings with optional metadata filtering.
        """
        q_terms = self.tokenize(query)
        if not q_terms or self.corpus_size == 0:
            return []

        doc_id_str = str(document_id) if document_id else None
        ver_id_str = str(version_id) if version_id else None
        dept_id_str = str(department_id) if department_id else None

        k1 = self.config.k1
        b = self.config.b
        N = self.corpus_size
        avgdl = self.avg_doc_length if self.avg_doc_length > 0 else 1.0

        scores: Dict[str, float] = defaultdict(float)

        for term in q_terms:
            if term not in self.postings:
                continue

            term_postings = self.postings[term]
            n_q = len(term_postings)  # document frequency

            # Standard BM25Okapi IDF with Robertson-Spärck Jones smoothing
            idf = math.log((N - n_q + 0.5) / (n_q + 0.5) + 1.0)

            for chunk_id, tf in term_postings.items():
                meta = self.doc_metadata.get(chunk_id, {})

                # Metadata Pre-Filtering
                if doc_id_str and meta.get("document_id") != doc_id_str:
                    continue
                if ver_id_str and meta.get("version_id") != ver_id_str:
                    continue
                if dept_id_str and meta.get("department_id") != dept_id_str:
                    continue

                doc_len = self.doc_lengths.get(chunk_id, 0)
                len_norm = 1.0 - b + b * (doc_len / avgdl)
                tf_score = (tf * (k1 + 1.0)) / (tf + k1 * len_norm)

                scores[chunk_id] += idf * tf_score

        if not scores:
            return []

        # Sort candidate chunks by BM25 score descending
        sorted_hits = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]

        results: List[BM25SearchResult] = []
        for chunk_id, score in sorted_hits:
            payload = self.doc_metadata.get(chunk_id, {})
            results.append(
                BM25SearchResult(
                    chunk_id=uuid.UUID(chunk_id),
                    document_id=uuid.UUID(payload["document_id"]),
                    version_id=uuid.UUID(payload["version_id"]) if payload.get("version_id") else None,
                    score=float(score),
                    content=payload.get("content", ""),
                    page_number=payload.get("page_number"),
                    section_path=payload.get("section_path"),
                    payload=payload,
                )
            )

        return results

    def delete_by_document(self, document_id: uuid.UUID) -> int:
        """
        Deletes all chunks for a document and performs an atomic save.
        """
        doc_id_str = str(document_id)
        target_chunk_ids: Set[str] = set()

        for chunk_id, meta in list(self.doc_metadata.items()):
            if meta.get("document_id") == doc_id_str:
                target_chunk_ids.add(chunk_id)

        if not target_chunk_ids:
            return 0

        snapshot = self._create_snapshot()
        try:
            for term in list(self.postings.keys()):
                term_postings = self.postings[term]
                for cid in target_chunk_ids:
                    term_postings.pop(cid, None)
                if not term_postings:
                    del self.postings[term]

            for cid in target_chunk_ids:
                self.doc_lengths.pop(cid, None)
                self.doc_metadata.pop(cid, None)

            self.corpus_size = len(self.doc_lengths)
            self.total_tokens = sum(self.doc_lengths.values())
            self.avg_doc_length = (
                (self.total_tokens / self.corpus_size) if self.corpus_size > 0 else 0.0
            )

            if self.config.auto_persist:
                self.save_to_disk()

            return len(target_chunk_ids)
        except Exception:
            self._restore_snapshot(snapshot)
            raise

    def delete_by_version(self, document_id: uuid.UUID, version_id: Optional[uuid.UUID]) -> int:
        """
        Deletes all chunks for a specific (document_id, version_id) and performs an atomic save.
        """
        snapshot = self._create_snapshot()
        try:
            purged = self._purge_document_version_internal(document_id, version_id)
            if purged and self.config.auto_persist:
                self.save_to_disk()
            return len(purged)
        except Exception:
            self._restore_snapshot(snapshot)
            raise

    def save_to_disk(self, file_path: Optional[str] = None) -> None:
        """
        Atomically persists index state to disk using a temporary file and os.replace.
        """
        target_path = Path(file_path or self.config.index_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_suffix(".tmp")

        state = {
            "corpus_size": self.corpus_size,
            "total_tokens": self.total_tokens,
            "avg_doc_length": self.avg_doc_length,
            "doc_lengths": self.doc_lengths,
            "doc_metadata": self.doc_metadata,
            "postings": self.postings,
        }

        try:
            with open(temp_path, "wb") as f:
                pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
            # Atomic replacement
            os.replace(temp_path, target_path)
        except Exception as e:
            if temp_path.exists():
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise BM25Error(f"Failed to atomically persist BM25 index to '{target_path}': {str(e)}")

    def load_from_disk(self, file_path: Optional[str] = None) -> bool:
        """
        Loads index state from the configured application-internal disk path.
        Treats pickle file strictly as application-internal trusted state.
        """
        target_path = Path(file_path or self.config.index_path)
        if not target_path.exists():
            return False

        try:
            with open(target_path, "rb") as f:
                state = pickle.load(f)

            self.corpus_size = state.get("corpus_size", 0)
            self.total_tokens = state.get("total_tokens", 0)
            self.avg_doc_length = state.get("avg_doc_length", 0.0)
            self.doc_lengths = state.get("doc_lengths", {})
            self.doc_metadata = state.get("doc_metadata", {})
            self.postings = state.get("postings", {})
            return True
        except Exception as e:
            # Fallback cleanly without crashing
            self.clear()
            raise IndexCorruptedError(f"Corrupted or invalid BM25 index file '{target_path}': {str(e)}")

    def clear(self) -> None:
        """
        Clears all in-memory index structures.
        """
        self.corpus_size = 0
        self.total_tokens = 0
        self.avg_doc_length = 0.0
        self.doc_lengths.clear()
        self.doc_metadata.clear()
        self.postings.clear()


# Global BM25 index service singleton
bm25_service = BM25IndexService()
