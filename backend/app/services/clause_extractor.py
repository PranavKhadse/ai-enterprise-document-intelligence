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
                clauses.append(
                    ExtractedClause(
                        clause_id=f"{doc_prefix}_clause_{clause_counter}",
                        section_path=sec_path,
                        raw_text=block_text,
                        normalized_text=self.normalize_text_for_comparison(block_text),
                        normalized_heading=self.normalize_heading(sec_path),
                        page_number=default_page,
                        is_table=False,
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
                        clause_index=clause_counter,
                    )
                )
            table_lines = []
            in_table = False

        for line in lines:
            stripped = line.strip()

            # Heading Detection (# Heading, ## Subheading, ### Sub-subheading)
            heading_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if heading_match:
                if in_table:
                    flush_table()
                else:
                    flush_current_block()

                level = len(heading_match.group(1))
                heading_title = heading_match.group(2).strip()

                # Adjust heading stack to current level
                if level <= len(current_heading_stack):
                    current_heading_stack = current_heading_stack[: level - 1]
                current_heading_stack.append(heading_title)
                continue

            # Table Row Detection (| Col 1 | Col 2 |)
            if stripped.startswith("|") and stripped.endswith("|"):
                if not in_table:
                    flush_current_block()
                    in_table = True
                table_lines.append(line)
                continue
            elif in_table:
                # Table ended
                flush_table()

            # Blank line separates paragraphs/clauses
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
