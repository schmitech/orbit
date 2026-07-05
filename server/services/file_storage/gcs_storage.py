"""
Google Cloud Storage Backend

Google Cloud Storage (GCS) implementation of FileStorageBackend. Stores files as
objects with a JSON metadata sidecar object, mirroring the filesystem backend's
layout so behaviour is identical across backends.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional

from .base_storage import FileStorageBackend

logger = logging.getLogger(__name__)

_METADATA_SUFFIX = ".metadata.json"


class GcsStorage(FileStorageBackend):
    """
    Google Cloud Storage backend.

    Object layout mirrors the filesystem backend (GCS treats '/' as a virtual
    folder separator):
        {prefix}{api_key}/{file_id}/{filename}                  # the file
        {prefix}{api_key}/{file_id}/{filename}.metadata.json    # metadata sidecar

    The synchronous google-cloud-storage SDK is used, with every network call
    dispatched to a worker thread via ``asyncio.to_thread``.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        project: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        """
        Initialize the GCS storage backend.

        Auth precedence:
            1. credentials_path (service-account JSON key file)
            2. Application Default Credentials (ADC) — GOOGLE_APPLICATION_CREDENTIALS,
               gcloud user creds, or Workload Identity / metadata server on GCP.

        Args:
            bucket: Name of an existing GCS bucket (not created implicitly).
            prefix: Optional object-name prefix applied to every object.
            project: Optional GCP project ID (inferred from credentials if omitted).
            credentials_path: Optional path to a service-account JSON key file.
        """
        try:
            from google.cloud import storage
        except ImportError as e:
            raise ImportError(
                "The GCS storage backend requires google-cloud-storage. Install it with "
                "'./install/setup.sh --profile cloud-services' or 'pip install google-cloud-storage'."
            ) from e

        self.prefix = self._normalize_prefix(prefix)

        if credentials_path:
            self._client = storage.Client.from_service_account_json(
                credentials_path, project=project or None
            )
        else:
            self._client = storage.Client(project=project or None)

        # Fail loudly if the bucket does not exist / is not accessible.
        try:
            self._bucket = self._client.get_bucket(bucket)
        except Exception as e:
            raise RuntimeError(
                f"GCS bucket '{bucket}' is not accessible: {e}. "
                "Create it (or fix credentials/permissions) before starting the server."
            ) from e

        logger.info(
            f"Initialized GcsStorage (bucket={bucket}, prefix='{self.prefix}')"
        )

    @staticmethod
    def _normalize_prefix(prefix: str) -> str:
        """Normalize prefix: no leading slash, single trailing slash (or empty)."""
        prefix = (prefix or "").strip().lstrip("/")
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        return prefix

    def _full_key(self, key: str) -> str:
        """Apply the configured prefix to a storage key."""
        return f"{self.prefix}{key}"

    @staticmethod
    def _normalize_list_prefix(prefix: str) -> str:
        """Normalize logical directory prefixes to avoid prefix collisions."""
        prefix = (prefix or "").lstrip("/")
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        return prefix

    def _metadata_key(self, key: str) -> str:
        """Get the sidecar object name for a storage key."""
        return self._full_key(key) + _METADATA_SUFFIX

    async def put_file(self, file_data: bytes, key: str, metadata: Dict[str, Any]) -> str:
        """Store a file object and its metadata sidecar (each upload is atomic)."""
        metadata_bytes = json.dumps(metadata).encode("utf-8")

        await asyncio.to_thread(
            self._bucket.blob(self._metadata_key(key)).upload_from_string,
            metadata_bytes,
            content_type="application/json",
        )
        await asyncio.to_thread(
            self._bucket.blob(self._full_key(key)).upload_from_string,
            file_data,
        )

        logger.debug(f"Stored object gs://{self._bucket.name}/{self._full_key(key)} ({len(file_data)} bytes)")
        return key

    async def get_file(self, key: str) -> bytes:
        """Retrieve file contents."""
        from google.api_core.exceptions import NotFound

        def _download() -> bytes:
            try:
                return self._bucket.blob(self._full_key(key)).download_as_bytes()
            except NotFound as e:
                raise FileNotFoundError(f"File not found: {key}") from e

        return await asyncio.to_thread(_download)

    async def delete_file(self, key: str) -> bool:
        """Delete the file object and its metadata sidecar."""
        from google.api_core.exceptions import NotFound

        deleted = await self.file_exists(key)

        def _delete(name: str) -> None:
            try:
                self._bucket.blob(name).delete()
            except NotFound:
                pass

        await asyncio.to_thread(_delete, self._full_key(key))
        await asyncio.to_thread(_delete, self._metadata_key(key))

        if deleted:
            logger.debug(f"Deleted object gs://{self._bucket.name}/{self._full_key(key)}")
        return deleted

    async def list_files(self, prefix: str) -> List[str]:
        """List file keys under a prefix (metadata sidecars excluded)."""
        search_prefix = self._full_key(self._normalize_list_prefix(prefix))

        def _list() -> List[str]:
            files: List[str] = []
            for blob in self._client.list_blobs(self._bucket, prefix=search_prefix):
                if blob.name.endswith(_METADATA_SUFFIX):
                    continue
                files.append(blob.name[len(self.prefix):] if self.prefix else blob.name)
            return files

        files = await asyncio.to_thread(_list)
        logger.debug(f"Listed {len(files)} files with prefix {prefix}")
        return files

    async def get_metadata(self, key: str) -> Dict[str, Any]:
        """Get file metadata from the sidecar object."""
        from google.api_core.exceptions import NotFound

        def _download() -> bytes:
            try:
                return self._bucket.blob(self._metadata_key(key)).download_as_bytes()
            except NotFound as e:
                raise FileNotFoundError(f"Metadata not found for: {key}") from e

        body = await asyncio.to_thread(_download)
        return json.loads(body)

    async def file_exists(self, key: str) -> bool:
        """Check if a file object exists."""
        def _exists() -> bool:
            return self._bucket.blob(self._full_key(key)).exists()

        return await asyncio.to_thread(_exists)

    async def get_file_size(self, key: str) -> int:
        """Get file size in bytes."""
        def _size() -> int:
            blob = self._bucket.get_blob(self._full_key(key))
            if blob is None:
                raise FileNotFoundError(f"File not found: {key}")
            return blob.size

        return await asyncio.to_thread(_size)
