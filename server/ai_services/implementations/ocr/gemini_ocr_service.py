"""
Gemini OCR service — native document processing endpoint.

Uses Gemini's multimodal document understanding (``client.models.generate_content``
with an inline ``Part.from_bytes``), which ingests a PDF or image directly and
returns extracted text in a single call. No page rasterization is required,
mirroring Mistral's native OCR endpoint.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from ...base import ServiceType
from ...providers import GoogleBaseService
from ...services import OcrService

logger = logging.getLogger(__name__)

_DEFAULT_OCR_PROMPT = (
    "Extract all text from this document as markdown, preserving structure "
    "(headings, lists, tables). Return only the extracted text, with no "
    "commentary."
)


class GeminiOcrService(OcrService, GoogleBaseService):
    """Gemini native document OCR service (single call, no rasterization)."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Gemini OCR service."""
        GoogleBaseService.__init__(self, config, ServiceType.OCR, "gemini")
        # Default to a fast Gemini model rather than the vision-service default.
        self.model = self._get_model("gemini-3.6-flash")
        self.prompt = (config.get("ai_document", {}) or {}).get("prompt") or _DEFAULT_OCR_PROMPT
        self._genai_client = None

    def _get_client(self):
        """Get or create the Google GenAI client."""
        if self._genai_client is None:
            from google import genai
            import os

            api_key = self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                os.environ["GOOGLE_API_KEY"] = api_key

            self._genai_client = genai.Client()
        return self._genai_client

    async def extract_document(
        self,
        file_data: bytes,
        mime_type: str,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract markdown from a PDF or image via a single Gemini call."""
        if not self.initialized:
            await self.initialize()

        try:
            from google.genai import types

            client = self._get_client()
            document_part = types.Part.from_bytes(data=file_data, mime_type=mime_type)

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.model,
                contents=[document_part, self.prompt],
            )

            if not response.candidates or not response.candidates[0].content:
                raise ValueError("No content returned from Gemini")

            text = response.candidates[0].content.parts[0].text or ""
        except Exception as e:
            self._handle_google_error(e, "document OCR")
            raise

        return {"text": text, "page_count": self._count_pages(file_data, mime_type)}

    def _count_pages(self, file_data: bytes, mime_type: str) -> int:
        """Count pages/frames locally (Gemini processes the whole document, uncapped)."""
        if mime_type.startswith("image/"):
            try:
                from io import BytesIO
                from PIL import Image
                return getattr(Image.open(BytesIO(file_data)), "n_frames", 1)
            except Exception:
                return 1
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(file_data)
            try:
                return len(pdf)
            finally:
                pdf.close()
        except Exception as e:
            logger.debug(f"Could not count PDF pages: {e}")
            return 0
