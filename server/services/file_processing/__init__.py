"""
File Processing Service

Provides processors for extracting text and metadata from various file formats.
Supports PDF, DOCX, CSV, TXT, MD, HTML, JSON, etc.
"""

from .base_processor import FileProcessor
from .chunking import Chunk, FixedSizeChunker, SemanticChunker, TextChunker
from .file_processing_service import FileProcessingService
from .processor_registry import FileProcessorRegistry

__all__ = [
    'Chunk',
    'FileProcessingService',
    'FileProcessor',
    'FileProcessorRegistry',
    'FixedSizeChunker',
    'SemanticChunker',
    'TextChunker',
]