"""
Clause & Section Hierarchy Extraction Service.
Extracts cohesive clauses from Markdown prose, tables, and document chunks while preserving
section breadcrumb paths, page tags, and structural integrity.
"""
import re
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

# Pattern to strip leading numbering from headings e.g. "1.2 Authentication" or "Section 4.1.2: Data Retention" -> "Data Retention"
HEADING_NUMBERING_PATTERN = re.compile(
    r"^\s*(?:(?:Section|Chapter|Article|Clause|Part|Policy)\s+)?(?:\d+(?:\.\d+)*|[A-Z]\b|\([a-z0-9]+\))\s*[\.:\-–]?\s*",
    re.IGNORECASE,
)

# Context breadcrumb pattern e.g. "[Context: DocTitle > Section 1 > Subsection]"
CONTEXT_BREADCRUMB_PATTERN = re.compile(r"^\[Context:\s*(.*?)\]$", re.IGNORECASE)

# Plain-text section heading pattern e.g. "Section 1: Access Control", "1. Information Security Principles"
PLAIN_HEADING_PATTERN = re.compile(
    r"^(?:(?:Section|Chapter|Article|Clause|Part|Policy)\s+\d+(?:\.\d+)*\s*[:\.\-–]?\s*.+|\d+(?:\.\d+)+\s+[A-Z].+|\d+\.\s+[A-Z][A-Za-z0-9\s&/\-_,\'\"]{2,80})$",
    re.IGNORECASE,
)

# Document-level administrative metadata pattern e.g. "Policy owner: ...", "Version 2.1", "Review cycle: ..."
METADATA_LINE_PATTERN = re.compile(
    r"(?:"
    r"^(?:Policy\s+Owner|Document\s+Owner|Author|Review\s+Cycle|Current\s+Version|Effective\s+Date|Status|Classification|Doc\s+ID|Document\s+ID)\s*[:\-–]|"
    r"\b(?:Version\s+\d+(?:\.\d+)*|Effective\s+\d{1,2}\s+[A-Za-z]+\s+\d{4})\b.*(?:Version|Effective|Status|Date)|"
    r"\b(?:Review\s+cycle|Current\s+version)\b.*(?:\d+|months|years)|"
    r"^(?:This\s+(?:fictional\s+)?policy\s+is\s+designed|This\s+document\s+is\s+intended|This\s+policy\s+applies\s+to\s+all\s+testing)\b"
    r")",
    re.IGNORECASE,
)

# Negation and polarity terms that MUST be preserved during comparison
POLARITY_TERMS = {
    "mandatory", "required", "prohibited", "forbidden", "optional", "discretionary",
    "must", "must not", "shall", "shall not", "may", "may not", "cannot", "not required",
    "allowed", "permitted", "restricted", "strictly", "exempt", "waiver"
}


class ExtractedClause(BaseModel):
    """Internal structural unit representing a distinct clause or table block in a document."""
    model_config = ConfigDict(frozen=True)

    clause_id: str = Field(description="Unique deterministic ID for clause within document")
    section_path: str = Field(default="General", description="Breadcrumb hierarchy e.g. 'Security > Auth'")
    raw_text: str = Field(description="Exact original unmodified text of the clause")
    normalized_text: str = Field(description="Normalized text for alignment comparisons")
    normalized_heading: str = Field(description="Normalized section path for structural matching")
    page_number: Optional[int] = Field(default=None, description="Page number if available")
    is_table: bool = Field(default=False, description="True if clause is a Markdown table")
    is_metadata: bool = Field(default=False, description="True if clause represents administrative/document metadata")
    clause_index: int = Field(default=0, ge=0, description="Sequential index in document")


