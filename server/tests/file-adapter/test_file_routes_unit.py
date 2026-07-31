"""
Unit tests for file upload route validation behavior.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from routes.file_routes import create_file_router
from services.file_processing.magika_detector import FileValidationError
from services.pricing_service import PricingService


class DummyProcessingService:
    def __init__(self, inspect_result=None, inspect_error=None):
        self.inspect_result = inspect_result
        self.inspect_error = inspect_error
        self.received_mime_type = None

    def inspect_upload(self, *, file_data, filename, claimed_mime_type):
        if self.inspect_error:
            raise self.inspect_error
        return self.inspect_result or claimed_mime_type

    async def process_file(self, *, file_data, filename, mime_type, api_key):
        self.received_mime_type = mime_type
        return {
            "file_id": "file-123",
            "filename": filename,
            "mime_type": mime_type,
            "file_size": len(file_data),
            "status": "completed",
            "chunk_count": 1,
        }

    async def quick_upload(self, *, file_data, filename, mime_type, api_key):
        self.received_mime_type = mime_type
        return "file-123"

    async def process_file_content(self, **_kwargs):
        return None


def create_test_client(service: DummyProcessingService) -> TestClient:
    app = FastAPI()
    app.include_router(create_file_router())
    app.state.file_processing_service = service
    return TestClient(app)


def test_upload_rejects_validation_error():
    service = DummyProcessingService(
        inspect_error=FileValidationError(
            "Uploaded file content does not match the declared file type"
        )
    )
    client = create_test_client(service)

    response = client.post(
        "/api/files/upload",
        headers={"X-API-Key": "files"},
        files={"file": ("test.txt", b"not text", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Uploaded file content does not match the declared file type"


def test_upload_uses_verified_mime_type():
    service = DummyProcessingService(inspect_result="text/markdown")
    client = create_test_client(service)

    response = client.post(
        "/api/files/upload",
        headers={"X-API-Key": "files"},
        files={"file": ("test.md", b"# heading\n", "application/octet-stream")},
    )

    assert response.status_code == 200
    assert response.json()["mime_type"] == "text/markdown"
    assert service.received_mime_type == "text/markdown"


def test_file_query_audits_embedding_usage(monkeypatch):
    service = DummyProcessingService()
    service.metadata_store = SimpleNamespace(
        get_file_info=AsyncMock(return_value={
            "api_key": "files",
            "collection_name": "collection-1",
            "filename": "notes.txt",
        })
    )
    service._get_adapter_config_for_api_key = AsyncMock(return_value={})

    async def get_relevant_context(**kwargs):
        kwargs["usage_sink"].update({
            "prompt_tokens": 500,
            "completion_tokens": 0,
            "total_tokens": 500,
            "provider": "openai",
            "model": "text-embedding-3-small",
            "reported": True,
        })
        return []

    retriever = SimpleNamespace(get_relevant_context=get_relevant_context)
    cache = SimpleNamespace(get_retriever=AsyncMock(return_value=retriever))
    monkeypatch.setattr(
        "services.retriever_cache.get_retriever_cache", lambda: cache
    )

    audit_service = AsyncMock()
    app = FastAPI()
    app.include_router(create_file_router())
    app.state.file_processing_service = service
    app.state.audit_service = audit_service
    app.state.pricing_service = PricingService({
        "pricing": {
            "providers": {
                "openai": {
                    "text-embedding-3-small": {
                        "input_per_1m": 0.02,
                        "output_per_1m": 0.0,
                    }
                }
            }
        }
    })
    client = TestClient(app)

    response = client.post(
        "/api/files/file-1/query",
        headers={"X-API-Key": "files"},
        json={"query": "find notes"},
    )

    assert response.status_code == 200
    usage = audit_service.log_conversation.call_args.kwargs["usage"]
    assert usage["embedding_prompt_tokens"] == 500
    assert usage["embedding_cost_usd"] == 0.00001
    assert audit_service.log_conversation.call_args.kwargs["adapter_name"] == "file-query"
