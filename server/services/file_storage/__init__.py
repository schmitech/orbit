"""
File Storage Service

Provides pluggable storage backends for file uploads and management.
Supports local filesystem (default), AWS S3 / S3-compatible stores (MinIO),
Azure Blob Storage, and Google Cloud Storage. Backend selection is config-driven
via ``create_storage_backend``.

Cloud backend classes lazy-import their SDKs, so importing this package does not
require boto3, azure-storage-blob, or google-cloud-storage unless a cloud backend
is instantiated.
"""

from .base_storage import FileStorageBackend
from .filesystem_storage import FilesystemStorage
from .s3_storage import S3Storage
from .azure_blob_storage import AzureBlobStorage
from .gcs_storage import GcsStorage
from .factory import create_storage_backend

__all__ = [
    'FileStorageBackend',
    'FilesystemStorage',
    'S3Storage',
    'AzureBlobStorage',
    'GcsStorage',
    'create_storage_backend',
]