class ClauseExtractorService:
    """
    Extracts structured, cohesive clauses from raw markdown, plain text, or document chunks.
    """

    @staticmethod
    def normalize_heading(heading: str) -> str:
        """
        Normalizes heading by stripping numbers (e.g. 'Section 4.1.2: Backup Retention Policy' -> 'backup retention policy')
        while preserving semantic tokens.
        """
        if not heading:
            return "general"
        parts = [p.strip() for p in heading.split(">")]
        clean_parts = []
        for part in parts:
            cleaned = HEADING_NUMBERING_PATTERN.sub("", part).strip().lower()
            cleaned = re.sub(r"\s+", " ", cleaned)
            if cleaned:
                clean_parts.append(cleaned)
        return " > ".join(clean_parts) if clean_parts else "general"

    @staticmethod
    def normalize_text_for_comparison(text: str) -> str:
        """
        Normalizes clause text for comparison:
        - Collapses whitespace
        - Lowercases
        - Preserves numbers, versions, identifiers, currency, and polarity terms
        """
        if not text:
            return ""
        norm = text.strip().lower()
        norm = re.sub(r"\s+", " ", norm)
        # Remove markdown bold/italic markers for clean text comparison
        norm = re.sub(r"[\*_]{1,3}", "", norm)
        return norm

    @staticmethod
    def is_document_metadata(text: str) -> bool:
        """Detects if a line or block represents document-level administrative metadata rather than a policy clause."""
        if not text:
            return False
        return bool(METADATA_LINE_PATTERN.search(text))

    @staticmethod
    def _is_plain_heading(line: str) -> bool:
        """
        Detects if a plain text line represents a section heading rather than a body clause sentence.
        """
        if not line or len(line) > 100:
            return False
        # Full sentences ending in period with > 6 words are body clauses, not headings
        words = line.split()
        if line.endswith(".") and len(words) > 6:
            return False
        return bool(PLAIN_HEADING_PATTERN.match(line))

    @staticmethod
    def _is_title_candidate(line: str, heading_stack: List[str], saw_section_heading: bool) -> bool:
        """Detects standalone document title before section headings."""
        if saw_section_heading:
            return False
        if not line or len(line) > 80:
            return False
        if line.endswith(".") or line.endswith(":") or line.endswith(";"):
            return False
        words = line.split()
        if len(words) > 8:
            return False
        # If it has policy modality verbs, it's a clause, not a title
        lower = line.lower()
        if any(v in lower for v in [" must ", " shall ", " cannot ", " is required ", " are required "]):
            return False
        return True

    def extract_from_markdown(
        self,
        text: str,
        doc_prefix: str = "doc",
        default_page: Optional[int] = None,
    ) -> List[ExtractedClause]:
        """
        Parses Markdown text into structured clauses preserving heading tree context.
        """
        if not text or not text.strip():
            return []

        clauses: List[ExtractedClause] = []
        lines = text.splitlines()

        current_heading_stack: List[str] = []
        current_block_lines: List[str] = []
        in_table = False
        table_lines: List[str] = []
        clause_counter = 0
        saw_section_heading = False

        def get_current_section_path() -> str:
            return " > ".join(current_heading_stack) if current_heading_stack else "General"

        def flush_current_block():
            nonlocal clause_counter, current_block_lines
            if not current_block_lines:
                return
            block_text = "\n".join(current_block_lines).strip()
            if block_text:
                clause_counter += 1
                sec_path = get_current_section_path()
                is_meta = self.is_document_metadata(block_text)
                clauses.append(
                    ExtractedClause(
                        clause_id=f"{doc_prefix}_clause_{clause_counter}",
                        section_path=sec_path,
                        raw_text=block_text,
                        normalized_text=self.normalize_text_for_comparison(block_text),
                        normalized_heading=self.normalize_heading(sec_path),
                        page_number=default_page,
                        is_table=False,
                        is_metadata=is_meta,
                        clause_index=clause_counter,
                    )
                )
            current_block_lines = []

        def flush_table():
            nonlocal clause_counter, table_lines, in_table
            if not table_lines:
                in_table = False
                return
            table_text = "\n".join(table_lines).strip()
            if table_text:
                clause_counter += 1
                sec_path = get_current_section_path()
                clauses.append(
                    ExtractedClause(
                        clause_id=f"{doc_prefix}_clause_{clause_counter}",
                        section_path=sec_path,
                        raw_text=table_text,
                        normalized_text=self.normalize_text_for_comparison(table_text),
                        normalized_heading=self.normalize_heading(sec_path),
                        page_number=default_page,
                        is_table=True,
                        is_metadata=False,
                        clause_index=clause_counter,
                    )
                )
            table_lines = []
            in_table = False

        for line in lines:
            stripped = line.strip()

            # 1. Context Breadcrumb Detection (e.g. [Context: DocTitle > Section 1 > Subsection])
            context_match = CONTEXT_BREADCRUMB_PATTERN.match(stripped)
            if context_match:
                if in_table:
                    flush_table()
                else:
                    flush_current_block()

                raw_breadcrumb = context_match.group(1).strip()
                if raw_breadcrumb:
                    parts = [p.strip() for p in raw_breadcrumb.split(">") if p.strip()]
                    current_heading_stack = parts
                    if len(parts) > 1:
                        saw_section_heading = True
                continue

            # 2. Markdown Heading Detection (# Heading, ## Subheading, ### Sub-subheading)
            heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if heading_match:
                if in_table:
                    flush_table()
                else:
                    flush_current_block()

                saw_section_heading = True
                level = len(heading_match.group(1))
                heading_title = heading_match.group(2).strip()

                # Adjust heading stack to current level
                if level <= len(current_heading_stack):
                    current_heading_stack = current_heading_stack[: level - 1]
                current_heading_stack.append(heading_title)
                continue

            # 3. Plain-text Section Heading Detection (e.g. "Section 1: Access Control", "3. Authentication & Password Rules")
            if self._is_plain_heading(stripped):
                if in_table:
                    flush_table()
                else:
                    flush_current_block()

                saw_section_heading = True
                if len(current_heading_stack) > 1:
                    current_heading_stack = current_heading_stack[:1] + [stripped]
                else:
                    current_heading_stack = [stripped]
                continue

            # 4. Top-of-Document Title Candidate (e.g. "Enterprise Security Policy 2026")
            if not saw_section_heading and self._is_title_candidate(stripped, current_heading_stack, saw_section_heading):
                if in_table:
                    flush_table()
                else:
                    flush_current_block()
                current_heading_stack = [stripped]
                continue

            # 5. Table Row Detection (| Col 1 | Col 2 |)
            if stripped.startswith("|") and stripped.endswith("|"):
                if not in_table:
                    flush_current_block()
                    in_table = True
                table_lines.append(line)
                continue
            elif in_table:
                # Table ended
                flush_table()

            # 6. Blank line separates paragraphs/clauses
            if not stripped:
                flush_current_block()
                continue

            current_block_lines.append(line)

        # Flush any remaining content
        if in_table:
            flush_table()
        else:
            flush_current_block()

        return clauses


# Global singleton
clause_extractor = ClauseExtractorService()
