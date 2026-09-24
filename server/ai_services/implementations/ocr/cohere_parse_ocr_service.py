"""
Cohere Parse OCR service — native document parsing endpoint.

Uses Cohere's Parse API (``client.parse``), which accepts image input only
(no native PDF ingestion). PDFs are rasterized page-by-page and multi-frame
images are split into individual pages before being sent through Parse.
"""

import asyncio
import base64
from typing import Any, Optional

from ...base import ServiceType
from ...providers import CohereBaseService
from ...services import OcrService
from .vision_ocr_service import VisionBackedOcrService

_MAX_CONCURRENT_PAGES = 4


class CohereParseOcrService(OcrService, CohereBaseService):
    """Cohere native document parsing OCR service (``client.parse``)."""

    def __init__(self, config: dict[str, Any]):
        """Initialize the Cohere Parse OCR service."""
        CohereBaseService.__init__(self, config, ServiceType.OCR, "cohere_parse")
        # Default to Cohere's Parse model rather than the None default set
        # by CohereBaseService for unrecognized service types.
        self.model = self._get_model("parse-v5.0")

        # OCR tuning forwarded from files.processing.ai_document by the processor.
        ai_cfg = config.get("ai_document", {}) or {}
        self.max_pages = ai_cfg.get("max_pages", 50)
        self.dpi = ai_cfg.get("dpi", 150)

    async def extract_document(
        self,
        file_data: bytes,
        mime_type: str,
        filename: Optional[str] = None,
    ) -> dict[str, Any]:
        """Extract markdown from a PDF or image via Cohere's Parse endpoint."""
        if not self.initialized:
            await self.initialize()

        if mime_type.startswith("image/"):
            page_images = VisionBackedOcrService._split_image_frames(self, file_data)
            # A single frame is returned unchanged, so it keeps the source
            # MIME type; a split multi-frame image is re-encoded as PNG.
            page_mime_types = [mime_type] if len(page_images) == 1 else ["image/png"] * len(page_images)
        else:
            page_images = VisionBackedOcrService._rasterize_pdf(self, file_data)
            page_mime_types = ["image/png"] * len(page_images)

        if not page_images:
            return {"text": "", "page_count": 0}

        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_PAGES)

        async def _parse_bounded(image_bytes: bytes, image_mime_type: str) -> str:
            async with semaphore:
                return await self._parse_image(image_bytes, image_mime_type)

        page_texts = await asyncio.gather(
            *[_parse_bounded(img, mt) for img, mt in zip(page_images, page_mime_types)]
        )
        text = "\n\n---\n\n".join(page_texts)
        return {
            "text": text,
            "page_count": len(page_images),
            "media_usage": {"unit": "pages", "quantity": len(page_images)},
        }

    async def _parse_image(self, image_bytes: bytes, mime_type: str) -> str:
        from cohere.types.parse_document import ParseDocument

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        document = ParseDocument(type="image_url", image_url=f"data:{mime_type};base64,{b64}")

        try:
            response = await self.client.parse(
                model=self.model,
                document=document,
                output_format="markdown",
            )
        except Exception as e:
            self._handle_cohere_error(e, "document parse")
            raise

        pages = getattr(response, "pages", None) or []
        texts = []
        for page in pages:
            markdown = getattr(page, "markdown", None)
            texts.append(getattr(markdown, "content", "") or "" if markdown else "")
        return "\n\n---\n\n".join(texts)
