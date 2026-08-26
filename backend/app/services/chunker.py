"""
Structure-Aware Chunking & Metadata Enrichment Service.
Recursively splits parsed document elements into token-bounded chunks (target 450, max 512 tokens),
preserves table integrity, injects context breadcrumbs, applies intra-section overlap,
and constructs JSON-safe provenance metadata.
"""
import hashlib
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple
import tiktoken
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.db.models.document_chunk import DocumentChunk
from backend.app.schemas.chunk import ChunkDTO, ChunkMetadata, ChunkingConfig
from backend.app.schemas.parser import ElementType, ParsedDocument, ParsedElement


class ChunkingError(Exception):
    """Base exception for chunking operations."""
    pass


class TableTooLargeError(ChunkingError):
    """Raised when a table header or single row exceeds the maximum chunk size ceiling."""
    pass


class StructureAwareChunkerService:
    """
    Structure-aware chunker enforcing strict token ceilings (<=512 tokens),
    table integrity, section-restricted overlap, and transactional persistence.
    """

    def __init__(self):
        self._tokenizers: Dict[str, tiktoken.Encoding] = {}

    def _get_tokenizer(self, encoding_name: str) -> tiktoken.Encoding:
        """
        Retrieves or caches a tiktoken encoding instance.
        """
        if encoding_name not in self._tokenizers:
            try:
                self._tokenizers[encoding_name] = tiktoken.get_encoding(encoding_name)
            except Exception:
                self._tokenizers[encoding_name] = tiktoken.get_encoding("cl100k_base")
        return self._tokenizers[encoding_name]

    def count_tokens(self, text: str, encoding_name: str = "cl100k_base") -> int:
        """
        Counts tokens using the configured tiktoken tokenizer.
        """
        if not text:
            return 0
        tokenizer = self._get_tokenizer(encoding_name)
        return len(tokenizer.encode(text, disallowed_special=()))

    def _truncate_to_tokens(self, text: str, max_tokens: int, encoding_name: str) -> str:
        """
        Truncates text strictly to max_tokens.
        """
        if max_tokens <= 0:
            return ""
        tokenizer = self._get_tokenizer(encoding_name)
        tokens = tokenizer.encode(text, disallowed_special=())
        if len(tokens) <= max_tokens:
            return text
        return tokenizer.decode(tokens[:max_tokens])

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Splits text into sentences along standard punctuation boundaries.
        """
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def _format_breadcrumb(self, doc_title: Optional[str], section_path: Optional[str]) -> str:
        """
        Formats the context breadcrumb header.
        """
        if section_path and section_path.strip():
            return f"[Context: {section_path.strip()}]\n\n"
        elif doc_title and doc_title.strip():
            return f"[Context: {doc_title.strip()}]\n\n"
        return ""

    def _compute_chunk_hash(
        self,
        document_id: uuid.UUID,
        version_id: Optional[uuid.UUID],
        chunk_index: int,
        final_content: str,
    ) -> str:
        """
        Computes a deterministic SHA-256 hash on canonical chunk string.
        """
        ver_str = str(version_id) if version_id else "none"
        canonical = f"{document_id}:{ver_str}:{chunk_index}:{final_content}"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def create_chunks(
        self,
        parsed_doc: ParsedDocument,
        document_id: uuid.UUID,
        version_id: Optional[uuid.UUID] = None,
        config: Optional[ChunkingConfig] = None,
    ) -> List[ChunkDTO]:
        """
        Generates in-memory ChunkDTO objects from a ParsedDocument without DB interaction.
        """
        cfg = config or ChunkingConfig(
            target_size_tokens=settings.CHUNK_TARGET_SIZE_TOKENS,
            max_size_tokens=settings.CHUNK_MAX_SIZE_TOKENS,
            overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
            tokenizer_encoding=settings.CHUNK_TOKENIZER_ENCODING,
        )

        if not parsed_doc.all_elements:
            return []

        chunks: List[ChunkDTO] = []
        encoding = cfg.tokenizer_encoding
        doc_title = parsed_doc.document_title

        # Filter elements: absorb pure headings into breadcrumbs, chunk body paragraphs/tables/lists
        content_elements = [
            e for e in parsed_doc.all_elements
            if e.element_type not in (ElementType.HEADING_1, ElementType.HEADING_2, ElementType.HEADING_3, ElementType.TITLE)
        ]

        if not content_elements:
            return []

        # Group elements by continuous section path
        section_groups: List[Tuple[str, List[ParsedElement]]] = []
        current_section = content_elements[0].section_path or ""
        current_group: List[ParsedElement] = []

        for elem in content_elements:
            elem_section = elem.section_path or ""
            if elem_section != current_section:
                if current_group:
                    section_groups.append((current_section, current_group))
                current_section = elem_section
                current_group = [elem]
            else:
                current_group.append(elem)

        if current_group:
            section_groups.append((current_section, current_group))

        chunk_index = 0

        for section_path, elements in section_groups:
            breadcrumb = self._format_breadcrumb(doc_title, section_path) if cfg.include_breadcrumbs else ""
            breadcrumb_tokens = self.count_tokens(breadcrumb, encoding)

            # Check if breadcrumb alone violates ceiling
            if breadcrumb_tokens >= cfg.max_size_tokens:
                breadcrumb = self._truncate_to_tokens(breadcrumb, 50, encoding)
                breadcrumb_tokens = self.count_tokens(breadcrumb, encoding)

            available_budget = cfg.max_size_tokens - breadcrumb_tokens
            target_budget = min(cfg.target_size_tokens, available_budget)

            # Intra-section working buffers
            curr_text_parts: List[str] = []
            curr_elements: List[ParsedElement] = []
            prev_trailing_text: Optional[str] = None

            for elem in elements:
                # Handle Table elements atomically or slice row-by-row
                if elem.element_type == ElementType.TABLE:
                    # Flush any pending text before table
                    if curr_text_parts:
                        chunk_dto, prev_trailing_text = self._build_chunk(
                            document_id=document_id,
                            version_id=version_id,
                            chunk_index=chunk_index,
                            breadcrumb=breadcrumb,
                            breadcrumb_tokens=breadcrumb_tokens,
                            body_text="\n\n".join(curr_text_parts),
                            overlap_text=prev_trailing_text,
                            contributing_elements=curr_elements,
                            doc_title=doc_title,
                            section_path=section_path,
                            is_table=False,
                            cfg=cfg,
                        )
                        chunks.append(chunk_dto)
                        chunk_index += 1
                        curr_text_parts = []
                        curr_elements = []
                        prev_trailing_text = None  # No overlap from text into table

                    table_chunks = self._chunk_table(
                        elem=elem,
                        document_id=document_id,
                        version_id=version_id,
                        doc_title=doc_title,
                        section_path=section_path,
                        breadcrumb=breadcrumb,
                        breadcrumb_tokens=breadcrumb_tokens,
                        start_index=chunk_index,
                        cfg=cfg,
                    )
                    chunks.extend(table_chunks)
                    chunk_index += len(table_chunks)
                    prev_trailing_text = None  # No overlap from table into text
                    continue

                # Normal Paragraph / List item processing
                elem_text = elem.content.strip()
                if not elem_text:
                    continue

                elem_tokens = self.count_tokens(elem_text, encoding)

                # If single paragraph exceeds target budget, split into sentences
                if elem_tokens > target_budget:
                    sentences = self._split_into_sentences(elem_text)
                    for sent in sentences:
                        sent_tokens = self.count_tokens(sent, encoding)
                        curr_tokens = self.count_tokens("\n\n".join(curr_text_parts), encoding)

                        if curr_text_parts and (curr_tokens + sent_tokens > target_budget):
                            chunk_dto, prev_trailing_text = self._build_chunk(
                                document_id=document_id,
                                version_id=version_id,
                                chunk_index=chunk_index,
                                breadcrumb=breadcrumb,
                                breadcrumb_tokens=breadcrumb_tokens,
                                body_text="\n\n".join(curr_text_parts),
                                overlap_text=prev_trailing_text,
                                contributing_elements=curr_elements,
                                doc_title=doc_title,
                                section_path=section_path,
                                is_table=False,
                                cfg=cfg,
                            )
                            chunks.append(chunk_dto)
                            chunk_index += 1
                            curr_text_parts = []
                            curr_elements = []

                        # If single sentence exceeds budget, truncate or slice strictly
                        if sent_tokens > available_budget:
                            sent = self._truncate_to_tokens(sent, available_budget, encoding)

                        curr_text_parts.append(sent)
                        if elem not in curr_elements:
                            curr_elements.append(elem)
                else:
                    curr_tokens = self.count_tokens("\n\n".join(curr_text_parts), encoding)
                    if curr_text_parts and (curr_tokens + elem_tokens > target_budget):
                        chunk_dto, prev_trailing_text = self._build_chunk(
                            document_id=document_id,
                            version_id=version_id,
                            chunk_index=chunk_index,
                            breadcrumb=breadcrumb,
                            breadcrumb_tokens=breadcrumb_tokens,
                            body_text="\n\n".join(curr_text_parts),
                            overlap_text=prev_trailing_text,
                            contributing_elements=curr_elements,
                            doc_title=doc_title,
                            section_path=section_path,
                            is_table=False,
                            cfg=cfg,
                        )
                        chunks.append(chunk_dto)
                        chunk_index += 1
                        curr_text_parts = []
                        curr_elements = []

                    curr_text_parts.append(elem_text)
                    curr_elements.append(elem)

            # Flush any remaining text in section
            if curr_text_parts:
                chunk_dto, _ = self._build_chunk(
                    document_id=document_id,
                    version_id=version_id,
                    chunk_index=chunk_index,
                    breadcrumb=breadcrumb,
                    breadcrumb_tokens=breadcrumb_tokens,
                    body_text="\n\n".join(curr_text_parts),
                    overlap_text=prev_trailing_text,
                    contributing_elements=curr_elements,
                    doc_title=doc_title,
                    section_path=section_path,
                    is_table=False,
                    cfg=cfg,
                )
                chunks.append(chunk_dto)
                chunk_index += 1

        return chunks

    def _build_chunk(
        self,
        document_id: uuid.UUID,
        version_id: Optional[uuid.UUID],
        chunk_index: int,
        breadcrumb: str,
        breadcrumb_tokens: int,
        body_text: str,
        overlap_text: Optional[str],
        contributing_elements: List[ParsedElement],
        doc_title: Optional[str],
        section_path: Optional[str],
        is_table: bool,
        cfg: ChunkingConfig,
    ) -> Tuple[ChunkDTO, str]:
        """
        Assembles breadcrumb + overlap + body content, verifies strict <= 512 token limit,
        and constructs the ChunkDTO object.
        """
        encoding = cfg.tokenizer_encoding
        clean_body = body_text.strip()

        # Extract trailing sentence for overlap into next chunk (if not a table)
        sentences = self._split_into_sentences(clean_body)
        trailing_overlap = sentences[-1] if sentences else clean_body

        # Validate overlap addition within ceiling
        effective_overlap = ""
        if overlap_text and overlap_text.strip() and not is_table:
            candidate_overlap = overlap_text.strip()
            overlap_tokens = self.count_tokens(candidate_overlap, encoding)
            if overlap_tokens > cfg.overlap_tokens:
                candidate_overlap = self._truncate_to_tokens(candidate_overlap, cfg.overlap_tokens, encoding)

            # Ensure breadcrumb + overlap + body <= max_size_tokens
            test_content = breadcrumb + candidate_overlap + "\n\n" + clean_body
            if self.count_tokens(test_content, encoding) <= cfg.max_size_tokens:
                effective_overlap = candidate_overlap

        # Build final content string
        content_parts = []
        if breadcrumb:
            content_parts.append(breadcrumb.strip())
        if effective_overlap:
            content_parts.append(f"[... {effective_overlap}]")
        if clean_body:
            content_parts.append(clean_body)

        final_content = "\n\n".join(content_parts).strip()
        final_tokens = self.count_tokens(final_content, encoding)

        # Enforce strict hard ceiling (<=512 tokens)
        if final_tokens > cfg.max_size_tokens:
            final_content = self._truncate_to_tokens(final_content, cfg.max_size_tokens, encoding)
            final_tokens = self.count_tokens(final_content, encoding)

        # Metadata extraction
        page_numbers = sorted(list({e.page_number for e in contributing_elements if e.page_number is not None}))
        primary_page = page_numbers[0] if page_numbers else None
        element_types = list({e.element_type.value for e in contributing_elements})
        source_element_ids = [e.element_id for e in contributing_elements]
        bounding_boxes = [e.bbox for e in contributing_elements if e.bbox is not None]

        chunk_hash = self._compute_chunk_hash(document_id, version_id, chunk_index, final_content)

        metadata = ChunkMetadata(
            document_title=doc_title,
            section_path=section_path,
            primary_page=primary_page,
            page_numbers=page_numbers,
            element_types=element_types,
            source_element_ids=source_element_ids,
            bounding_boxes=bounding_boxes,
            token_count=final_tokens,
            char_count=len(final_content),
            is_table=is_table,
            chunk_hash=chunk_hash,
        )

        chunk_dto = ChunkDTO(
            document_id=document_id,
            version_id=version_id,
            chunk_index=chunk_index,
            content=final_content,
            page_number=primary_page,
            section_path=section_path,
            token_count=final_tokens,
            metadata=metadata,
        )

        return chunk_dto, trailing_overlap

    def _chunk_table(
        self,
        elem: ParsedElement,
        document_id: uuid.UUID,
        version_id: Optional[uuid.UUID],
        doc_title: Optional[str],
        section_path: Optional[str],
        breadcrumb: str,
        breadcrumb_tokens: int,
        start_index: int,
        cfg: ChunkingConfig,
    ) -> List[ChunkDTO]:
        """
        Slices tables strictly by row boundaries while repeating headers on every slice.
        """
        encoding = cfg.tokenizer_encoding
        lines = [line.strip() for line in elem.content.strip().split("\n") if line.strip()]

        if len(lines) < 2:
            # Degenerate single-line table
            chunk_dto, _ = self._build_chunk(
                document_id=document_id,
                version_id=version_id,
                chunk_index=start_index,
                breadcrumb=breadcrumb,
                breadcrumb_tokens=breadcrumb_tokens,
                body_text=elem.content,
                overlap_text=None,
                contributing_elements=[elem],
                doc_title=doc_title,
                section_path=section_path,
                is_table=True,
                cfg=cfg,
            )
            return [chunk_dto]

        # Extract markdown table header row + separator row
        header_block = lines[0] + "\n" + lines[1]
        data_rows = lines[2:]

        base_header_text = (breadcrumb + header_block).strip()
        base_header_tokens = self.count_tokens(base_header_text, encoding)

        if base_header_tokens >= cfg.max_size_tokens:
            raise TableTooLargeError(
                f"Table header plus context breadcrumb ({base_header_tokens} tokens) exceeds "
                f"maximum chunk size ceiling ({cfg.max_size_tokens} tokens)."
            )

        available_for_rows = cfg.max_size_tokens - base_header_tokens
        target_for_rows = min(cfg.target_size_tokens - base_header_tokens, available_for_rows)

        table_chunks: List[ChunkDTO] = []
        current_rows: List[str] = []
        curr_idx = start_index

        for row in data_rows:
            candidate_rows = current_rows + [row]
            candidate_body = header_block + "\n" + "\n".join(candidate_rows)
            candidate_tokens = self.count_tokens(breadcrumb + candidate_body, encoding)

            if current_rows and (candidate_tokens > cfg.target_size_tokens):
                # Flush current table slice
                body_text = header_block + "\n" + "\n".join(current_rows)
                chunk_dto, _ = self._build_chunk(
                    document_id=document_id,
                    version_id=version_id,
                    chunk_index=curr_idx,
                    breadcrumb=breadcrumb,
                    breadcrumb_tokens=breadcrumb_tokens,
                    body_text=body_text,
                    overlap_text=None,
                    contributing_elements=[elem],
                    doc_title=doc_title,
                    section_path=section_path,
                    is_table=True,
                    cfg=cfg,
                )
                table_chunks.append(chunk_dto)
                curr_idx += 1
                current_rows = [row]
            else:
                current_rows.append(row)

        if current_rows:
            body_text = header_block + "\n" + "\n".join(current_rows)
            chunk_dto, _ = self._build_chunk(
                document_id=document_id,
                version_id=version_id,
                chunk_index=curr_idx,
                breadcrumb=breadcrumb,
                breadcrumb_tokens=breadcrumb_tokens,
                body_text=body_text,
                overlap_text=None,
                contributing_elements=[elem],
                doc_title=doc_title,
                section_path=section_path,
                is_table=True,
                cfg=cfg,
            )
            table_chunks.append(chunk_dto)

        return table_chunks

    async def chunk_and_persist(
        self,
        document_id: uuid.UUID,
        parsed_doc: ParsedDocument,
        version_id: Optional[uuid.UUID] = None,
        db: Optional[AsyncSession] = None,
        config: Optional[ChunkingConfig] = None,
    ) -> List[DocumentChunk]:
        """
        Generates chunks and transactionally persists them to PostgreSQL.
        Replaces any existing chunks for the exact (document_id, version_id) pair.
        """
        if db is None:
            raise ValueError("AsyncSession 'db' must be provided for persistence.")

        chunks_dto = self.create_chunks(
            parsed_doc=parsed_doc,
            document_id=document_id,
            version_id=version_id,
            config=config,
        )

        try:
            # 1. Atomic delete of existing chunks for this specific version/document pair
            if version_id is None:
                delete_stmt = delete(DocumentChunk).where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.version_id.is_(None),
                )
            else:
                delete_stmt = delete(DocumentChunk).where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.version_id == version_id,
                )
            await db.execute(delete_stmt)

            # 2. Batch insert new chunks
            orm_chunks = [
                DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=dto.document_id,
                    version_id=dto.version_id,
                    chunk_index=dto.chunk_index,
                    content=dto.content,
                    metadata_json=dto.metadata.model_dump(),
                    page_number=dto.page_number,
                    section_path=dto.section_path,
                    token_count=dto.token_count,
                )
                for dto in chunks_dto
            ]

            if orm_chunks:
                db.add_all(orm_chunks)

            await db.commit()

            # Refresh and return
            return orm_chunks

        except Exception as e:
            await db.rollback()
            raise ChunkingError(f"Failed to persist document chunks: {str(e)}")


# Global chunker service instance
chunker_service = StructureAwareChunkerService()
