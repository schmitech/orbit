"""
Two-Factor Authentication (TOTP) Service
========================================

Enrollment, verification, and recovery-code management for local-password
2FA. External (Entra/Auth0) identities are out of scope - 2FA for those is
the IdP's own responsibility.

The TOTP secret is symmetric (unlike a password hash, anyone who reads it
can generate valid codes forever), so it is encrypted at rest with the same
AES-256-GCM primitive already used for file storage
(``server/services/file_storage/encryption.py``), keyed from a dedicated env
var so a leaked file-encryption key does not also expose every TOTP secret.
"""

import base64
import hashlib
import io
import json
import logging
import secrets
from datetime import datetime, UTC
from typing import Any, Optional

import pyotp
import qrcode

from services.database_service import DatabaseService
from services.file_storage.encryption import FileEncryptor

logger = logging.getLogger(__name__)

DEFAULT_RECOVERY_CODES_COUNT = 10
_MFA_ENCRYPTION_KEY_ENV_VAR = "ORBIT_MFA_ENCRYPTION_KEY"


class MfaError(ValueError):
    """Raised for malformed input or invalid state transitions."""


def _hash_recovery_code(code: str) -> str:
    """Hash a recovery code for storage.

    High-entropy random strings (not user-chosen passwords), so a fast
    SHA-256 is sufficient here - unlike password hashing, there is no
    meaningful dictionary/brute-force surface to slow down.
    """
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_recovery_codes(count: int) -> list[str]:
    return [secrets.token_hex(5) for _ in range(count)]


