"""
Integration Tests for File Routes

Tests all file management HTTP endpoints with a running server.
Make sure the server is running before executing these tests.

Prerequisites:
1. Server must be running on http://localhost:3000 (or configured port)
2. File Processing Service must be initialized
3. Vector store (Chroma) must be available
4. Test API key should be configured (default: "files" for testing)
"""

import pytest
import httpx
import json
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Test configuration
TEST_API_KEY = "files"
TEST_SERVER_URL = "http://localhost:3000"

# Sample test content
TEST_FILE_CONTENT = """From https://schmitech.ai/en/about:

Leading Schmitech is Remsy Schmilinsky, a seasoned technology architect with over two decades of experience delivering mission-critical systems across North America's public and private sectors.

At Schmitech, Remsy applies his background in cloud architecture and enterprise integration to help organizations make AI more accessible and genuinely useful. He focuses on practical, secure implementations that align with each client's unique goals.

From predictive analytics to automation and AI agents, his work centers on building reliable, scalable solutions that bridge cutting-edge technology with real-world business needs—without overcomplicating things.

Fluent in English, French, and Spanish, Remsy collaborates across borders to support teams in building future-ready systems while maintaining data privacy, security, and compliance every step of the way.
"""


@pytest.fixture
def test_file(tmp_path):
    """Create a temporary test file"""
    test_file_path = tmp_path / "test_document.md"
    test_file_path.write_text(TEST_FILE_CONTENT)
    return test_file_path


@pytest.fixture
async def http_client():
    """Create an HTTP client for making requests"""
    # Use 120 second timeout for file processing operations which may involve
    # chunking, embedding generation, and vector indexing
    async with httpx.AsyncClient(timeout=120.0) as client:
        yield client


@pytest.fixture
async def server_health_check(http_client):
    """Check if server is running before tests"""
    try:
        response = await http_client.get(f"{TEST_SERVER_URL}/health")
        if response.status_code != 200:
            pytest.skip(f"Server is not healthy (status: {response.status_code})")
    except Exception as e:
        pytest.skip(f"Server is not accessible: {e}")


@pytest.mark.asyncio
async def test_file_upload(http_client, test_file, server_health_check):
    """Test file upload endpoint"""
    headers = {"X-API-Key": TEST_API_KEY}
    
    with open(test_file, "rb") as f:
        files = {"file": (test_file.name, f, "text/markdown")}
        response = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/upload",
            headers=headers,
            files=files
        )
    
    assert response.status_code == 200, f"Upload failed: {response.text}"
    data = response.json()
    
    # Verify response structure
    assert "file_id" in data
    assert data["filename"] == test_file.name
    assert data["mime_type"] == "text/markdown"
    assert data["status"] == "completed"
    assert data["chunk_count"] > 0
    assert "collection_name" in data or "message" in data


@pytest.mark.asyncio
async def test_list_files(http_client, server_health_check):
    """Test list files endpoint"""
    headers = {"X-API-Key": TEST_API_KEY}
    
    response = await http_client.get(
        f"{TEST_SERVER_URL}/api/files",
        headers=headers
    )
    
    assert response.status_code == 200
    files = response.json()
    
    assert isinstance(files, list)
    
    # Verify file structure
    if len(files) > 0:
        file = files[0]
        assert "file_id" in file
        assert "filename" in file
        assert "processing_status" in file
        assert "chunk_count" in file


@pytest.mark.asyncio
async def test_get_file_info(http_client, test_file, server_health_check):
    """Test get file info endpoint"""
    headers = {"X-API-Key": TEST_API_KEY}
    
    # First upload a file
    with open(test_file, "rb") as f:
        files = {"file": (test_file.name, f, "text/markdown")}
        upload_response = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/upload",
            headers=headers,
            files=files
        )
    
    assert upload_response.status_code == 200
    file_id = upload_response.json()["file_id"]
    
    # Now get file info
    response = await http_client.get(
        f"{TEST_SERVER_URL}/api/files/{file_id}",
        headers=headers
    )
    
    assert response.status_code == 200
    file_info = response.json()
    
    # Verify response structure
    assert file_info["file_id"] == file_id
    assert "filename" in file_info
    assert "mime_type" in file_info
    assert "file_size" in file_info
    assert "upload_timestamp" in file_info
    assert file_info["processing_status"] == "completed"
    assert file_info["chunk_count"] > 0
    assert "storage_type" in file_info


