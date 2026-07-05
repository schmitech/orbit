"""
Tests for File Encryption

Covers the FileEncryptor primitive, the EncryptedFileStorageBackend decorator,
and end-to-end opt-in behavior through FileProcessingService via the
per-adapter `requires_encryption` capability.
"""

import sys
from pathlib import Path

import pytest
import pytest_asyncio

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_storage.encryption import FileEncryptor, FileEncryptionError
from services.file_storage.encrypted_storage import EncryptedFileStorageBackend
from services.file_storage.filesystem_storage import FilesystemStorage
from services.file_processing.file_processing_service import FileProcessingService

TEST_KEY_B64 = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="  # 32 raw bytes, base64-encoded
OTHER_KEY_B64 = "ZmVkY2JhOTg3NjU0MzIxMGZlZGNiYTk4NzY1NDMyMTA="  # different 32-byte key


# ---------------------------------------------------------------------------
# FileEncryptor
# ---------------------------------------------------------------------------

def test_encryptor_round_trip():
    import base64
    encryptor = FileEncryptor(base64.b64decode(TEST_KEY_B64))

    plaintext = b"sensitive classified content"
    ciphertext = encryptor.encrypt(plaintext)

    assert ciphertext != plaintext
    assert encryptor.decrypt(ciphertext) == plaintext


def test_encryptor_ciphertext_is_unique_per_call():
    import base64
    encryptor = FileEncryptor(base64.b64decode(TEST_KEY_B64))

    plaintext = b"same content"
    assert encryptor.encrypt(plaintext) != encryptor.encrypt(plaintext)


def test_encryptor_rejects_wrong_key_length():
    with pytest.raises(FileEncryptionError):
        FileEncryptor(b"too-short")


def test_encryptor_detects_tampering():
    import base64
    encryptor = FileEncryptor(base64.b64decode(TEST_KEY_B64))

    ciphertext = bytearray(encryptor.encrypt(b"do not modify me"))
    ciphertext[-1] ^= 0xFF  # flip a bit in the GCM tag/ciphertext

    with pytest.raises(FileEncryptionError):
        encryptor.decrypt(bytes(ciphertext))


def test_encryptor_aad_binds_ciphertext_to_context():
    import base64
    encryptor = FileEncryptor(base64.b64decode(TEST_KEY_B64))

    ciphertext = encryptor.encrypt(b"secret", aad=b"file/a")

    # Correct AAD decrypts fine
    assert encryptor.decrypt(ciphertext, aad=b"file/a") == b"secret"

    # Wrong AAD (as if the ciphertext were swapped onto a different storage
    # key) must fail rather than silently returning the plaintext.
    with pytest.raises(FileEncryptionError):
        encryptor.decrypt(ciphertext, aad=b"file/b")

    # Missing AAD when it was used at encryption time must also fail.
    with pytest.raises(FileEncryptionError):
        encryptor.decrypt(ciphertext)


def test_encryptor_wrong_key_fails_to_decrypt():
    import base64
    encryptor_a = FileEncryptor(base64.b64decode(TEST_KEY_B64))
    encryptor_b = FileEncryptor(base64.b64decode(OTHER_KEY_B64))

    ciphertext = encryptor_a.encrypt(b"secret")
    with pytest.raises(FileEncryptionError):
        encryptor_b.decrypt(ciphertext)


def test_from_env_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ORBIT_FILE_ENCRYPTION_KEY", raising=False)
    with pytest.raises(FileEncryptionError):
        FileEncryptor.from_env()


def test_from_env_invalid_base64_raises(monkeypatch):
    monkeypatch.setenv("ORBIT_FILE_ENCRYPTION_KEY", "not-valid-base64!!!")
    with pytest.raises(FileEncryptionError):
        FileEncryptor.from_env()


def test_from_env_valid_key_succeeds(monkeypatch):
    monkeypatch.setenv("ORBIT_FILE_ENCRYPTION_KEY", TEST_KEY_B64)
    encryptor = FileEncryptor.from_env()
    assert encryptor.decrypt(encryptor.encrypt(b"ok")) == b"ok"


# ---------------------------------------------------------------------------
# EncryptedFileStorageBackend
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def encrypted_storage(tmp_path):
    import base64
    inner = FilesystemStorage(storage_root=str(tmp_path))
    encryptor = FileEncryptor(base64.b64decode(TEST_KEY_B64))
    return EncryptedFileStorageBackend(inner, encryptor), inner, tmp_path


@pytest.mark.asyncio
async def test_put_file_stores_ciphertext_on_disk(encrypted_storage):
    storage, _inner, tmp_path = encrypted_storage
    plaintext = b"classified: eyes only"
    key = "api_key/file_1/secret.txt"

    await storage.put_file(plaintext, key, {"filename": "secret.txt"})

    raw_on_disk = (tmp_path / "api_key" / "file_1" / "secret.txt").read_bytes()
    assert raw_on_disk != plaintext
    assert plaintext not in raw_on_disk


