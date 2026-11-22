"""
Characterization tests for the two file-processing pipelines
(`process_file_content` and `process_file`) ahead of the merge described in
docs/roadmap/file-processing-service-simplification.md item 1.

These pin down today's behavior for the success path, partial (extraction)
failure, timeout, encryption on/off, and deletion-during-extraction so the
eventual merge into a shared persistence helper is provably
behavior-preserving. Not meant to test new behavior - every assertion here
should already pass against the current, unmerged code.
"""

import json
import sys
from pathlib import Path

import pytest
import pytest_asyncio

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.file_processing_service import FileProcessingService

TEST_KEY_B64 = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="  # 32 raw bytes, base64-encoded


class _FakeAdapterManager:
    def __init__(self, configs):
        self._configs = configs

    def get_adapter_config(self, adapter_name):
        return self._configs.get(adapter_name)


class _FakeApiKeyService:
    def __init__(self, mapping):
        self._mapping = mapping  # api_key -> adapter_name

    async def get_adapter_for_api_key(self, api_key, adapter_manager, current_user_id=None, current_user_email=None):
        return self._mapping.get(api_key), None


class _FakeAppState:
    def __init__(self, adapter_manager, api_key_service):
        self.adapter_manager = adapter_manager
        self.api_key_service = api_key_service


def _build_service(tmp_path, monkeypatch, encryption_enabled=False):
    from services.file_metadata.metadata_store import FileMetadataStore

    if encryption_enabled:
        monkeypatch.setenv("ORBIT_FILE_ENCRYPTION_KEY", TEST_KEY_B64)

    test_db_path = str(tmp_path / "test_orbit_pipeline_characterization.db")
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
        'test_api_key': 'general-docs',
    })
    app_state = _FakeAppState(adapter_manager, api_key_service)

    FileMetadataStore.reset_instance()
    service = FileProcessingService(config, app_state=app_state)
    service.metadata_store = FileMetadataStore(config=config)
    return service


@pytest_asyncio.fixture
async def service(tmp_path, monkeypatch):
    svc = _build_service(tmp_path, monkeypatch)
    yield svc
    svc.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()


@pytest_asyncio.fixture
async def encrypted_service(tmp_path, monkeypatch):
    svc = _build_service(tmp_path, monkeypatch, encryption_enabled=True)
    yield svc
    svc.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()


FILE_DATA = b"Some content to extract and chunk for characterization."
FILENAME = "characterize.txt"
MIME_TYPE = "text/plain"
API_KEY = "test_api_key"


