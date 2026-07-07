"""
OCR service interface and base implementation.

This module defines the common interface for AI/LLM-based OCR services that
turn a whole document (PDF or image) into markdown text. It complements the
per-image VisionService interface by operating at the document level, which
lets purpose-built endpoints (e.g. Mistral OCR) ingest a PDF directly while
vision-backed providers rasterize pages first.
"""

from abc import abstractmethod
from typing import Dict, Any, Optional

from ..base import ProviderAIService, ServiceType


class OcrService(ProviderAIService):
    """
    Base class for all document OCR services.

    Implementations extract markdown text from a full document (PDF or image),
    regardless of provider (Mistral native OCR, or any vision provider via
    page rasterization).
    """

    # Class attribute for service type
    service_type = ServiceType.OCR

    def __init__(self, config: Dict[str, Any], provider_name: str):
        """
        Initialize the OCR service.

        Args:
            config: Configuration dictionary
            provider_name: Provider name (e.g., 'mistral', 'openai')
        """
        super().__init__(config, ServiceType.OCR, provider_name)

    @abstractmethod
    async def extract_document(
        self,
        file_data: bytes,
        mime_type: str,
        filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract text from a document (PDF or image) as markdown.

        Args:
            file_data: Raw document bytes
            mime_type: MIME type of the document (e.g. 'application/pdf', 'image/png')
            filename: Optional filename for context

        Returns:
            Dictionary with at least:
                - 'text': extracted markdown text (str)
                - 'page_count': number of pages processed (int)
        """
        pass


# Helper function for service creation
def create_ocr_service(
    provider: str,
    config: Dict[str, Any]
) -> OcrService:
    """
    Factory function to create an OCR service.

    Args:
        provider: Provider name (e.g., 'mistral', 'openai')
        config: Configuration dictionary

    Returns:
        OCR service instance
    """
    from ..factory import AIServiceFactory

    return AIServiceFactory.create_service(
        ServiceType.OCR,
        provider,
        config
    )
