"""
VTT Processor

Handles WebVTT subtitle files using webvtt-py.
"""

import logging
from typing import Dict, Any
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)

try:
    import webvtt
    from io import StringIO
    VTT_AVAILABLE = True
except ImportError:
    VTT_AVAILABLE = False
    logger.warning("webvtt-py not available. VTT processing disabled.")


class VTTProcessor(FileProcessor):
    """
    Processor for WebVTT subtitle files.

    Supports: text/vtt
    Requires: webvtt-py
    """

    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        vtt_types = [
            'text/vtt',
            'text/x-vtt',
        ]
        return VTT_AVAILABLE and mime_type.lower() in vtt_types

    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """Extract text from VTT file."""
        if not VTT_AVAILABLE:
            raise ImportError("webvtt-py not available")

        logger.debug(f"VTTProcessor.extract_text() called for file: {filename or 'unknown'} (using webvtt-py)")

        text_parts = []

        try:
            # Decode file data
            try:
                vtt_content = file_data.decode('utf-8')
            except UnicodeDecodeError:
                vtt_content = file_data.decode('latin-1')

            # Parse VTT content
            captions = webvtt.read_buffer(StringIO(vtt_content))

            for caption in captions:
                # Include timestamp for context
                timestamp = f"[{caption.start} --> {caption.end}]"
                text = caption.text.strip()

                if text:
                    text_parts.append(f"{timestamp} {text}")

            # Also create a clean transcript without timestamps
            if text_parts:
                text_parts.append("")
                text_parts.append("--- Full Transcript ---")
                for caption in captions:
                    if caption.text.strip():
                        text_parts.append(caption.text.strip())

            return "\n".join(text_parts)

        except Exception as e:
            logger.error(f"Error processing VTT: {e}")
            raise

    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from VTT file."""
        metadata = await super().extract_metadata(file_data, filename)

        if not VTT_AVAILABLE:
            return metadata

        try:
            # Decode file data
            try:
                vtt_content = file_data.decode('utf-8')
            except UnicodeDecodeError:
                vtt_content = file_data.decode('latin-1')

            # Parse VTT content
            captions = webvtt.read_buffer(StringIO(vtt_content))
            caption_list = list(captions)

            # Calculate total duration
            total_duration = None
            if caption_list:
                # Get the end time of the last caption
                last_caption = caption_list[-1]
                total_duration = last_caption.end

            # Count words in all captions
            total_words = sum(len(c.text.split()) for c in caption_list)

            metadata.update({
                'caption_count': len(caption_list),
                'total_duration': total_duration,
                'total_words': total_words,
                'mime_type': 'text/vtt',
            })

        except Exception as e:
            logger.warning(f"Error extracting VTT metadata: {e}")

        return metadata