# ---------------------------------------------------------------------------
# process_file_content - the background pipeline (production entry point)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_file_content_success(service):
    file_id = await service.quick_upload(FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    await service.process_file_content(file_id, FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    file_info = await service.metadata_store.get_file_info(file_id)
    assert file_info['processing_status'] == 'completed'
    assert file_info['chunk_count'] > 0

    chunks = await service.metadata_store.get_file_chunks(file_id)
    assert len(chunks) == file_info['chunk_count']


@pytest.mark.asyncio
async def test_process_file_content_extraction_failure_marks_failed(service, monkeypatch):
    file_id = await service.quick_upload(FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated extraction failure")

    monkeypatch.setattr(service, "_extract_content", _boom)

    # process_file_content swallows the exception and records failure instead
    # of propagating - callers (background tasks) must not crash.
    await service.process_file_content(file_id, FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    file_info = await service.metadata_store.get_file_info(file_id)
    assert file_info['processing_status'] == 'failed'
    assert file_info['chunk_count'] == 0
    assert 'simulated extraction failure' in file_info.get('metadata', {}).get('error', '')


@pytest.mark.asyncio
async def test_process_file_content_timeout_marks_failed(service, monkeypatch):
    file_id = await service.quick_upload(FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    async def _times_out(*args, **kwargs):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(service, "_extract_content", _times_out)

    await service.process_file_content(file_id, FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    file_info = await service.metadata_store.get_file_info(file_id)
    assert file_info['processing_status'] == 'failed'
    assert file_info['chunk_count'] == 0
    assert 'timed out' in file_info.get('metadata', {}).get('error', '')


@pytest.mark.asyncio
async def test_process_file_content_deletion_during_extraction_skips_persistence(service, monkeypatch):
    """A user can delete the file while an async processor is still
    extracting. process_file_content must observe the missing file record
    under its lock and return early - without raising, without indexing, and
    without resurrecting the file's metadata row."""
    file_id = await service.quick_upload(FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    original_extract = service._extract_content

    async def _extract_then_delete(*args, **kwargs):
        result = await original_extract(*args, **kwargs)
        # Simulate a concurrent delete landing after extraction starts but
        # before this task reaches the persistence boundary.
        await service.metadata_store.delete_file(file_id)
        return result

    monkeypatch.setattr(service, "_extract_content", _extract_then_delete)

    # Must not raise even though the file record is gone by persistence time.
    await service.process_file_content(file_id, FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    file_info = await service.metadata_store.get_file_info(file_id)
    assert file_info is None

    chunks = await service.metadata_store.get_file_chunks(file_id)
    assert chunks == []


@pytest.mark.asyncio
async def test_process_file_content_encrypts_chunks_when_required(encrypted_service):
    file_id = await encrypted_service.quick_upload(
        FILE_DATA, FILENAME, MIME_TYPE, "classified-key"
    )

    await encrypted_service.process_file_content(file_id, FILE_DATA, FILENAME, MIME_TYPE, "classified-key")

    file_info = await encrypted_service.metadata_store.get_file_info(file_id)
    assert file_info['processing_status'] == 'completed'

    chunks = await encrypted_service.metadata_store.get_file_chunks(file_id)
    assert len(chunks) > 0
    for chunk in chunks:
        assert json.loads(chunk['chunk_metadata']).get('encrypted') is True
        assert FILE_DATA.decode() not in str(chunk['chunk_metadata'])


@pytest.mark.asyncio
async def test_process_file_content_plaintext_when_not_required(service):
    file_id = await service.quick_upload(FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    await service.process_file_content(file_id, FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    chunks = await service.metadata_store.get_file_chunks(file_id)
    assert len(chunks) > 0
    for chunk in chunks:
        assert json.loads(chunk['chunk_metadata']).get('encrypted') is not True


@pytest.mark.asyncio
async def test_process_file_content_re_reads_stored_encryption_flag(service, monkeypatch):
    """process_file_content decides encryption from the *stored* file record
    (re-read under the persistence lock), not from a fresh capability lookup -
    so a capability change mid-extraction doesn't change how an in-flight
    upload gets persisted."""
    file_id = await service.quick_upload(FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    # Flip the adapter's capability after upload, simulating a config change
    # while extraction is still in flight.
    service.app_state.adapter_manager._configs['general-docs']['capabilities']['requires_encryption'] = True

    await service.process_file_content(file_id, FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    chunks = await service.metadata_store.get_file_chunks(file_id)
    assert len(chunks) > 0
    for chunk in chunks:
        # Still plaintext: the stored 'encrypted' flag from upload time wins.
        assert json.loads(chunk['chunk_metadata']).get('encrypted') is not True


# ---------------------------------------------------------------------------
# process_file - the synchronous pipeline (no production caller; tests only)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_file_success_returns_metadata_field(service):
    result = await service.process_file(FILE_DATA, FILENAME, MIME_TYPE, API_KEY)

    assert result['status'] == 'completed'
    assert result['chunk_count'] > 0
    assert 'metadata' in result
    assert result['metadata'] is not None


@pytest.mark.asyncio
async def test_process_file_extraction_failure_marks_failed_and_raises(service, monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated extraction failure")

    monkeypatch.setattr(service, "_extract_content", _boom)

    with pytest.raises(RuntimeError, match="simulated extraction failure"):
        await service.process_file(FILE_DATA, FILENAME, MIME_TYPE, API_KEY)


@pytest.mark.asyncio
async def test_process_file_uses_upload_time_encryption_decision(encrypted_service, monkeypatch):
    """Unlike process_file_content, process_file computes requires_encryption
    once at upload time and reuses that same value for persistence - there is
    no background gap for a stored flag to diverge from a fresh lookup."""
    result = await encrypted_service.process_file(FILE_DATA, FILENAME, MIME_TYPE, "classified-key")
    assert result['status'] == 'completed'

    chunks = await encrypted_service.metadata_store.get_file_chunks(result['file_id'])
    assert len(chunks) > 0
    for chunk in chunks:
        assert json.loads(chunk['chunk_metadata']).get('encrypted') is True
