"""
Encrypted Storage Backend Decorator

Wraps any FileStorageBackend and transparently encrypts file bytes and the
metadata sidecar with a FileEncryptor. Delegates everything that doesn't
touch plaintext content (existence checks, deletion, key listing) straight
to the wrapped backend.
"""

import json
import logging
from typing import Any, Dict, List

from .base_storage import FileStorageBackend
from .encryption import FileEncryptor

logger = logging.getLogger(__name__)

_ENCRYPTED_MARKER = "__encrypted__"


class EncryptedFileStorageBackend(FileStorageBackend):
    """
    Transparent encryption wrapper around a FileStorageBackend.

    Wraps the SAME inner backend instance used for plaintext storage — same
    bucket/root, just encrypt-before-write / decrypt-after-read. Metadata is
    encrypted as a JSON blob and stored inside a small unencrypted envelope
    dict so the wrapped backend's sidecar-metadata contract is unaffected.
    """

    def __init__(self, inner: FileStorageBackend, encryptor: FileEncryptor):
        self._inner = inner
        self._encryptor = encryptor

    async def put_file(self, file_data: bytes, key: str, metadata: Dict[str, Any]) -> str:
        aad = self._aad_for(key)
        encrypted_data = self._encryptor.encrypt(file_data, aad)
        encrypted_metadata = {
            _ENCRYPTED_MARKER: True,
            "payload": self._encryptor.encrypt(json.dumps(metadata).encode("utf-8"), aad).hex(),
        }
        return await self._inner.put_file(encrypted_data, key, encrypted_metadata)

    async def get_file(self, key: str) -> bytes:
        encrypted_data = await self._inner.get_file(key)
        return self._encryptor.decrypt(encrypted_data, self._aad_for(key))

    async def delete_file(self, key: str) -> bool:
        return await self._inner.delete_file(key)

    async def list_files(self, prefix: str) -> List[str]:
        return await self._inner.list_files(prefix)

    async def get_metadata(self, key: str) -> Dict[str, Any]:
        stored = await self._inner.get_metadata(key)
        if not stored.get(_ENCRYPTED_MARKER):
            return stored
        decrypted = self._encryptor.decrypt(bytes.fromhex(stored["payload"]), self._aad_for(key))
        return json.loads(decrypted.decode("utf-8"))

    @staticmethod
    def _aad_for(key: str) -> bytes:
        # Binds ciphertext to its storage key so a blob copied onto a
        # different key (e.g. by someone with raw backend access) fails to
        # decrypt instead of silently returning the wrong file's content.
        return key.encode("utf-8")

    async def file_exists(self, key: str) -> bool:
        return await self._inner.file_exists(key)

    async def get_file_size(self, key: str) -> int:
        # Returns the CIPHERTEXT size (includes a 12-byte nonce + 16-byte GCM
        # tag of overhead). Returning the exact plaintext size would require
        # a full decrypt; callers use this for display/limits, not billing.
        return await self._inner.get_file_size(key)
