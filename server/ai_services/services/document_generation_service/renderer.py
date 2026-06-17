from typing import Dict, Any, Optional

from .pdf import PDFRenderer
from .docx import DocxRenderer
from .xlsx import XlsxRenderer
from .pptx import PptxRenderer
from .md import MarkdownRenderer
from .csv import CSVRenderer

MIME_TYPES: Dict[str, str] = {
    "pdf":  "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "md":   "text/markdown",
    "csv":  "text/csv",
}

_RENDERERS = {
    "pdf":  PDFRenderer,
    "docx": DocxRenderer,
    "xlsx": XlsxRenderer,
    "pptx": PptxRenderer,
    "md":   MarkdownRenderer,
    "csv":  CSVRenderer,
}


class DocumentRenderer:
    """Dispatch a document spec to the appropriate format renderer.

    Pass the ``document_renderer`` section of ``document.yaml`` as ``config``
    to override colours, fonts, margins, and other layout defaults.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._cfg: Dict[str, Any] = config or {}

    def render(self, spec: Dict[str, Any], fmt: str) -> bytes:
        fmt = fmt.lower()
        renderer_cls = _RENDERERS.get(fmt)
        if renderer_cls is None:
            raise ValueError(
                f"Unsupported document format: {fmt!r}. "
                f"Supported: {', '.join(_RENDERERS)}"
            )
        return renderer_cls(self._cfg).render(spec)
