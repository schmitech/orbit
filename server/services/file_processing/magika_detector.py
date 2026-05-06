"""
Magika-backed upload inspection helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


GENERIC_TEXT_LABEL = "txt"
GENERIC_BINARY_LABEL = "unknown"


class FileValidationError(ValueError):
    """Raised when an uploaded file fails validation."""

    def __init__(self, message: str, status_code: int = 415):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class MagikaDetection:
    """Normalized Magika detection details."""

    label: str
    mime_type: str
    score: float
    is_text: bool
    group: str
    description: str
    is_generic_text: bool
    is_generic_binary: bool

    @property
    def is_generic(self) -> bool:
        return self.is_generic_text or self.is_generic_binary


class MagikaDetector:
    """Thin wrapper around the optional Magika dependency."""

    def __init__(
        self,
        *,
        enabled: bool,
        prediction_mode: str = "HIGH_CONFIDENCE",
        log_detection_details: bool = True,
    ) -> None:
        self.enabled = enabled
        self.log_detection_details = log_detection_details
        self._detector = None

        if not enabled:
            return

        from magika import Magika, PredictionMode

        try:
            selected_mode = getattr(PredictionMode, prediction_mode.upper())
        except AttributeError as exc:
            raise ValueError(f"Unsupported Magika prediction mode: {prediction_mode}") from exc

        self._detector = Magika(prediction_mode=selected_mode)

    def identify_bytes(self, file_data: bytes) -> Optional[MagikaDetection]:
        """Return normalized detection data for the provided bytes."""
        if not self.enabled or self._detector is None:
            return None

        result = self._detector.identify_bytes(file_data)
        if not result.ok:
            message = getattr(getattr(result, "status", None), "message", "unknown Magika error")
            raise ValueError(f"Magika failed to inspect upload: {message}")

        output = result.output
        return MagikaDetection(
            label=getattr(output, "label", "") or "",
            mime_type=getattr(output, "mime_type", "") or "",
            score=float(getattr(result, "score", 0.0) or 0.0),
            is_text=bool(getattr(output, "is_text", False)),
            group=getattr(output, "group", "") or "",
            description=getattr(output, "description", "") or "",
            is_generic_text=(getattr(output, "label", "") or "") == GENERIC_TEXT_LABEL,
            is_generic_binary=(getattr(output, "label", "") or "") == GENERIC_BINARY_LABEL,
        )


LABEL_TO_CANONICAL_TYPE: Dict[str, str] = {
    "aac": "audio/aac",
    "bmp": "image/bmp",
    "c": "text/x-csrc",
    "cpp": "text/x-c++src",
    "csv": "text/csv",
    "css": "text/css",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "flac": "audio/flac",
    "gif": "image/gif",
    "go": "text/x-go",
    "html": "text/html",
    "java": "text/x-java-source",
    "javascript": "application/javascript",
    "jpeg": "image/jpeg",
    "json": "application/json",
    "markdown": "text/markdown",
    "mp3": "audio/mpeg",
    "mp4": "audio/mp4",
    "ogg": "audio/ogg",
    "pdf": "application/pdf",
    "php": "text/x-php",
    "png": "image/png",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "py": "text/x-python",
    "python": "text/x-python",
    "rb": "text/x-ruby",
    "rs": "text/x-rust",
    "sass": "text/x-sass",
    "scss": "text/x-scss",
    "shell": "text/x-shellscript",
    "sql": "application/x-sql",
    "text": "text/plain",
    "tiff": "image/tiff",
    "toml": "text/plain",
    "tsv": "text/plain",
    "typescript": "text/typescript",
    "txt": "text/plain",
    "vtt": "text/vtt",
    "wav": "audio/wav",
    "webm": "audio/webm",
    "webp": "image/webp",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xml": "application/xml",
    "yaml": "text/yaml",
    "yml": "text/yaml",
}


MIME_TO_CANONICAL_TYPE: Dict[str, str] = {
    "application/javascript": "application/javascript",
    "application/json": "application/json",
    "application/pdf": "application/pdf",
    "application/sql": "application/x-sql",
    "application/typescript": "text/typescript",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/x-sql": "application/x-sql",
    "application/xml": "application/xml",
    "audio/aac": "audio/aac",
    "audio/flac": "audio/flac",
    "audio/mp3": "audio/mpeg",
    "audio/mp4": "audio/mp4",
    "audio/mpeg": "audio/mpeg",
    "audio/ogg": "audio/ogg",
    "audio/wav": "audio/wav",
    "audio/webm": "audio/webm",
    "audio/x-m4a": "audio/x-m4a",
    "image/bmp": "image/bmp",
    "image/gif": "image/gif",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/png": "image/png",
    "image/tiff": "image/tiff",
    "image/webp": "image/webp",
    "text/css": "text/css",
    "text/csv": "text/csv",
    "text/html": "text/html",
    "text/javascript": "application/javascript",
    "text/markdown": "text/markdown",
    "text/plain": "text/plain",
    "text/typescript": "text/typescript",
    "text/vtt": "text/vtt",
    "text/x-c": "text/x-csrc",
    "text/x-c++src": "text/x-c++src",
    "text/x-csrc": "text/x-csrc",
    "text/x-go": "text/x-go",
    "text/x-java": "text/x-java-source",
    "text/x-java-source": "text/x-java-source",
    "text/x-less": "text/x-less",
    "text/x-php": "text/x-php",
    "text/x-python": "text/x-python",
    "text/x-python-script": "text/x-python",
    "text/x-ruby": "text/x-ruby",
    "text/x-rust": "text/x-rust",
    "text/x-sass": "text/x-sass",
    "text/x-scss": "text/x-scss",
    "text/x-sh": "text/x-shellscript",
    "text/x-shellscript": "text/x-shellscript",
    "text/x-yaml": "text/yaml",
    "text/xml": "application/xml",
    "text/yaml": "text/yaml",
}


def canonicalize_mime_type(mime_type: Optional[str]) -> Optional[str]:
    """Collapse known MIME aliases into the canonical type used by Orbit."""
    if not mime_type:
        return None
    return MIME_TO_CANONICAL_TYPE.get(mime_type.lower())


def canonicalize_label(label: Optional[str]) -> Optional[str]:
    """Map a Magika label to Orbit's canonical MIME type."""
    if not label:
        return None
    return LABEL_TO_CANONICAL_TYPE.get(label.lower())