@pytest.mark.asyncio
async def test_get_file_returns_original_plaintext(encrypted_storage):
    storage, _inner, _tmp_path = encrypted_storage
    plaintext = b"round trip me"
    key = "api_key/file_2/data.bin"

    await storage.put_file(plaintext, key, {"filename": "data.bin"})
    result = await storage.get_file(key)

    assert result == plaintext


@pytest.mark.asyncio
async def test_get_metadata_round_trips_original_dict(encrypted_storage):
    storage, _inner, _tmp_path = encrypted_storage
    key = "api_key/file_3/doc.pdf"
    original_metadata = {"filename": "doc.pdf", "note": "unicode: café ☃"}

    await storage.put_file(b"content", key, original_metadata)
    result = await storage.get_metadata(key)

    assert result == original_metadata


@pytest.mark.asyncio
async def test_delete_list_and_exists_pass_through(encrypted_storage):
    storage, _inner, _tmp_path = encrypted_storage
    key = "api_key/file_4/x.txt"

    await storage.put_file(b"x", key, {"filename": "x.txt"})
    assert await storage.file_exists(key) is True
    assert key in await storage.list_files("api_key/file_4")

    deleted = await storage.delete_file(key)
    assert deleted is True
    assert await storage.file_exists(key) is False


@pytest.mark.asyncio
async def test_get_file_size_returns_ciphertext_size_with_overhead(encrypted_storage):
    storage, _inner, _tmp_path = encrypted_storage
    plaintext = b"12345"
    key = "api_key/file_5/small.txt"

    await storage.put_file(plaintext, key, {"filename": "small.txt"})
    size = await storage.get_file_size(key)

    # Ciphertext = nonce(12) + plaintext + GCM tag(16)
    assert size == len(plaintext) + 12 + 16


@pytest.mark.asyncio
async def test_get_file_not_found_raises(encrypted_storage):
    storage, _inner, _tmp_path = encrypted_storage
    with pytest.raises(FileNotFoundError):
        await storage.get_file("api_key/does_not_exist/missing.txt")


@pytest.mark.asyncio
async def test_swapped_ciphertext_between_files_fails_to_decrypt(encrypted_storage):
    """A blob copied from one file's storage key onto another's must not
    decrypt, even though it's valid ciphertext under the same key."""
    storage, inner, _tmp_path = encrypted_storage
    key_a = "api_key/file_a/a.txt"
    key_b = "api_key/file_b/b.txt"

    await storage.put_file(b"content A", key_a, {"filename": "a.txt"})
    await storage.put_file(b"content B", key_b, {"filename": "b.txt"})

    # Simulate an attacker/bug with raw backend access copying A's encrypted
    # bytes onto B's storage key.
    raw_a = await inner.get_file(key_a)
    await inner.delete_file(key_b)
    await inner.put_file(raw_a, key_b, {"filename": "b.txt"})

    with pytest.raises(FileEncryptionError):
        await storage.get_file(key_b)


# ---------------------------------------------------------------------------
# FileProcessingService integration: per-adapter opt-in
# ---------------------------------------------------------------------------

class _FakeAdapterManager:
    def __init__(self, configs):
        self._configs = configs

    def get_adapter_config(self, adapter_name):
        return self._configs.get(adapter_name)


class _FakeApiKeyService:
    def __init__(self, mapping):
        self._mapping = mapping  # api_key -> adapter_name

    async def get_adapter_for_api_key(self, api_key, adapter_manager):
        return self._mapping.get(api_key), None


class _FakeAppState:
    def __init__(self, adapter_manager, api_key_service):
        self.adapter_manager = adapter_manager
        self.api_key_service = api_key_service


def _build_service(tmp_path, encryption_enabled, monkeypatch):
    from services.file_metadata.metadata_store import FileMetadataStore

    if encryption_enabled:
        monkeypatch.setenv("ORBIT_FILE_ENCRYPTION_KEY", TEST_KEY_B64)

    test_db_path = str(tmp_path / "test_orbit_encryption.db")
    config = {
        'storage_root': str(tmp_path / "uploads"),
        'chunking_strategy': 'fixed',
        'chunk_size': 100,
        'chunk_overlap': 20,
        'max_file_size': 10485760,
        'supported_types': ['text/plain'],
        'files': {
            'encryption': {'enabled': encryption_enabled},
        },
        'internal_services': {
            'backend': {'type': 'sqlite', 'sqlite': {'database_path': test_db_path}},
        },
    }

    adapter_manager = _FakeAdapterManager({
        'classified-docs': {'capabilities': {'requires_encryption': True}},
        'general-docs': {'capabilities': {'requires_encryption': False}},
    })
    api_key_service = _FakeApiKeyService({
        'classified-key': 'classified-docs',
        'general-key': 'general-docs',
    })
    app_state = _FakeAppState(adapter_manager, api_key_service)

    FileMetadataStore.reset_instance()
    service = FileProcessingService(config, app_state=app_state)
    service.metadata_store = FileMetadataStore(config=config)
    return service, test_db_path


@pytest_asyncio.fixture
async def encryption_service(tmp_path, monkeypatch):
    service, test_db_path = _build_service(tmp_path, encryption_enabled=True, monkeypatch=monkeypatch)
    yield service
    service.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()


