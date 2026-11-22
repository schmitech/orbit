"""
Behavior-pinning tests for the vision/audio dispatch special-casing in
_extract_content/_validate_file, ahead of the registry-based dispatch rewrite
described in docs/roadmap/file-processing-service-simplification.md item 3.

These pin down three behaviors the doc calls out as easy to accidentally
change in a "transparent" registry rewrite:

1. Upload-time validation accepts allowlisted image/audio MIME types
   independently of whether vision/audio is actually enabled.
2. Extraction-time: vision/audio bypass the registry's multi-processor
   fallback loop entirely - a failure is not retried with a different
   processor the way Docling -> MarkItDown is.
3. When AI OCR is the priority processor, generic vision is skipped entirely
   for image MIME types, including when AI OCR itself then fails - there is
   no "OCR failed, fall back to generic vision" path today.

Not meant to test new behavior - every assertion here should already pass
against the current, unmerged code.
"""

import sys
from pathlib import Path

import pytest
import pytest_asyncio

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.file_processing_service import FileProcessingService


def _build_service(tmp_path, *, enable_vision=True, enable_audio=True, ai_ocr_priority=False):
    from services.file_metadata.metadata_store import FileMetadataStore

    test_db_path = str(tmp_path / "test_orbit_dispatch_characterization.db")
    config = {
        'storage_root': str(tmp_path / "uploads"),
        'chunking_strategy': 'fixed',
        'chunk_size': 100,
        'chunk_overlap': 20,
        'max_file_size': 10485760,
        'supported_types': ['text/plain', 'image/png', 'audio/mpeg'],
        'enable_vision': enable_vision,
        'enable_audio': enable_audio,
        'internal_services': {
            'backend': {'type': 'sqlite', 'sqlite': {'database_path': test_db_path}},
        },
    }
    if ai_ocr_priority:
        config['files'] = {
            'processing': {
                'ai_document_enabled': True,
                'processor_priority': 'ai_document',
            }
        }

    FileMetadataStore.reset_instance()
    service = FileProcessingService(config)
    service.metadata_store = FileMetadataStore(config=config)
    return service


@pytest_asyncio.fixture
async def service(tmp_path):
    svc = _build_service(tmp_path)
    yield svc
    svc.metadata_store.close()
    from services.file_metadata.metadata_store import FileMetadataStore
    FileMetadataStore.reset_instance()


# ---------------------------------------------------------------------------
# 1. Upload-time validation is independent of enable_vision/enable_audio
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_file_accepts_image_mime_even_when_vision_disabled(tmp_path):
    service = _build_service(tmp_path, enable_vision=False)
    try:
        assert service._validate_file(b"fake png bytes", "image/png") is True
    finally:
        service.metadata_store.close()
        from services.file_metadata.metadata_store import FileMetadataStore
        FileMetadataStore.reset_instance()


@pytest.mark.asyncio
async def test_validate_file_accepts_audio_mime_even_when_audio_disabled(tmp_path):
    service = _build_service(tmp_path, enable_audio=False)
    try:
        assert service._validate_file(b"fake mp3 bytes", "audio/mpeg") is True
    finally:
        service.metadata_store.close()
        from services.file_metadata.metadata_store import FileMetadataStore
        FileMetadataStore.reset_instance()


# ---------------------------------------------------------------------------
# 2. Vision/audio extraction failures are not retried with another processor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vision_extraction_failure_is_not_retried(service, monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated vision failure")

    monkeypatch.setattr(service, "_extract_image_content", _boom)

    with pytest.raises(RuntimeError, match="simulated vision failure"):
        await service._extract_content(
            b"fake png bytes", "test.png", "image/png", api_key="test_api_key"
        )


@pytest.mark.asyncio
async def test_audio_extraction_failure_is_not_retried(service, monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated audio failure")

    monkeypatch.setattr(service, "_extract_audio_content", _boom)

    with pytest.raises(RuntimeError, match="simulated audio failure"):
        await service._extract_content(
            b"fake mp3 bytes", "test.mp3", "audio/mpeg", api_key="test_api_key"
        )


# ---------------------------------------------------------------------------
# 3. AI-OCR-priority excludes generic vision entirely, even on OCR failure
# ---------------------------------------------------------------------------

class _FailingProcessor:
    """Stand-in for AIDocumentProcessor: registered, but its extraction fails."""

    def supports_mime_type(self, mime_type: str) -> bool:
        return mime_type.startswith('image/')

    async def extract_text(self, file_data, filename=None):
        raise RuntimeError("simulated OCR failure")

    async def extract_metadata(self, file_data, filename=None):
        return {}


@pytest.mark.asyncio
async def test_ai_ocr_priority_skips_generic_vision_even_on_ocr_failure(tmp_path, monkeypatch):
    service = _build_service(tmp_path, ai_ocr_priority=True)
    try:
        assert service._ai_ocr_is_priority() is True

        vision_called = False

        async def _track_vision_call(*args, **kwargs):
            nonlocal vision_called
            vision_called = True
            return "should never reach here", {}

        monkeypatch.setattr(service, "_extract_image_content", _track_vision_call)
        monkeypatch.setattr(
            service.processor_registry, "get_processors",
            lambda mime_type: [_FailingProcessor()]
        )

        with pytest.raises(RuntimeError, match="simulated OCR failure"):
            await service._extract_content(
                b"fake png bytes", "test.png", "image/png", api_key="test_api_key"
            )

        assert vision_called is False
    finally:
        service.metadata_store.close()
        from services.file_metadata.metadata_store import FileMetadataStore
        FileMetadataStore.reset_instance()
