"""
Tests for AIDocumentProcessor.extract() — the unified extraction path added by
docs/roadmap/complete/file-processing-unified-extraction-result.md, specifically its
usage/model billing-attribution guarantee under concurrency
(docs/roadmap/complete/file-processing-unified-extraction-result.md#ai-ocr-usagemodel-attribution-under-concurrency).
"""

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.ai_document_processor import AIDocumentProcessor
from services.file_processing.file_processing_service import FileProcessingService

TEST_MIME_TYPE = "application/x-test-ai-ocr"


class _FakeService:
    """OCR service stand-in. `model` is a static attribute fixed at
    construction, exactly like the real OCR provider services (see
    ai_services/providers/*_base.py: `self.model` is set once at init, never
    mutated per call) - the no-usage call's service is a distinct instance
    from the usage-reporting call's, so a resolved-model mixup can only be
    caught if the processor captures its own service's model locally rather
    than reading shared/instance state after an await."""

    initialized = True
    SUPPORTS_USAGE_REPORTING = False

    def __init__(self, model: str, pause_event: asyncio.Event | None = None, resume_event: asyncio.Event | None = None):
        self.model = model
        self._pause_event = pause_event
        self._resume_event = resume_event

    async def extract_document(self, file_data, mime_type, filename):
        if self._pause_event is not None:
            self._pause_event.set()
            await self._resume_event.wait()
            return {"text": "no-usage result"}

        return {
            "text": "usage result",
            "media_usage": {"unit": "pages", "quantity": 7},
        }


def _build_service(tmp_path):
    from services.file_metadata.metadata_store import FileMetadataStore

    test_db_path = str(tmp_path / "test_orbit_ai_ocr_unified.db")
    config = {
        'storage_root': str(tmp_path / "uploads"),
        'chunking_strategy': 'fixed',
        'chunk_size': 100,
        'chunk_overlap': 20,
        'max_file_size': 10485760,
        'supported_types': [TEST_MIME_TYPE],
        'enable_vision': False,
        'enable_audio': False,
        'internal_services': {
            'backend': {'type': 'sqlite', 'sqlite': {'database_path': test_db_path}},
        },
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


@pytest.mark.asyncio
async def test_concurrent_extractions_through_dispatch_attribute_usage_correctly(service, monkeypatch):
    pause_event = asyncio.Event()
    resume_event = asyncio.Event()
    no_usage_service = _FakeService("model-no-usage", pause_event, resume_event)
    has_usage_service = _FakeService("model-with-usage")

    # _get_ocr_service() is called synchronously, before any await, at the
    # very start of extract() - so the no-usage call (started and run up to
    # its pause point first) always consumes the first service, and the
    # usage-reporting call (only started afterwards) always consumes the
    # second, regardless of how their awaits later interleave.
    services_by_call_order = iter([no_usage_service, has_usage_service])

    processor = AIDocumentProcessor(enabled=True)
    processor.supports_mime_type = lambda mime_type: mime_type == TEST_MIME_TYPE
    processor._get_ocr_service = lambda: next(services_by_call_order)
    processor._detect_mime_type = lambda file_data, filename: TEST_MIME_TYPE
    processor._count_pages = lambda file_data, mime_type: 1
    service.processor_registry.register(processor)

    # Capture the actual ExtractionResult per call (not just what
    # _extract_content's tuple return or the audit spy surfaces), so a wrong
    # model/provider on the no-usage result - which never reaches the audit
    # log - is still caught.
    extraction_results = {}
    real_extract = processor.extract

    async def _extract_and_record(file_data, filename=None):
        result = await real_extract(file_data, filename)
        extraction_results[filename] = result
        return result

    processor.extract = _extract_and_record

    logged_calls = []

    async def spy_log(api_key, filename, provider, model, usage, call_type):
        logged_calls.append({
            "filename": filename,
            "provider": provider,
            "model": model,
            "usage": usage,
            "call_type": call_type,
        })

    monkeypatch.setattr(service, "_log_extraction_usage", spy_log)

    # 1. Start the no-usage call first; it pauses mid-flight inside the OCR service.
    no_usage_task = asyncio.create_task(
        service._extract_content(b"no-usage", "no-usage.pdf", TEST_MIME_TYPE, api_key="test_api_key")
    )
    await pause_event.wait()

    # 2. While paused, run the usage-reporting call (different filename/model) to completion.
    text2, _metadata2, _tables2, _segments2 = await service._extract_content(
        b"has-usage", "has-usage.pdf", TEST_MIME_TYPE, api_key="test_api_key"
    )

    # 3. Only now let the paused call resume and finish.
    resume_event.set()
    text1, _metadata1, _tables1, _segments1 = await no_usage_task

    assert text1 == "no-usage result"
    assert text2 == "usage result"

    # Exactly one audit write happened, and it's for the reporting call only,
    # with that call's own filename/usage/provider/model - not the no-usage
    # call's, and not a mix of both.
    assert len(logged_calls) == 1
    logged = logged_calls[0]
    assert logged["filename"] == "has-usage.pdf"
    assert logged["usage"] == {"reported": True, "usage_unit": "pages", "usage_quantity": 7}
    assert logged["provider"] == processor.provider
    assert logged["model"] == "model-with-usage"

    # Each call's own ExtractionResult must carry its own model/provider,
    # even the no-usage one that never reaches the audit log.
    no_usage_result = extraction_results["no-usage.pdf"]
    has_usage_result = extraction_results["has-usage.pdf"]

    assert no_usage_result.usage is None
    assert no_usage_result.model == "model-no-usage"
    assert no_usage_result.provider == processor.provider

    assert has_usage_result.usage == {"reported": True, "usage_unit": "pages", "usage_quantity": 7}
    assert has_usage_result.model == "model-with-usage"
    assert has_usage_result.provider == processor.provider
