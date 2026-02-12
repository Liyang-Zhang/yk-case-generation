from typing import List, Optional, Literal
from pydantic import BaseModel, Field

SourceType = Literal["lims_text", "pdf", "png", "jpg", "docx", "ocr_attachment", "unknown"]

class Line(BaseModel):
    line_id: int
    text: str
    confidence: Optional[float] = None
    polygon: Optional[list] = None  # list of [x, y] points
    bbox: Optional[list] = None     # [x, y, w, h]
    parag_no: Optional[int] = None
    flags: dict = Field(default_factory=dict)

class Page(BaseModel):
    page_number: Optional[int]
    lines: List[Line]

class Source(BaseModel):
    source_id: str
    source_type: SourceType
    error: Optional[str] = None
    pages: List[Page] = Field(default_factory=list)

class DocumentIR(BaseModel):
    case_id: str
    sources: List[Source]
