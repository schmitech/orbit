"""
File Storage Service

Provides pluggable storage backends for file uploads and management.
Supports local filesystem (current) and future S3-compatible backends (MinIO, AWS S3).
"""

from .base_storage import FileStorageBackend
from .filesystem_storage import FilesystemStorage

__all__ = [
    'FileStorageBackend',
    'FilesystemStorage',
]
