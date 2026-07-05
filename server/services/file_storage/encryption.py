"""
File Encryption Primitive

AES-256-GCM encryption for file bytes and metadata, keyed from a single
local symmetric key. Used by EncryptedFileStorageBackend to make file
storage safe for sensitive/classified content without requiring a cloud
KMS dependency.
"""

import base64
import logging
import os
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_KEY_SIZE_BYTES = 32  # AES-256
_NONCE_SIZE_BYTES = 12  # standard AES-GCM nonce size


class FileEncryptionError(Exception):
    """Raised on key/config errors, or when ciphertext fails to decrypt."""
    pass


class FileEncryptor:
    """
    Encrypts/decrypts arbitrary bytes with AES-256-GCM.

    Ciphertext layout: 12-byte random nonce || AESGCM(nonce, plaintext) (the
    GCM authentication tag is appended by the underlying AESGCM implementation).
    """

    def __init__(self, key: bytes):
        if len(key) != _KEY_SIZE_BYTES:
            raise FileEncryptionError(
                f"File encryption key must be {_KEY_SIZE_BYTES} bytes, got {len(key)}"
            )
        self._aesgcm = AESGCM(key)

    @classmethod
    def from_env(cls, env_var: str = "ORBIT_FILE_ENCRYPTION_KEY") -> "FileEncryptor":
        """
        Build a FileEncryptor from a base64-encoded 32-byte key in an env var.

        Raises:
            FileEncryptionError: If the env var is missing or not a valid
                base64-encoded 32-byte key. Fails loudly by design — a
                misconfigured encryption key must never fall back silently
                to storing sensitive content in plaintext.
        """
        raw = os.environ.get(env_var)
        if not raw:
            raise FileEncryptionError(
                f"files.encryption.enabled is true but {env_var} is not set. "
                f"Generate a key with: python -c \"import secrets, base64; "
                f"print(base64.b64encode(secrets.token_bytes(32)).decode())\""
            )
        try:
            key = base64.b64decode(raw, validate=True)
        except Exception as e:
            raise FileEncryptionError(f"{env_var} is not valid base64: {e}") from e
        return cls(key)

    def encrypt(self, data: bytes, aad: Optional[bytes] = None) -> bytes:
        """
        Args:
            data: Plaintext to encrypt.
            aad: Optional associated data (e.g. the storage key) authenticated
                but not encrypted. Binds the ciphertext to its context so it
                cannot be silently swapped onto a different storage key/file —
                decrypt() must be called with the same aad or it raises.
        """
        nonce = os.urandom(_NONCE_SIZE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, data, aad)
        return nonce + ciphertext

    def decrypt(self, data: bytes, aad: Optional[bytes] = None) -> bytes:
        if len(data) < _NONCE_SIZE_BYTES:
            raise FileEncryptionError("Ciphertext is too short to contain a nonce")
        nonce, ciphertext = data[:_NONCE_SIZE_BYTES], data[_NONCE_SIZE_BYTES:]
        try:
            return self._aesgcm.decrypt(nonce, ciphertext, aad)
        except InvalidTag as e:
            raise FileEncryptionError(
                "Failed to decrypt file: wrong key, wrong storage key, or corrupted/tampered ciphertext"
            ) from e
