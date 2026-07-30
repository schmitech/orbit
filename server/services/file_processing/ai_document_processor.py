"""
AI Document Processor

Third universal document processor (peer to Docling and MarkItDown) that
offloads OCR to an LLM inference service. Handles PDFs and images by
delegating to an OcrService (Mistral native OCR, or any vision provider via
page rasterization).

Configured under files.processing.ai_document; the OCR provider/model are
resolved from config/ocr.yaml.
"""

import logging
import mimetypes
from typing import Dict, Any, Optional

from .base_processor import FileProcessor

logger = logging.getLogger(__name__)


class AIDocumentProcessor(FileProcessor):
    """Universal processor that extracts text via an AI/LLM OCR service."""

    def __init__(self, enabled: bool = True, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the AI document processor.

        Args:
            enabled: Whether AI document processing is enabled.
            config: Full application config (used to resolve OCR provider settings).
        """
        super().__init__()
        self._enabled = enabled
        self.config = config or {}

        ai_cfg = (
            self.config.get('files', {})
            .get('processing', {})
            .get('ai_document', {})
        ) or {}
        self.provider = ai_cfg.get('provider', 'mistral')
        self.model_override = ai_cfg.get('model')
        self.max_pages = ai_cfg.get('max_pages', 50)
        # Usage from the most recent extract_text() call — {"reported": bool,
        # "prompt_tokens"/"completion_tokens" (token-billed OCR, e.g. Gemini)
        # OR "usage_unit"/"usage_quantity" (unit-billed, e.g. Mistral pages)}.
        # FileProcessor.extract_text() only returns a bare str, so callers that
        # want usage (_extract_content) read this instance attribute right
        # after calling it, rather than widening that shared return contract.
        self.last_usage: Optional[Dict[str, Any]] = None
        # The OCR service's actually-resolved model (may differ from
        # model_override, which is usually unset) — set by extract_text(),
        # read by _extract_content() for pricing.
        self.last_model: Optional[str] = None

    def supports_mime_type(self, mime_type: str) -> bool:
        """Supports PDFs and images."""
        if not self._enabled:
            return False
        mime_type = (mime_type or '').lower()
        return mime_type == 'application/pdf' or mime_type.startswith('image/')

    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """Extract markdown text via the configured OCR service."""
        if not self._enabled:
            raise ValueError("AI document processor is disabled")

        self.last_usage = None
        mime_type = self._detect_mime_type(file_data, filename)
        service = self._get_ocr_service()
        if not service.initialized:
            await service.initialize()
        # self.model_override is only set when the operator explicitly
        # overrides it in config — the OCR service itself always resolves a
        # concrete model (from ocr.yaml's default, e.g. "mistral-ocr-latest"
        # or "gemini-3.6-flash"), so pricing must match against that resolved
        # model, not the (usually unset) override.
        self.last_model = getattr(service, "model", None) or self.model_override

        # usage_sink is only passed to services that opted into
        # UsageReportingMixin (currently Gemini OCR) — un-migrated services
        # splat **kwargs straight through, so an unrecognized kwarg would
        # break the request.
        if getattr(service, "SUPPORTS_USAGE_REPORTING", False):
            usage_sink: Dict[str, Any] = {}
            result = await service.extract_document(file_data, mime_type, filename, usage_sink=usage_sink)
            if usage_sink.get("reported"):
                self.last_usage = usage_sink
        else:
            result = await service.extract_document(file_data, mime_type, filename)

        if self.last_usage is None:
            media_usage = result.get("media_usage")
            if media_usage:
                self.last_usage = {
                    "reported": True,
                    "usage_unit": media_usage.get("unit"),
                    "usage_quantity": media_usage.get("quantity"),
                }

        return result.get('text', '')

    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Metadata for AI-OCR extraction (page count computed locally, no extra API call)."""
        metadata = await super().extract_metadata(file_data, filename)
        mime_type = self._detect_mime_type(file_data, filename)
        metadata['processed_by'] = 'ai_ocr'
        metadata['extraction_method'] = 'ai_ocr'
        metadata['ocr_provider'] = self.provider
        metadata['page_count'] = self._count_pages(file_data, mime_type)
        return metadata

    def _get_ocr_service(self):
        """Create (or fetch the cached) OCR service for the configured provider."""
        from ai_services import AIServiceFactory, ServiceType

        ocr_cfg = dict(self.config.get('ocr', {}))
        if self.model_override:
            provider_cfg = dict(ocr_cfg.get(self.provider, {}))
            provider_cfg['model'] = self.model_override
            ocr_cfg[self.provider] = provider_cfg

        service_config = {
            'ocr': ocr_cfg,
            'visions': self.config.get('visions', {}),
            'ai_document': self.config.get('files', {}).get('processing', {}).get('ai_document', {}),
        }
        return AIServiceFactory.create_service(ServiceType.OCR, self.provider, service_config)

    def _detect_mime_type(self, file_data: bytes, filename: Optional[str]) -> str:
        """Detect MIME type from magic bytes, falling back to the filename extension."""
        if file_data[:4] == b'%PDF':
            return 'application/pdf'
        if file_data[:2] == b'\xff\xd8':
            return 'image/jpeg'
        if file_data[:8] == b'\x89PNG\r\n\x1a\n':
            return 'image/png'
        if file_data[:6] in (b'GIF87a', b'GIF89a'):
            return 'image/gif'
        if len(file_data) > 12 and file_data[:4] == b'RIFF' and file_data[8:12] == b'WEBP':
            return 'image/webp'
        if filename:
            guessed, _ = mimetypes.guess_type(filename)
            if guessed:
                return guessed
        return 'application/pdf'

    def _count_pages(self, file_data: bytes, mime_type: str) -> int:
        """Count the pages/frames that are actually OCR'd (computed locally, no API call).

        Vision-backed providers cap work at max_pages; native OCR providers
        (Mistral, Gemini) process the whole document, so their count is not capped.
        """
        if mime_type.startswith('image/'):
            try:
                from io import BytesIO
                from PIL import Image
                source_count = getattr(Image.open(BytesIO(file_data)), 'n_frames', 1)
            except Exception:
                return 1
        else:
            try:
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(file_data)
                try:
                    source_count = len(pdf)
                finally:
                    pdf.close()
            except Exception as e:
                logger.debug(f"Could not count PDF pages: {e}")
                return 0

        if self.provider in ('mistral', 'gemini'):
            return source_count
        return min(source_count, self.max_pages)