@pytest.mark.asyncio
async def test_classified_adapter_upload_is_encrypted_on_disk(encryption_service, tmp_path):
    plaintext = b"TOP SECRET: launch codes"
    result = await encryption_service.process_file(
        file_data=plaintext,
        filename="classified.txt",
        mime_type="text/plain",
        api_key="classified-key",
    )
    file_id = result["file_id"]

    raw_path = tmp_path / "uploads" / "classified-key" / file_id / "classified.txt"
    assert raw_path.exists()
    assert plaintext not in raw_path.read_bytes()

    # Reads back correctly through the service despite being encrypted at rest
    read_back = await encryption_service.get_file(file_id, "classified-key")
    assert read_back == plaintext


@pytest.mark.asyncio
async def test_general_adapter_upload_stays_plaintext(encryption_service, tmp_path):
    plaintext = b"just a memo, nothing sensitive"
    result = await encryption_service.process_file(
        file_data=plaintext,
        filename="memo.txt",
        mime_type="text/plain",
        api_key="general-key",
    )
    file_id = result["file_id"]

    raw_path = tmp_path / "uploads" / "general-key" / file_id / "memo.txt"
    assert raw_path.read_bytes() == plaintext

    read_back = await encryption_service.get_file(file_id, "general-key")
    assert read_back == plaintext


@pytest.mark.asyncio
async def test_classified_adapter_upload_fails_loudly_without_encryption_enabled(tmp_path, monkeypatch):
    service, test_db_path = _build_service(tmp_path, encryption_enabled=False, monkeypatch=monkeypatch)
    try:
        with pytest.raises(ValueError, match="requires encrypted file storage"):
            await service.process_file(
                file_data=b"should never be stored in plaintext",
                filename="classified.txt",
                mime_type="text/plain",
                api_key="classified-key",
            )
    finally:
        service.metadata_store.close()
        from services.file_metadata.metadata_store import FileMetadataStore
        FileMetadataStore.reset_instance()


class _FailingApiKeyService:
    """Simulates a transient failure in adapter lookup (e.g. a DB hiccup)."""

    async def get_adapter_for_api_key(self, api_key, adapter_manager):
        raise RuntimeError("simulated lookup failure")


@pytest.mark.asyncio
async def test_upload_fails_closed_when_capability_lookup_errors(tmp_path, monkeypatch):
    """If the adapter/capability lookup itself raises, the upload must fail
    rather than silently defaulting to unencrypted storage — a transient
    error must never be indistinguishable from 'no encryption required'."""
    service, test_db_path = _build_service(tmp_path, encryption_enabled=True, monkeypatch=monkeypatch)
    service.app_state.api_key_service = _FailingApiKeyService()
    try:
        with pytest.raises(RuntimeError, match="simulated lookup failure"):
            await service.process_file(
                file_data=b"must not be silently stored in plaintext",
                filename="classified.txt",
                mime_type="text/plain",
                api_key="classified-key",
            )
    finally:
        service.metadata_store.close()
        from services.file_metadata.metadata_store import FileMetadataStore
        FileMetadataStore.reset_instance()


# ---------------------------------------------------------------------------
# Metadata durability: encryption state must survive later metadata updates
# and reads must fail loudly if decryption becomes unavailable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_file_metadata_preserves_encrypted_flag(encryption_service):
    """A later partial metadata update (e.g. recording a processing error)
    must not clobber the 'encrypted' flag recorded at upload time."""
    result = await encryption_service.process_file(
        file_data=b"classified content",
        filename="classified.txt",
        mime_type="text/plain",
        api_key="classified-key",
    )
    file_id = result["file_id"]

    file_info_before = await encryption_service.metadata_store.get_file_info(file_id)
    assert file_info_before["metadata"]["encrypted"] is True

    # Simulate what process_file_content does on failure/timeout: a partial
    # metadata update carrying only error fields.
    await encryption_service.metadata_store.update_file_metadata(
        file_id, {"error": "processing timed out", "failed_at": "2026-01-01T00:00:00Z"}
    )

    file_info_after = await encryption_service.metadata_store.get_file_info(file_id)
    assert file_info_after["metadata"]["encrypted"] is True
    assert file_info_after["metadata"]["error"] == "processing timed out"

    # The read path must still decrypt correctly after the metadata update.
    read_back = await encryption_service.get_file(file_id, "classified-key")
    assert read_back == b"classified content"


@pytest.mark.asyncio
async def test_read_fails_loudly_when_encrypted_file_has_no_decryptor(tmp_path, monkeypatch):
    """If a file's metadata says it was encrypted but the service has no
    encrypted_storage configured (encryption disabled/misconfigured after the
    fact), reads must raise instead of silently returning ciphertext."""
    service, test_db_path = _build_service(tmp_path, encryption_enabled=False, monkeypatch=monkeypatch)
    try:
        file_info = {"metadata": {"encrypted": True}}
        with pytest.raises(ValueError, match="Cannot decrypt"):
            service._select_storage_for_read(file_info)
    finally:
        service.metadata_store.close()
        from services.file_metadata.metadata_store import FileMetadataStore
        FileMetadataStore.reset_instance()
