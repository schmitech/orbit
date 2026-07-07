"""
Mistral OCR service — native document OCR endpoint.

Uses Mistral's dedicated OCR API (``client.ocr``) which ingests a PDF or image
directly and returns per-page markdown. No page rasterization is required.
"""

import base64
from typing import Dict, Any, Optional

from ...base import ServiceType
from ...providers import MistralBaseService
from ...services import OcrService


class MistralOcrService(OcrService, MistralBaseService):
    """Mistral native OCR service (``client.ocr.process``)."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Mistral OCR service."""
        MistralBaseService.__init__(self, config, ServiceType.OCR, "mistral")
        # Default to Mistral's OCR model rather than the embedding default set
        # by MistralBaseService.
        self.model = self._get_model("mistral-ocr-latest")

    async def extract_document(
        self,
        file_data: bytes,
        mime_type: str,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract markdown from a PDF or image via Mistral's OCR endpoint."""
        if not self.initialized:
            await self.initialize()

        b64 = base64.b64encode(file_data).decode("utf-8")
        if mime_type.startswith("image/"):
            document = {
                "type": "image_url",
                "image_url": f"data:{mime_type};base64,{b64}",
            }
        else:
            document = {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{b64}",
            }
            if filename:
                document["document_name"] = filename

        try:
            response = await self.client.ocr.process_async(
                model=self.model,
                document=document,
            )
        except Exception as e:
            self._handle_mistral_error(e, "document OCR")
            raise

        pages = getattr(response, "pages", None) or []
        markdown = "\n\n---\n\n".join(
            (getattr(page, "markdown", "") or "") for page in pages
        )
        return {"text": markdown, "page_count": len(pages)}
