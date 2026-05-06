"""
Unit tests for file upload route validation behavior.
"""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from routes.file_routes import create_file_router
from services.file_processing.magika_detector import FileValidationError


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
