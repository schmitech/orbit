"""
Storage Backend Factory

Selects and constructs a FileStorageBackend based on configuration. The backend
is chosen by the ``storage_backend`` config value (default: filesystem), so
existing filesystem deployments are unaffected.
"""

import logging
from typing import Dict, Any

from .base_storage import FileStorageBackend
from .filesystem_storage import FilesystemStorage

logger = logging.getLogger(__name__)


def create_storage_backend(config: Dict[str, Any]) -> FileStorageBackend:
    """
    Construct a storage backend from the merged config.

    Selection precedence for the backend type:
        config['files']['storage_backend']  (global)
        -> config['storage_backend']  (legacy adapter-level fallback)
        -> 'filesystem'  (default)

    Backend-specific settings are read from the matching sub-block under
    ``files`` (files.s3 / files.azure / files.gcs). Empty-string values (from
    unset ``${VAR:-}`` env defaults) are treated as None.

    Args:
        config: Merged configuration dictionary.

    Returns:
        A FileStorageBackend instance.

    Raises:
        ValueError: If storage_backend is not a recognized value.
    """
    files = config.get('files', {})
    backend = (files.get('storage_backend')
               or config.get('storage_backend')
               or 'filesystem').lower()

    if backend == 'filesystem':
        storage_root = config.get('storage_root') or files.get('storage_root', './uploads')
        return FilesystemStorage(storage_root=storage_root)

    if backend in ('s3', 'minio'):
        from .s3_storage import S3Storage
        s3 = files.get('s3', {})
        return S3Storage(
            bucket=s3['bucket'],
            prefix=s3.get('prefix', ''),
            endpoint_url=s3.get('endpoint_url') or None,
            region_name=s3.get('region') or None,
            aws_access_key_id=s3.get('access_key_id') or None,
            aws_secret_access_key=s3.get('secret_access_key') or None,
            path_style=(backend == 'minio' or bool(s3.get('endpoint_url'))),
        )

    if backend == 'azure':
        from .azure_blob_storage import AzureBlobStorage
        az = files.get('azure', {})
        return AzureBlobStorage(
            container=az['container'],
            prefix=az.get('prefix', ''),
            connection_string=az.get('connection_string') or None,
            account_url=az.get('account_url') or None,
            account_key=az.get('account_key') or None,
        )

    if backend == 'gcs':
        from .gcs_storage import GcsStorage
        gcs = files.get('gcs', {})
        return GcsStorage(
            bucket=gcs['bucket'],
            prefix=gcs.get('prefix', ''),
            project=gcs.get('project') or None,
            credentials_path=gcs.get('credentials_path') or None,
        )

    raise ValueError(
        f"Unknown storage_backend '{backend}'. Valid options: filesystem, s3, minio, azure, gcs."
    )
