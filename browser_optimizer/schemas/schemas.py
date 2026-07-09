from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class UIElement(BaseModel):
    tag: str
    text: str
    id: Optional[str] = None
    name: Optional[str] = None
    placeholder: Optional[str] = None
    type: Optional[str] = None
    href: Optional[str] = None

class CompressedContext(BaseModel):
    ui: List[UIElement]
    ax_tree: Optional[Any] = None
    url: str
    title: str
    text_content: str
    raw_html_length: int
    compressed_length: int
    compression_ratio: float

class ClassificationResult(BaseModel):
    page_type: str
    scores: Dict[str, int]

class PageDiff(BaseModel):
    url: str
    added: List[UIElement] = Field(default_factory=list)
    removed: List[UIElement] = Field(default_factory=list)
    changed: List[Dict[str, Any]] = Field(default_factory=list)

class ActionRequest(BaseModel):
    action: str  # click, type, select, wait, scroll, navigate
    selector: Optional[str] = None
    value: Optional[str] = None

class ActionResult(BaseModel):
    success: bool
    message: str
    url: Optional[str] = None

class CacheEntry(BaseModel):
    url: str
    compressed_context: Dict[str, Any]
    timestamp: float
