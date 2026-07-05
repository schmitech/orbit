"""
Azure Blob Storage Backend

Azure Blob Storage implementation of FileStorageBackend. Stores files as blobs
with a JSON metadata sidecar blob, mirroring the filesystem backend's layout so
behaviour is identical across backends.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional

from .base_storage import FileStorageBackend

logger = logging.getLogger(__name__)

_METADATA_SUFFIX = ".metadata.json"


class AzureBlobStorage(FileStorageBackend):
    """
    Azure Blob storage backend.

    Blob layout mirrors the filesystem backend (Azure treats '/' as a virtual
    folder separator):
        {prefix}{api_key}/{file_id}/{filename}                  # the file
        {prefix}{api_key}/{file_id}/{filename}.metadata.json    # metadata sidecar

    The synchronous azure-storage-blob SDK is used, with every network call
    dispatched to a worker thread via ``asyncio.to_thread``.
    """

    def __init__(
        self,
        container: str,
        prefix: str = "",
        connection_string: Optional[str] = None,
        account_url: Optional[str] = None,
        account_key: Optional[str] = None,
    ):
        """
        Initialize the Azure Blob storage backend.

        Auth precedence:
            1. connection_string (if provided)
            2. account_url + account_key
            3. account_url + DefaultAzureCredential (managed identity / Entra)

        Args:
            container: Name of an existing blob container (not created implicitly).
            prefix: Optional blob-name prefix applied to every blob.
            connection_string: Azure Storage connection string.
            account_url: Storage account URL (e.g. https://acct.blob.core.windows.net).
            account_key: Storage account access key (used with account_url).
        """
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as e:
            raise ImportError(
                "The Azure Blob storage backend requires azure-storage-blob. Install it with "
                "'./install/setup.sh --profile cloud-services' or 'pip install azure-storage-blob azure-identity'."
            ) from e

        self.prefix = self._normalize_prefix(prefix)

        if connection_string:
            service_client = BlobServiceClient.from_connection_string(connection_string)
        elif account_url:
            credential: Any = account_key
            if not credential:
                try:
                    from azure.identity import DefaultAzureCredential
                except ImportError as e:
                    raise ImportError(
                        "Identity-based Azure auth requires azure-identity. Install it with "
                        "'./install/setup.sh --profile cloud-services' or 'pip install azure-identity'."
                    ) from e
                credential = DefaultAzureCredential()
            service_client = BlobServiceClient(account_url=account_url, credential=credential)
        else:
            raise ValueError(
                "Azure Blob storage requires either a connection_string or an account_url."
            )

        self._container = service_client.get_container_client(container)

        # Fail loudly if the container does not exist / is not accessible.
        try:
            self._container.get_container_properties()
        except Exception as e:
            raise RuntimeError(
                f"Azure container '{container}' is not accessible: {e}. "
                "Create it (or fix credentials/permissions) before starting the server."
            ) from e

        logger.info(
            f"Initialized AzureBlobStorage (container={container}, prefix='{self.prefix}')"
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
        """Get the sidecar blob name for a storage key."""
        return self._full_key(key) + _METADATA_SUFFIX

    async def put_file(self, file_data: bytes, key: str, metadata: Dict[str, Any]) -> str:
        """Store a file blob and its metadata sidecar (each upload is atomic)."""
        metadata_bytes = json.dumps(metadata).encode("utf-8")

        await asyncio.to_thread(
            self._container.upload_blob,
            name=self._metadata_key(key),
            data=metadata_bytes,
            overwrite=True,
        )
        await asyncio.to_thread(
            self._container.upload_blob,
            name=self._full_key(key),
            data=file_data,
            overwrite=True,
        )

        logger.debug(f"Stored blob {self._full_key(key)} ({len(file_data)} bytes)")
        return key

    async def get_file(self, key: str) -> bytes:
        """Retrieve file contents."""
        from azure.core.exceptions import ResourceNotFoundError

        def _download() -> bytes:
            try:
                return self._container.download_blob(self._full_key(key)).readall()
            except ResourceNotFoundError as e:
                raise FileNotFoundError(f"File not found: {key}") from e

        return await asyncio.to_thread(_download)

    async def delete_file(self, key: str) -> bool:
        """Delete the file blob and its metadata sidecar."""
        from azure.core.exceptions import ResourceNotFoundError

        deleted = await self.file_exists(key)

        def _delete(name: str) -> None:
            try:
                self._container.delete_blob(name)
            except ResourceNotFoundError:
                pass

        await asyncio.to_thread(_delete, self._full_key(key))
        await asyncio.to_thread(_delete, self._metadata_key(key))

        if deleted:
            logger.debug(f"Deleted blob {self._full_key(key)}")
        return deleted

    async def list_files(self, prefix: str) -> List[str]:
        """List file keys under a prefix (metadata sidecars excluded)."""
        search_prefix = self._full_key(self._normalize_list_prefix(prefix))

        def _list() -> List[str]:
            files: List[str] = []
            for blob in self._container.list_blobs(name_starts_with=search_prefix):
                if blob.name.endswith(_METADATA_SUFFIX):
                    continue
                files.append(blob.name[len(self.prefix):] if self.prefix else blob.name)
            return files

        files = await asyncio.to_thread(_list)
        logger.debug(f"Listed {len(files)} files with prefix {prefix}")
        return files

    async def get_metadata(self, key: str) -> Dict[str, Any]:
        """Get file metadata from the sidecar blob."""
        from azure.core.exceptions import ResourceNotFoundError

        def _download() -> bytes:
            try:
                return self._container.download_blob(self._metadata_key(key)).readall()
            except ResourceNotFoundError as e:
                raise FileNotFoundError(f"Metadata not found for: {key}") from e

        body = await asyncio.to_thread(_download)
        return json.loads(body)

    async def file_exists(self, key: str) -> bool:
        """Check if a file blob exists."""
        return await asyncio.to_thread(
            self._container.get_blob_client(self._full_key(key)).exists
        )

    async def get_file_size(self, key: str) -> int:
        """Get file size in bytes."""
        from azure.core.exceptions import ResourceNotFoundError

        def _size() -> int:
            try:
                return self._container.get_blob_client(self._full_key(key)).get_blob_properties().size
            except ResourceNotFoundError as e:
                raise FileNotFoundError(f"File not found: {key}") from e

        return await asyncio.to_thread(_size)