def _render_qr_code_data_uri(otpauth_uri: str) -> str:
    """Render an ``otpauth://`` URI to a scannable QR code, as a data: URI.

    Rendered server-side (rather than left to the frontend) so any admin
    client can display it with a plain ``<img>`` tag, no QR library required
    on that end.
    """
    img = qrcode.make(otpauth_uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


class MfaService:
    """Manages per-user TOTP enrollment, verification, and recovery codes."""

    COLLECTION = "user_mfa"

    def __init__(self, config: dict[str, Any], database_service: DatabaseService):
        self.config = config
        self.database = database_service
        self.collection_name = self.COLLECTION

        two_factor_config = config.get("auth", {}).get("two_factor", {}) or {}
        self.enabled = bool(two_factor_config.get("enabled", False))
        self.required_for_roles = list(two_factor_config.get("required_for_roles", []) or [])
        self.issuer_name = two_factor_config.get("issuer_name", "ORBIT")
        self.recovery_codes_count = int(
            two_factor_config.get("recovery_codes_count", DEFAULT_RECOVERY_CODES_COUNT)
        )
        self.remember_device_days = int(two_factor_config.get("remember_device_days", 0))

        self._encryptor: Optional[FileEncryptor] = None

    def _get_encryptor(self) -> FileEncryptor:
        """Lazily build the encryptor, failing loudly if the key is missing.

        Deferred rather than built in ``__init__`` so a deployment that never
        enables 2FA is not forced to configure the env var.
        """
        if self._encryptor is None:
            self._encryptor = FileEncryptor.from_env(_MFA_ENCRYPTION_KEY_ENV_VAR)
        return self._encryptor

    def _encrypt_secret(self, user_id: str, secret: str) -> str:
        encryptor = self._get_encryptor()
        ciphertext = encryptor.encrypt(secret.encode("utf-8"), aad=user_id.encode("utf-8"))
        return ciphertext.hex()

    def _decrypt_secret(self, user_id: str, encrypted_hex: str) -> str:
        encryptor = self._get_encryptor()
        plaintext = encryptor.decrypt(bytes.fromhex(encrypted_hex), aad=user_id.encode("utf-8"))
        return plaintext.decode("utf-8")

    async def get_record(self, user_id: str) -> Optional[dict[str, Any]]:
        return await self.database.find_one(self.collection_name, {"user_id": str(user_id)})

    async def is_enabled(self, user_id: str) -> bool:
        record = await self.get_record(user_id)
        return bool(record and record.get("enabled"))

    def role_requires_2fa(self, roles: list[str]) -> bool:
        return any(role in self.required_for_roles for role in (roles or []))

    async def begin_enrollment(self, user_id: str, username: str) -> dict[str, Any]:
        """Generate a new pending secret and return the enrollment material.

        Overwrites any prior pending (unconfirmed) enrollment. Does not touch
        an already-``enabled`` record - the caller must disable first.
        """
        existing = await self.get_record(user_id)
        if existing and existing.get("enabled"):
            raise MfaError("2FA is already enabled for this account")

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        otpauth_uri = totp.provisioning_uri(name=username, issuer_name=self.issuer_name)

        doc = {
            "user_id": str(user_id),
            "totp_secret_encrypted": self._encrypt_secret(str(user_id), secret),
            "enabled": False,
            "recovery_codes_hashed": None,
            "created_at": datetime.now(UTC),
            "enabled_at": None,
        }
        if existing:
            await self.database.update_one(
                self.collection_name, {"user_id": str(user_id)}, {"$set": doc}
            )
        else:
            await self.database.insert_one(self.collection_name, doc)

        return {
            "secret": secret,
            "otpauth_uri": otpauth_uri,
            "qr_code_data_uri": _render_qr_code_data_uri(otpauth_uri),
        }

    async def confirm_enrollment(self, user_id: str, code: str) -> Optional[list[str]]:
        """Verify the confirmation code and flip ``enabled`` to true.

        Returns the plaintext recovery codes (shown to the user exactly once)
        on success, or None if there is no pending enrollment or the code is
        invalid - proving the user actually captured the secret in their
        authenticator app before it can lock them out.
        """
        record = await self.get_record(user_id)
        if not record or record.get("enabled"):
            return None

        secret = self._decrypt_secret(str(user_id), record["totp_secret_encrypted"])
        if not pyotp.TOTP(secret).verify(code, valid_window=1):
            return None

        recovery_codes = _generate_recovery_codes(self.recovery_codes_count)
        recovery_entries = [
            {"hash": _hash_recovery_code(c), "consumed": False} for c in recovery_codes
        ]

        await self.database.update_one(
            self.collection_name,
            {"user_id": str(user_id)},
            {"$set": {
                "enabled": True,
                "enabled_at": datetime.now(UTC),
                "recovery_codes_hashed": json.dumps(recovery_entries),
            }},
        )
        return recovery_codes

    async def verify_totp(self, user_id: str, code: str) -> bool:
        """Verify a 6-digit TOTP code against the user's confirmed secret."""
        record = await self.get_record(user_id)
        if not record or not record.get("enabled"):
            return False
        secret = self._decrypt_secret(str(user_id), record["totp_secret_encrypted"])
        return pyotp.TOTP(secret).verify(code, valid_window=1)

    async def verify_recovery_code(self, user_id: str, code: str) -> bool:
        """Consume one recovery code. Each code is valid for exactly one use.

        Consumed codes are marked, not deleted, so the full set of issued
        codes remains auditable.

        Consumption is a compare-and-swap: the update's filter includes the
        exact JSON blob read here, so it only succeeds if no one else has
        already rewritten the row. Two concurrent requests for the same code
        both read ``consumed: false``, but only the first writer's filter
        still matches - the second's update affects zero rows and the code
        is correctly rejected, rather than both callers reporting success.
        """
        record = await self.get_record(user_id)
        if not record or not record.get("enabled") or not record.get("recovery_codes_hashed"):
            return False

        previous_json = record["recovery_codes_hashed"]
        entries = json.loads(previous_json)
        target_hash = _hash_recovery_code(code.strip())
        for entry in entries:
            if entry["hash"] == target_hash and not entry["consumed"]:
                entry["consumed"] = True
                updated = await self.database.update_one(
                    self.collection_name,
                    {"user_id": str(user_id), "recovery_codes_hashed": previous_json},
                    {"$set": {"recovery_codes_hashed": json.dumps(entries)}},
                )
                return bool(updated)
        return False

    async def verify_code_or_recovery(self, user_id: str, code: str) -> bool:
        """Accept either a live TOTP code or a one-time recovery code."""
        code = (code or "").strip()
        if not code:
            return False
        if code.isdigit() and len(code) == 6:
            if await self.verify_totp(user_id, code):
                return True
        return await self.verify_recovery_code(user_id, code)

    async def remember_device(self, user_id: str) -> Optional[str]:
        """Mint a device token exempting this device from 2FA for
        ``remember_device_days``. Returns None if the feature is disabled."""
        if self.remember_device_days <= 0:
            return None

        record = await self.get_record(user_id)
        if not record:
            return None

        devices = json.loads(record.get("remembered_devices") or "[]")
        raw_token = secrets.token_hex(32)
        from datetime import timedelta
        expires_at = (datetime.now(UTC) + timedelta(days=self.remember_device_days)).isoformat()
        devices.append({"hash": hashlib.sha256(raw_token.encode("utf-8")).hexdigest(), "expires_at": expires_at})
        await self.database.update_one(
            self.collection_name,
            {"user_id": str(user_id)},
            {"$set": {"remembered_devices": json.dumps(devices)}},
        )
        return raw_token

    async def is_device_remembered(self, user_id: str, device_token: str) -> bool:
        """Check whether ``device_token`` was previously remembered for this user."""
        if not device_token:
            return False
        record = await self.get_record(user_id)
        if not record or not record.get("remembered_devices"):
            return False

        target_hash = hashlib.sha256(device_token.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        for entry in json.loads(record["remembered_devices"]):
            if entry["hash"] != target_hash:
                continue
            try:
                expires_at = datetime.fromisoformat(entry["expires_at"])
                expires_at = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
            except (ValueError, KeyError):
                continue
            return expires_at > now
        return False

    async def admin_reset(self, user_id: str) -> bool:
        """Disable and clear 2FA for a user who lost their device and codes.

        Deletes the row entirely rather than just flipping ``enabled`` off,
        so a subsequent re-enrollment starts clean.
        """
        deleted = await self.database.delete_one(self.collection_name, {"user_id": str(user_id)})
        return bool(deleted)