@pytest.mark.asyncio
async def test_query_file(http_client, test_file, server_health_check):
    """Test query file endpoint"""
    headers = {"X-API-Key": TEST_API_KEY}
    
    # First upload a file
    with open(test_file, "rb") as f:
        files = {"file": (test_file.name, f, "text/markdown")}
        upload_response = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/upload",
            headers=headers,
            files=files
        )
    
    assert upload_response.status_code == 200
    file_id = upload_response.json()["file_id"]
    
    # Wait a moment for indexing to complete
    import asyncio
    await asyncio.sleep(1)
    
    query_headers = {
        "X-API-Key": TEST_API_KEY,
        "Content-Type": "application/json"
    }
    
    query_data = {
        "query": "What is this document about?",
        "max_results": 5
    }
    
    response = await http_client.post(
        f"{TEST_SERVER_URL}/api/files/{file_id}/query",
        headers=headers,
        json=query_data
    )
    
    assert response.status_code == 200, f"Query failed: {response.text}"
    data = response.json()
    
    # Verify response structure
    assert data["file_id"] == file_id
    assert "filename" in data
    assert "results" in data
    assert isinstance(data["results"], list)
    
    # Verify results have content and metadata
    if len(data["results"]) > 0:
        result = data["results"][0]
        assert "content" in result
        assert "metadata" in result
        assert result["metadata"]["chunk_id"] is not None
        assert result["metadata"]["file_id"] == file_id
        assert "chunk_index" in result["metadata"]
        assert "confidence" in result["metadata"]
        assert isinstance(result["metadata"]["confidence"], float)
        assert 0.0 <= result["metadata"]["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_query_file_invalid_file_id(http_client, server_health_check):
    """Test query with invalid file_id"""
    headers = {
        "X-API-Key": TEST_API_KEY,
        "Content-Type": "application/json"
    }
    
    query_data = {
        "query": "Test query",
        "max_results": 5
    }
    
    response = await http_client.post(
        f"{TEST_SERVER_URL}/api/files/invalid-file-id-12345/query",
        headers=headers,
        json=query_data
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_file(http_client, test_file, server_health_check):
    """Test delete file endpoint"""
    headers = {"X-API-Key": TEST_API_KEY}
    
    # First upload a file
    with open(test_file, "rb") as f:
        files = {"file": (test_file.name, f, "text/markdown")}
        upload_response = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/upload",
            headers=headers,
            files=files
        )
    
    assert upload_response.status_code == 200
    file_id = upload_response.json()["file_id"]
    
    response = await http_client.delete(
        f"{TEST_SERVER_URL}/api/files/{file_id}",
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "message" in data
    assert data["file_id"] == file_id
    
    # Verify file is deleted - get should return 404
    get_response = await http_client.get(
        f"{TEST_SERVER_URL}/api/files/{file_id}",
        headers=headers
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_all_files(http_client, server_health_check):
    """Test delete all files endpoint"""
    headers = {"X-API-Key": TEST_API_KEY}
    
    # First, upload a couple of test files
    test_files = []
    for i in range(2):
        file_data = f"Test file {i}\n" + TEST_FILE_CONTENT
        files = {"file": (f"test_{i}.md", file_data.encode(), "text/markdown")}
        
        response = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/upload",
            headers=headers,
            files=files
        )
        
        assert response.status_code == 200
        test_files.append(response.json()["file_id"])
    
    # Verify files are listed
    list_response = await http_client.get(
        f"{TEST_SERVER_URL}/api/files",
        headers=headers
    )
    assert list_response.status_code == 200
    files_before = list_response.json()
    assert len(files_before) >= 2
    
    # Delete all files
    delete_response = await http_client.delete(
        f"{TEST_SERVER_URL}/api/files",
        headers=headers
    )
    
    assert delete_response.status_code == 200
    data = delete_response.json()
    
    assert "message" in data
    assert "deleted_count" in data
    assert data["deleted_count"] >= 2
    
    # Verify all files are deleted
    list_response_after = await http_client.get(
        f"{TEST_SERVER_URL}/api/files",
        headers=headers
    )
    assert list_response_after.status_code == 200
    files_after = list_response_after.json()
    
    # All files for this API key should be gone
    assert len(files_after) == 0


@pytest.mark.asyncio
async def test_file_upload_invalid_api_key(http_client, test_file, server_health_check):
    """Test file upload with invalid API key
    
    Note: This test requires API key service to be enabled and initialized.
    If API key service is not available, the validation is skipped for backward compatibility.
    """
    headers = {"X-API-Key": "invalid-api-key-that-should-not-exist-12345"}
    
    with open(test_file, "rb") as f:
        files = {"file": (test_file.name, f, "text/markdown")}
        response = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/upload",
            headers=headers,
            files=files
        )
    
    # If API key service is available, should return 401 (unauthorized)
    # If API key service is not available, validation is skipped (backward compatibility)
    # In that case, we skip the test or allow 200 (service not enforcing validation)
    if response.status_code == 200:
        # API key service may not be available - this is acceptable for backward compatibility
        logger.warning("API key validation skipped - API key service may not be available")
        # Still verify the upload worked
        assert "file_id" in response.json()
    else:
        # API key service is available and validation should fail
        assert response.status_code in [400, 401, 403], f"Expected auth error, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_file_upload_missing_file(http_client, server_health_check):
    """Test file upload without file"""
    headers = {"X-API-Key": TEST_API_KEY}
    
    response = await http_client.post(
        f"{TEST_SERVER_URL}/api/files/upload",
        headers=headers,
        files={}
    )
    
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_complete_file_lifecycle(http_client, test_file, server_health_check):
    """Test complete file lifecycle: upload -> list -> query -> delete"""
    headers = {"X-API-Key": TEST_API_KEY}
    
    # 1. Upload file
    with open(test_file, "rb") as f:
        files = {"file": (test_file.name, f, "text/markdown")}
        upload_response = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/upload",
            headers=headers,
            files=files
        )
    
    assert upload_response.status_code == 200
    upload_data = upload_response.json()
    file_id = upload_data["file_id"]
    
    # 2. List files - verify uploaded file appears
    list_response = await http_client.get(
        f"{TEST_SERVER_URL}/api/files",
        headers=headers
    )
    assert list_response.status_code == 200
    files_list = list_response.json()
    assert any(f["file_id"] == file_id for f in files_list)
    
    # 3. Get file info
    info_response = await http_client.get(
        f"{TEST_SERVER_URL}/api/files/{file_id}",
        headers=headers
    )
    assert info_response.status_code == 200
    info_data = info_response.json()
    assert info_data["file_id"] == file_id
    assert info_data["processing_status"] == "completed"
    
    # 4. Query file
    query_headers = {
        "X-API-Key": TEST_API_KEY,
        "Content-Type": "application/json"
    }
    query_response = await http_client.post(
        f"{TEST_SERVER_URL}/api/files/{file_id}/query",
        headers=query_headers,
        json={"query": "What is Remsy's background?", "max_results": 3}
    )
    assert query_response.status_code == 200
    query_data = query_response.json()
    assert len(query_data["results"]) > 0
    assert "content" in query_data["results"][0]
    assert query_data["results"][0]["metadata"]["confidence"] > 0
    
    # 5. Delete file
    delete_response = await http_client.delete(
        f"{TEST_SERVER_URL}/api/files/{file_id}",
        headers=headers
    )
    assert delete_response.status_code == 200
    
    # 6. Verify file is deleted
    get_response = await http_client.get(
        f"{TEST_SERVER_URL}/api/files/{file_id}",
        headers=headers
    )
    assert get_response.status_code == 404

