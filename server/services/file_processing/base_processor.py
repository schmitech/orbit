"""
Base File Processor

Abstract base class for file format processors.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Unified result of a single processor extraction call."""

    text: str
    metadata: dict[str, Any]
    tables: list[dict[str, Any]] = field(default_factory=list)
    page_segments: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    provider: str | None = None
    model: str | None = None


class FileProcessor(ABC):
    """
    Abstract base class for file processors.
    
    Each processor handles a specific file format or set of formats.
    """
    
    def __init__(self):
        """Initialize processor."""
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def supports_mime_type(self, mime_type: str) -> bool:
        """
        Check if this processor supports a given MIME type.
        
        Args:
            mime_type: MIME type to check
            
        Returns:
            True if supported, False otherwise
        """
    
    async def extract_text(self, file_data: bytes, filename: str | None = None) -> str:
        """
        Extract plain text from file.

        Args:
            file_data: File contents as bytes
            filename: Optional filename for context

        Returns:
            Extracted text content
        """
        raise NotImplementedError

    def _base_metadata(self, file_data: bytes, filename: str | None = None) -> dict[str, Any]:
        """Base filename/file_size metadata shared by every processor."""
        return {
            'filename': filename,
            'file_size': len(file_data),
        }

    async def extract_metadata(self, file_data: bytes, filename: str | None = None) -> dict[str, Any]:
        """
        Extract metadata from file.

        Args:
            file_data: File contents as bytes
            filename: Optional filename for context

        Returns:
            Dictionary of metadata
        """
        return self._base_metadata(file_data, filename)

    async def extract(self, file_data: bytes, filename: str | None = None) -> ExtractionResult:
        """Default bridge: legacy extract_text/extract_metadata -> ExtractionResult.
        Processors override this directly once migrated; see migration order in
        docs/roadmap/complete/file-processing-unified-extraction-result.md."""
        text = await self.extract_text(file_data, filename)
        metadata = await self.extract_metadata(file_data, filename)
        return ExtractionResult(
            text=text,
            metadata=metadata,
            tables=getattr(self, "_last_tables", None) or [],
            page_segments=getattr(self, "_last_page_segments", None) or [],
            usage=getattr(self, "last_usage", None),
            provider=getattr(self, "provider", None),
            model=getattr(self, "last_model", None),
        )
