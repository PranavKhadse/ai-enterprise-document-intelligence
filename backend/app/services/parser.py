"""
PDF Parsing & Structural Extraction Engine using PyMuPDF.
Extracts headings, paragraphs, lists, and tables with spatial coordinates,
page numbers, and hierarchical breadcrumb paths.
"""
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import fitz  # PyMuPDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models.document import Document
from backend.app.schemas.parser import (
    ElementType,
    ParsedDocument,
    ParsedElement,
    ParsedPage,
)


class ParserError(Exception):
    """Base exception for parsing operations."""
    pass


class CorruptedPDFError(ParserError):
    """Raised when PDF binary is malformed or unreadable."""
    pass


class EncryptedPDFError(ParserError):
    """Raised when PDF is password-protected and cannot be parsed."""
    pass


class EmptyDocumentError(ParserError):
    """Raised when PDF contains zero pages or readable text."""
    pass


class PDFParserService:
    """
    High-performance, structure-aware PDF parsing service.
    """

    def parse_file(self, file_path: str | Path, document_title: Optional[str] = None) -> ParsedDocument:
        """
        Parses a PDF file from disk into a structured ParsedDocument.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found at path: {file_path}")

        try:
            doc = fitz.open(str(path))
        except Exception as e:
            raise CorruptedPDFError(f"Failed to open PDF file: {str(e)}")

        title = document_title or path.stem.replace("_", " ")
        return self._extract_structure(doc, default_title=title)

    def parse_bytes(self, pdf_bytes: bytes, document_title: Optional[str] = None) -> ParsedDocument:
        """
        Parses a PDF from in-memory bytes into a structured ParsedDocument.
        """
        if not pdf_bytes:
            raise EmptyDocumentError("Cannot parse empty (0 bytes) PDF payload.")

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise CorruptedPDFError(f"Failed to open PDF from memory bytes: {str(e)}")

        title = document_title or "Untitled Document"
        return self._extract_structure(doc, default_title=title)

    async def parse_and_update_document(
        self, document_id: uuid.UUID, db: AsyncSession
    ) -> ParsedDocument:
        """
        Parses a stored Document by ID and updates total_pages in PostgreSQL.
        """
        stmt = select(Document).where(Document.id == document_id)
        result = await db.execute(stmt)
        document = result.scalars().first()

        if not document:
            raise ValueError(f"Document with ID {document_id} not found in database.")

        parsed_doc = self.parse_file(document.file_path, document_title=document.title)

        # Update total_pages on database record
        document.total_pages = parsed_doc.total_pages
        await db.commit()
        await db.refresh(document)

        return parsed_doc

    def _extract_structure(self, doc: fitz.Document, default_title: str) -> ParsedDocument:
        """
        Internal engine performing font statistics, layout analysis, table extraction,
        and breadcrumb propagation.
        """
        try:
            if doc.is_encrypted:
                raise EncryptedPDFError("PDF is password-protected and cannot be parsed without credentials.")

            if doc.page_count == 0:
                raise EmptyDocumentError("PDF document has 0 pages.")

            # 1. Statistical Font Profiling across the entire document
            body_font_size = self._compute_body_font_mode(doc)

            parsed_pages: List[ParsedPage] = []
            all_elements: List[ParsedElement] = []

            # Stateful breadcrumb tracking stack across pages
            current_h1: Optional[str] = None
            current_h2: Optional[str] = None
            current_h3: Optional[str] = None

            for page_idx in range(doc.page_count):
                page = doc[page_idx]
                page_num = page_idx + 1  # 1-indexed
                page_width = page.rect.width
                page_height = page.rect.height

                page_elements: List[ParsedElement] = []

                # A. Extract Tables & record their bounding boxes
                tables_on_page, table_bboxes = self._extract_tables(page, page_num)

                # B. Extract & Order Text Blocks (excluding text inside table bboxes)
                text_blocks = self._extract_and_order_text_blocks(page, table_bboxes, page_width, page_height)

                # Merge text blocks and table objects into sequential reading order
                merged_items = self._merge_blocks_and_tables(text_blocks, tables_on_page)

                for item in merged_items:
                    if isinstance(item, ParsedElement) and item.element_type == ElementType.TABLE:
                        # Stamp current section path on table
                        item.section_path = self._build_section_path(
                            default_title, current_h1, current_h2, current_h3
                        )
                        page_elements.append(item)
                        all_elements.append(item)
                        continue

                    # Process text block dictionary
                    block_dict = item
                    element_type, content, bbox = self._classify_block(
                        block_dict, body_font_size, page_num
                    )

                    if not content or not content.strip():
                        continue

                    # Update hierarchical state machine when headings are encountered
                    if element_type == ElementType.HEADING_1:
                        current_h1 = content.strip()
                        current_h2 = None
                        current_h3 = None
                    elif element_type == ElementType.HEADING_2:
                        current_h2 = content.strip()
                        current_h3 = None
                    elif element_type == ElementType.HEADING_3:
                        current_h3 = content.strip()

                    section_path = self._build_section_path(
                        default_title, current_h1, current_h2, current_h3
                    )

                    element = ParsedElement(
                        element_type=element_type,
                        content=content.strip(),
                        page_number=page_num,
                        section_path=section_path,
                        bbox=bbox,
                        metadata={
                            "font_size": block_dict.get("max_font_size", body_font_size),
                            "is_bold": block_dict.get("is_bold", False),
                        },
                    )

                    page_elements.append(element)
                    all_elements.append(element)

                parsed_pages.append(
                    ParsedPage(
                        page_number=page_num,
                        width=page_width,
                        height=page_height,
                        elements=page_elements,
                        tables_count=len(tables_on_page),
                    )
                )

            return ParsedDocument(
                total_pages=doc.page_count,
                pages=parsed_pages,
                all_elements=all_elements,
                document_title=default_title,
            )

        finally:
            doc.close()

    def _compute_body_font_mode(self, doc: fitz.Document) -> float:
        """
        Samples text spans across the document to determine the statistical mode (most common)
        body text font size.
        """
        font_sizes: List[float] = []
        for page in doc:
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if len(text) > 3:  # Only count meaningful text spans
                                font_sizes.append(round(span.get("size", 10.0), 1))

        if not font_sizes:
            return 10.0  # Default fallback font size

        counter = Counter(font_sizes)
        mode_size, _ = counter.most_common(1)[0]
        return mode_size

    def _extract_tables(
        self, page: fitz.Page, page_num: int
    ) -> Tuple[List[ParsedElement], List[Tuple[float, float, float, float]]]:
        """
        Extracts tables from a page using PyMuPDF's find_tables() and converts them to Markdown tables.
        """
        table_elements: List[ParsedElement] = []
        table_bboxes: List[Tuple[float, float, float, float]] = []

        try:
            tabs = page.find_tables()
            for tab in tabs:
                extracted = tab.extract()
                if not extracted or len(extracted) < 1:
                    continue

                # Convert to Markdown Table format
                markdown_lines = []
                headers = [str(col or "").strip() for col in extracted[0]]
                markdown_lines.append("| " + " | ".join(headers) + " |")
                markdown_lines.append("| " + " | ".join([":---"] * len(headers)) + " |")

                for row in extracted[1:]:
                    cells = [str(cell or "").strip().replace("\n", " ") for cell in row]
                    markdown_lines.append("| " + " | ".join(cells) + " |")

                markdown_content = "\n".join(markdown_lines)
                bbox = tuple(tab.bbox)
                table_bboxes.append(bbox)

                table_elements.append(
                    ParsedElement(
                        element_type=ElementType.TABLE,
                        content=markdown_content,
                        page_number=page_num,
                        bbox=bbox,
                        metadata={"rows": len(extracted), "cols": len(headers)},
                    )
                )
        except Exception:
            # If table extraction fails on an irregular page, fall back gracefully
            pass

        return table_elements, table_bboxes

    def _is_inside_table(
        self, block_bbox: Tuple[float, float, float, float], table_bboxes: List[Tuple[float, float, float, float]]
    ) -> bool:
        """
        Checks if a text block's bounding box is enclosed inside any detected table bounding box.
        """
        bx0, by0, bx1, by1 = block_bbox
        for tx0, ty0, tx1, ty1 in table_bboxes:
            bc_x = (bx0 + bx1) / 2
            bc_y = (by0 + by1) / 2
            if tx0 - 2 <= bc_x <= tx1 + 2 and ty0 - 2 <= bc_y <= ty1 + 2:
                return True
        return False

    def _extract_and_order_text_blocks(
        self,
        page: fitz.Page,
        table_bboxes: List[Tuple[float, float, float, float]],
        page_width: float,
        page_height: float,
    ) -> List[Dict[str, Any]]:
        """
        Extracts text blocks, filters out table overlaps, and orders them with 2-column awareness.
        """
        page_dict = page.get_text("dict")
        raw_blocks = page_dict.get("blocks", [])
        text_blocks: List[Dict[str, Any]] = []

        for b in raw_blocks:
            if b.get("type") != 0:  # Skip image blocks
                continue

            bbox = tuple(b.get("bbox", (0, 0, 0, 0)))
            if self._is_inside_table(bbox, table_bboxes):
                continue

            # Extract block text, maximum font size, and bold flags
            block_text_lines = []
            max_font_size = 0.0
            is_bold = False

            for line in b.get("lines", []):
                line_spans = []
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    span_size = span.get("size", 10.0)
                    span_flags = span.get("flags", 0)
                    font_name = span.get("font", "").lower()

                    if span_size > max_font_size:
                        max_font_size = span_size

                    # Check bold via font flag (bit 1 is bold in PyMuPDF) or font name
                    if (span_flags & 2 != 0) or ("bold" in font_name) or ("black" in font_name) or ("heavy" in font_name):
                        is_bold = True

                    line_spans.append(span_text)

                line_str = "".join(line_spans).strip()
                if line_str:
                    block_text_lines.append(line_str)

            full_text = "\n".join(block_text_lines).strip()
            if full_text:
                text_blocks.append(
                    {
                        "text": full_text,
                        "bbox": bbox,
                        "max_font_size": max_font_size,
                        "is_bold": is_bold,
                    }
                )

        # 2-Column Layout Reading Order Heuristic
        mid_x = page_width / 2.0
        left_blocks = [b for b in text_blocks if b["bbox"][2] <= mid_x + 15]
        right_blocks = [b for b in text_blocks if b["bbox"][0] >= mid_x - 15]
        span_blocks = [b for b in text_blocks if b not in left_blocks and b not in right_blocks]

        is_two_column = len(left_blocks) >= 2 and len(right_blocks) >= 2

        if is_two_column:
            top_spans = sorted([b for b in span_blocks if b["bbox"][1] < page_height / 3], key=lambda x: x["bbox"][1])
            bottom_spans = sorted([b for b in span_blocks if b["bbox"][1] >= page_height / 3], key=lambda x: x["bbox"][1])
            sorted_left = sorted(left_blocks, key=lambda x: x["bbox"][1])
            sorted_right = sorted(right_blocks, key=lambda x: x["bbox"][1])
            return top_spans + sorted_left + sorted_right + bottom_spans

        # Standard 1-Column layout: sort top-to-bottom (y0), then left-to-right (x0)
        return sorted(text_blocks, key=lambda x: (x["bbox"][1], x["bbox"][0]))

    def _merge_blocks_and_tables(
        self, text_blocks: List[Dict[str, Any]], tables: List[ParsedElement]
    ) -> List[Any]:
        """
        Interleaves text blocks and tables in top-to-bottom vertical order.
        """
        all_items = []
        for tb in text_blocks:
            all_items.append((tb["bbox"][1], tb))
        for tab in tables:
            all_items.append((tab.bbox[1] if tab.bbox else 0, tab))

        all_items.sort(key=lambda x: x[0])
        return [item[1] for item in all_items]

    def _classify_block(
        self, block_dict: Dict[str, Any], body_font_size: float, page_num: int
    ) -> Tuple[ElementType, str, Tuple[float, float, float, float]]:
        """
        Applies document-adaptive relative font size thresholds, length safeguards,
        and punctuation checks to classify block into H1, H2, H3, or Paragraph.
        """
        text = block_dict["text"]
        max_font_size = block_dict.get("max_font_size", body_font_size)
        is_bold = block_dict.get("is_bold", False)
        bbox = block_dict.get("bbox", (0, 0, 0, 0))

        word_count = len(text.split())
        char_count = len(text)

        # Safeguard 1: Long text blocks are always paragraphs
        if char_count > 120 or word_count > 20:
            return ElementType.PARAGRAPH, text, bbox

        # Safeguard 2: Full sentences ending in period with > 8 words are paragraphs unless clause-numbered
        has_numbered_prefix = any(
            text.lstrip().startswith(p)
            for p in ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "1.1", "1.2", "Section", "Clause", "Article")
        )
        if text.endswith((".", ";")) and word_count > 8 and not has_numbered_prefix:
            return ElementType.PARAGRAPH, text, bbox

        # Safeguard 3: Bold text at standard body font size is just bold paragraph text
        if is_bold and max_font_size <= body_font_size * 1.08:
            return ElementType.PARAGRAPH, text, bbox

        # Relative font size classification against document body mode
        if max_font_size >= body_font_size * 1.50:
            if page_num == 1 and max_font_size >= body_font_size * 1.80 and char_count <= 80:
                return ElementType.TITLE, text, bbox
            return ElementType.HEADING_1, text, bbox

        if max_font_size >= body_font_size * 1.25:
            return ElementType.HEADING_2, text, bbox

        if max_font_size >= body_font_size * 1.15:
            if is_bold or has_numbered_prefix or (char_count <= 60 and not text.endswith(".")):
                return ElementType.HEADING_3, text, bbox

        # Bullet lists
        if text.startswith(("•", "-", "*", "–")) or (len(text) > 2 and text[0].isdigit() and text[1] == "."):
            if word_count > 2 and max_font_size <= body_font_size * 1.10:
                return ElementType.LIST_ITEM, text, bbox

        return ElementType.PARAGRAPH, text, bbox

    def _build_section_path(
        self,
        doc_title: str,
        h1: Optional[str],
        h2: Optional[str],
        h3: Optional[str],
    ) -> str:
        """
        Constructs a breadcrumb path: 'Document Title > H1 > H2 > H3'
        """
        parts = [doc_title]
        if h1:
            parts.append(h1)
        if h2:
            parts.append(h2)
        if h3:
            parts.append(h3)
        return " > ".join(parts)


# Global parser service instance
parser_service = PDFParserService()
