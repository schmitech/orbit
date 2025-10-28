"""
File Metadata Store

Provides SQLite-based metadata tracking for uploaded files and chunks.
"""

from .metadata_store import FileMetadataStore

__all__ = [
    'FileMetadataStore',
]
