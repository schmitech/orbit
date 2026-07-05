"""
S3 Storage Backend

AWS S3 (and S3-compatible, e.g. MinIO) implementation of FileStorageBackend.
Stores files as objects with a JSON metadata sidecar object, mirroring the
filesystem backend's layout so behaviour is identical across backends.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional

from .base_storage import FileStorageBackend

logger = logging.getLogger(__name__)

_METADATA_SUFFIX = ".metadata.json"


class S3Storage(FileStorageBackend):
    """
    S3 storage backend for AWS S3 and S3-compatible object stores (MinIO).

    Object layout mirrors the filesystem backend:
        {prefix}{api_key}/{file_id}/{filename}                  # the file
        {prefix}{api_key}/{file_id}/{filename}.metadata.json    # metadata sidecar

    boto3 is synchronous, so every network call is dispatched to a worker
    thread via ``asyncio.to_thread`` to keep the async interface honest.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: Optional[str] = None,
        region_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        path_style: bool = False,
    ):
        """
        Initialize the S3 storage backend.

        Args:
            bucket: Name of an existing S3 bucket (not created implicitly).
            prefix: Optional key prefix applied to every object.
            endpoint_url: Custom endpoint for S3-compatible stores (MinIO).
            region_name: AWS region.
            aws_access_key_id: Optional explicit access key (omit to use the
                boto3 default credential chain: env / instance role / SSO).
            aws_secret_access_key: Optional explicit secret key.
            path_style: Use path-style addressing (required by most MinIO setups).
        """
        try:
            import boto3
            from botocore.client import Config
        except ImportError as e:
            raise ImportError(
                "The S3 storage backend requires boto3. Install it with "
                "'./install/setup.sh --profile cloud-services' or 'pip install boto3'."
            ) from e

        self.bucket = bucket
        self.prefix = self._normalize_prefix(prefix)

        client_config = Config(s3={"addressing_style": "path"}) if path_style else None
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region_name or None,
            aws_access_key_id=aws_access_key_id or None,
            aws_secret_access_key=aws_secret_access_key or None,
            config=client_config,
        )

        # Fail loudly if the bucket does not exist / is not accessible.
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception as e:
            raise RuntimeError(
                f"S3 bucket '{self.bucket}' is not accessible: {e}. "
                "Create it (or fix credentials/permissions) before starting the server."
            ) from e

        logger.info(
            f"Initialized S3Storage (bucket={self.bucket}, prefix='{self.prefix}', "
            f"endpoint={endpoint_url or 'aws'})"
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
        """Get the sidecar object key for a storage key."""
        return self._full_key(key) + _METADATA_SUFFIX

    @staticmethod
    def _is_not_found(error) -> bool:
        """Check whether a botocore ClientError represents a missing object."""
        from botocore.exceptions import ClientError
        if not isinstance(error, ClientError):
            return False
        code = error.response.get("Error", {}).get("Code", "")
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return code in ("NoSuchKey", "404", "NotFound") or status == 404

    async def put_file(self, file_data: bytes, key: str, metadata: Dict[str, Any]) -> str:
        """Store a file object and its metadata sidecar (each put_object is atomic)."""
        metadata_bytes = json.dumps(metadata).encode("utf-8")

        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=self._metadata_key(key),
            Body=metadata_bytes,
            ContentType="application/json",
        )
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=self._full_key(key),
            Body=file_data,
        )

        logger.debug(f"Stored file at s3://{self.bucket}/{self._full_key(key)} ({len(file_data)} bytes)")
        return key

    async def get_file(self, key: str) -> bytes:
        """Retrieve file contents."""
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self.bucket, Key=self._full_key(key)
            )
        except Exception as e:
            if self._is_not_found(e):
                raise FileNotFoundError(f"File not found: {key}") from e
            raise
        return await asyncio.to_thread(response["Body"].read)

    async def delete_file(self, key: str) -> bool:
        """Delete the file object and its metadata sidecar."""
        deleted = await self.file_exists(key)

        await asyncio.to_thread(
            self._client.delete_object, Bucket=self.bucket, Key=self._full_key(key)
        )
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self.bucket, Key=self._metadata_key(key)
        )

        if deleted:
            logger.debug(f"Deleted s3://{self.bucket}/{self._full_key(key)}")
        return deleted

    async def list_files(self, prefix: str) -> List[str]:
        """List file keys under a prefix (metadata sidecars excluded)."""
        search_prefix = self._full_key(self._normalize_list_prefix(prefix))

        def _list() -> List[str]:
            files: List[str] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=search_prefix):
                for obj in page.get("Contents", []):
                    full_key = obj["Key"]
                    if full_key.endswith(_METADATA_SUFFIX):
                        continue
                    # Strip the configured prefix to return caller-space keys.
                    files.append(full_key[len(self.prefix):] if self.prefix else full_key)
            return files

        files = await asyncio.to_thread(_list)
        logger.debug(f"Listed {len(files)} files with prefix {prefix}")
        return files

    async def get_metadata(self, key: str) -> Dict[str, Any]:
        """Get file metadata from the sidecar object."""
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self.bucket, Key=self._metadata_key(key)
            )
        except Exception as e:
            if self._is_not_found(e):
                raise FileNotFoundError(f"Metadata not found for: {key}") from e
            raise
        body = await asyncio.to_thread(response["Body"].read)
        return json.loads(body)

    async def file_exists(self, key: str) -> bool:
        """Check if a file object exists."""
        try:
            await asyncio.to_thread(
                self._client.head_object, Bucket=self.bucket, Key=self._full_key(key)
            )
            return True
        except Exception as e:
            if self._is_not_found(e):
                return False
            raise

    async def get_file_size(self, key: str) -> int:
        """Get file size in bytes."""
        try:
            response = await asyncio.to_thread(
                self._client.head_object, Bucket=self.bucket, Key=self._full_key(key)
            )
        except Exception as e:
            if self._is_not_found(e):
                raise FileNotFoundError(f"File not found: {key}") from e
            raise
        return response["ContentLength"]
