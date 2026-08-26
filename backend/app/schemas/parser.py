"""
Pydantic schemas for structured PDF parsing intermediate representation.
"""
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field


class ElementType(str, Enum):
    """
    Classification of extracted structural elements.
    """
    TITLE = "title"
    HEADING_1 = "heading_1"
    HEADING_2 = "heading_2"
    HEADING_3 = "heading_3"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST_ITEM = "list_item"


class ParsedElement(BaseModel):
    """
    An individual extracted structural unit (paragraph, heading, or table)
    with spatial coordinates, 1-indexed page number, and section breadcrumbs.
    """
    element_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique identifier for the parsed element"
    )
    element_type: ElementType = Field(
        ...,
        description="Classification: heading_1, heading_2, heading_3, paragraph, table, etc."
    )
    content: str = Field(
        ...,
        description="Extracted clean text content or formatted Markdown table"
    )
    page_number: int = Field(
        ...,
        description="1-indexed source page number"
    )
    section_path: Optional[str] = Field(
        default=None,
        description="Hierarchical section breadcrumb path (e.g. 'Doc > H1 > H2')"
    )
    bbox: Optional[Tuple[float, float, float, float]] = Field(
        default=None,
        description="Bounding box coordinates (x0, y0, x1, y1) in points"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional styling and structural metadata"
    )

    model_config = ConfigDict(from_attributes=True)


class ParsedPage(BaseModel):
    """
    Structured representation of an individual document page.
    """
    page_number: int = Field(..., description="1-indexed page number")
    width: float = Field(..., description="Page width in points")
    height: float = Field(..., description="Page height in points")
    elements: List[ParsedElement] = Field(
        default_factory=list,
        description="Ordered list of structural elements on this page"
    )
    tables_count: int = Field(
        default=0,
        description="Total number of tables extracted from this page"
    )

    model_config = ConfigDict(from_attributes=True)


class ParsedDocument(BaseModel):
    """
    Complete structured intermediate representation of an ingested document.
    """
    total_pages: int = Field(..., description="Total number of pages in document")
    pages: List[ParsedPage] = Field(
        default_factory=list,
        description="List of parsed pages"
    )
    all_elements: List[ParsedElement] = Field(
        default_factory=list,
        description="Flattened list of all parsed elements across the entire document"
    )
    document_title: Optional[str] = Field(
        default=None,
        description="Inferred or extracted document title"
    )

    model_config = ConfigDict(from_attributes=True)
