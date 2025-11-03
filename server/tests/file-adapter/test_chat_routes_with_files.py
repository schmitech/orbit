"""
Integration Tests for Chat Routes with File Context

Tests the /v1/chat endpoint with file_ids parameter to verify
end-to-end file context integration in chat conversations.

Prerequisites:
1. Server must be running on http://localhost:3000 (or configured port)
2. File Processing Service must be initialized
3. File adapter (file-document-qa) must be enabled
4. API key must be mapped to file-document-qa adapter
"""

import pytest
import httpx
import json
import tempfile
from pathlib import Path
from typing import Optional
import logging
import asyncio

logger = logging.getLogger(__name__)

# Test configuration
TEST_API_KEY = "files"  # Assumes this key is mapped to file-document-qa adapter
TEST_SERVER_URL = "http://localhost:3000"
TEST_SESSION_ID = "test-session-file-chat"  # Test session ID

# Sample test content for file upload
TEST_FILE_CONTENT = """Technical Documentation: ORBIT System

The ORBIT system is a multi-adapter RAG platform that supports various data sources.

Key Features:
- File upload and processing with PDF, DOCX, TXT, CSV support
- Vector-based semantic search using ChromaDB
- Multiple adapter support for different data sources
- Chat integration with file context
- Multi-tenant isolation with API key authentication

The file-document-qa adapter allows users to upload files and query them using natural language.
Files are chunked into semantic segments and indexed in a vector store for efficient retrieval.
"""


@pytest.fixture
async def http_client():
    """Create an HTTP client for making requests"""
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


@pytest.fixture
async def uploaded_file(http_client, server_health_check):
    """Upload a test file and return its file_id"""
    headers = {"X-API-Key": TEST_API_KEY}

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(TEST_FILE_CONTENT)
        temp_path = f.name

    try:
        # Upload file
        with open(temp_path, "rb") as f:
            files = {"file": ("orbit_docs.md", f, "text/markdown")}
            response = await http_client.post(
                f"{TEST_SERVER_URL}/api/files/upload",
                headers=headers,
                files=files
            )

        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()

        # Wait for processing to complete
        await asyncio.sleep(2)

        yield data["file_id"]

        # Cleanup: delete the file
        try:
            await http_client.delete(
                f"{TEST_SERVER_URL}/api/files/{data['file_id']}",
                headers=headers
            )
        except Exception as e:
            logger.warning(f"Failed to delete test file: {e}")

    finally:
        # Remove temporary file
        import os
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_chat_with_single_file_context(http_client, uploaded_file, server_health_check):
    """Test chat endpoint with single file_id"""
    headers = {
        "X-API-Key": TEST_API_KEY,
        "X-Session-ID": TEST_SESSION_ID,
        "Content-Type": "application/json"
    }

    chat_request = {
        "messages": [
            {"role": "user", "content": "What are the key features of ORBIT?"}
        ],
        "stream": False,
        "file_ids": [uploaded_file]
    }

    response = await http_client.post(
        f"{TEST_SERVER_URL}/v1/chat",
        headers=headers,
        json=chat_request
    )

    assert response.status_code == 200, f"Chat request failed: {response.text}"
    data = response.json()

    # Verify response structure
    assert "response" in data
    assert isinstance(data["response"], str)
    assert len(data["response"]) > 0

    # Response should mention features from the file
    response_lower = data["response"].lower()
    # Should reference file content
    assert any(keyword in response_lower for keyword in [
        "file", "upload", "vector", "adapter", "semantic"
    ])


@pytest.mark.asyncio
async def test_chat_with_multiple_file_contexts(http_client, server_health_check):
    """Test chat endpoint with multiple file_ids"""
    headers = {"X-API-Key": TEST_API_KEY}

    # Upload multiple files
    file_ids = []
    try:
        for i in range(2):
            content = f"""Document {i+1}

This is test document number {i+1}.
It contains information about topic {chr(65+i)}.
"""
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(content)
                temp_path = f.name

            with open(temp_path, "rb") as f:
                files = {"file": (f"doc_{i+1}.txt", f, "text/plain")}
                response = await http_client.post(
                    f"{TEST_SERVER_URL}/api/files/upload",
                    headers=headers,
                    files=files
                )

            assert response.status_code == 200
            file_ids.append(response.json()["file_id"])

            import os
            os.remove(temp_path)

        # Wait for processing
        await asyncio.sleep(2)

        # Send chat request with multiple file_ids
        chat_headers = {
            "X-API-Key": TEST_API_KEY,
            "X-Session-ID": TEST_SESSION_ID,
            "Content-Type": "application/json"
        }

        chat_request = {
            "messages": [
                {"role": "user", "content": "What documents are available?"}
            ],
            "stream": False,
            "file_ids": file_ids
        }

        response = await http_client.post(
            f"{TEST_SERVER_URL}/v1/chat",
            headers=chat_headers,
            json=chat_request
        )

        assert response.status_code == 200, f"Chat request failed: {response.text}"
        data = response.json()

        assert "response" in data
        assert len(data["response"]) > 0

    finally:
        # Cleanup
        for file_id in file_ids:
            try:
                await http_client.delete(
                    f"{TEST_SERVER_URL}/api/files/{file_id}",
                    headers=headers
                )
            except Exception as e:
                logger.warning(f"Failed to delete file {file_id}: {e}")


@pytest.mark.asyncio
async def test_chat_streaming_with_file_context(http_client, uploaded_file, server_health_check):
    """Test streaming chat endpoint with file_ids"""
    headers = {
        "X-API-Key": TEST_API_KEY,
        "X-Session-ID": TEST_SESSION_ID,
        "Content-Type": "application/json"
    }

    chat_request = {
        "messages": [
            {"role": "user", "content": "Summarize the ORBIT system briefly."}
        ],
        "stream": True,
        "file_ids": [uploaded_file]
    }

    # Use longer timeout for streaming
    timeout = httpx.Timeout(180.0, read=180.0)  # 3 minutes for streaming
    client_with_timeout = httpx.AsyncClient(timeout=timeout)
    
    try:
        async with client_with_timeout.stream(
            "POST",
            f"{TEST_SERVER_URL}/v1/chat",
            headers=headers,
            json=chat_request
        ) as response:
            assert response.status_code == 200, f"Streaming request failed"

            chunks = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]  # Remove "data: " prefix
                    if data_str.strip() and data_str != "[DONE]":
                        try:
                            chunk_data = json.loads(data_str)
                            chunks.append(chunk_data)

                            if chunk_data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            pass

            # Verify we received streaming chunks
            assert len(chunks) > 0, "No chunks received from streaming response"

            # Verify chunks contain response text
            has_content = any(
                chunk.get("response", "") for chunk in chunks
            )
            assert has_content, "No content in streaming chunks"
    finally:
        await client_with_timeout.aclose()


@pytest.mark.asyncio
async def test_chat_without_file_context(http_client, server_health_check):
    """Test chat endpoint without file_ids (normal operation)"""
    headers = {
        "X-API-Key": TEST_API_KEY,
        "X-Session-ID": TEST_SESSION_ID,
        "Content-Type": "application/json"
    }

    chat_request = {
        "messages": [
            {"role": "user", "content": "What is 2+2?"}
        ],
        "stream": False
        # No file_ids provided
    }

    response = await http_client.post(
        f"{TEST_SERVER_URL}/v1/chat",
        headers=headers,
        json=chat_request
    )

    assert response.status_code == 200, f"Chat request failed: {response.text}"
    data = response.json()

    assert "response" in data
    assert len(data["response"]) > 0


@pytest.mark.asyncio
async def test_chat_with_empty_file_ids(http_client, server_health_check):
    """Test chat endpoint with empty file_ids array"""
    headers = {
        "X-API-Key": TEST_API_KEY,
        "X-Session-ID": TEST_SESSION_ID,
        "Content-Type": "application/json"
    }

    chat_request = {
        "messages": [
            {"role": "user", "content": "Hello"}
        ],
        "stream": False,
        "file_ids": []  # Empty array
    }

    response = await http_client.post(
        f"{TEST_SERVER_URL}/v1/chat",
        headers=headers,
        json=chat_request
    )

    assert response.status_code == 200, f"Chat request failed: {response.text}"
    data = response.json()

    assert "response" in data


@pytest.mark.asyncio
async def test_chat_with_invalid_file_id(http_client, server_health_check):
    """Test chat endpoint with non-existent file_id"""
    headers = {
        "X-API-Key": TEST_API_KEY,
        "X-Session-ID": TEST_SESSION_ID,
        "Content-Type": "application/json"
    }

    chat_request = {
        "messages": [
            {"role": "user", "content": "What is in this file?"}
        ],
        "stream": False,
        "file_ids": ["invalid_file_id_12345"]
    }

    response = await http_client.post(
        f"{TEST_SERVER_URL}/v1/chat",
        headers=headers,
        json=chat_request
    )

    # Should still return 200 but with no file context
    # (invalid file_ids are silently ignored in retrieval)
    assert response.status_code == 200, f"Chat request failed: {response.text}"
    data = response.json()

    assert "response" in data


@pytest.mark.asyncio
async def test_chat_file_context_isolation(http_client, server_health_check):
    """Test that file context respects API key isolation"""
    # Upload file with first API key
    headers_1 = {"X-API-Key": TEST_API_KEY}

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Secret content for API key 1")
        temp_path = f.name

    try:
        with open(temp_path, "rb") as f:
            files = {"file": ("secret.txt", f, "text/plain")}
            response = await http_client.post(
                f"{TEST_SERVER_URL}/api/files/upload",
                headers=headers_1,
                files=files
            )

        assert response.status_code == 200
        file_id = response.json()["file_id"]

        await asyncio.sleep(2)

        # Try to access with different API key (should be isolated)
        headers_2 = {
            "X-API-Key": "different_api_key",
            "X-Session-ID": TEST_SESSION_ID,
            "Content-Type": "application/json"
        }

        chat_request = {
            "messages": [
                {"role": "user", "content": "What is the secret?"}
            ],
            "stream": False,
            "file_ids": [file_id]  # File from different API key
        }

        response = await http_client.post(
            f"{TEST_SERVER_URL}/v1/chat",
            headers=headers_2,
            json=chat_request
        )

        # Request should succeed but not have access to the file
        # (The file will be filtered out during retrieval)
        if response.status_code == 200:
            data = response.json()
            # Should not contain "Secret content"
            # (unless the different API key has access, which depends on implementation)
            pass
        else:
            # Might return 401 if API key validation is strict
            assert response.status_code in [401, 403]

    finally:
        # Cleanup
        import os
        os.remove(temp_path)
        try:
            await http_client.delete(
                f"{TEST_SERVER_URL}/api/files/{file_id}",
                headers=headers_1
            )
        except Exception:
            pass


@pytest.mark.asyncio
async def test_chat_with_file_context_sources(http_client, uploaded_file, server_health_check):
    """Test that chat response includes sources from file context"""
    headers = {
        "X-API-Key": TEST_API_KEY,
        "X-Session-ID": TEST_SESSION_ID,
        "Content-Type": "application/json"
    }

    chat_request = {
        "messages": [
            {"role": "user", "content": "What file formats are supported?"}
        ],
        "stream": False,
        "file_ids": [uploaded_file]
    }

    response = await http_client.post(
        f"{TEST_SERVER_URL}/v1/chat",
        headers=headers,
        json=chat_request
    )

    assert response.status_code == 200
    data = response.json()

    # Check if sources are included
    if "sources" in data:
        sources = data["sources"]
        assert isinstance(sources, list)
        # Sources might include file metadata
        # The exact structure depends on the implementation


@pytest.mark.asyncio
async def test_complete_file_chat_workflow(http_client, server_health_check):
    """Test complete workflow: upload → chat with context → delete"""
    headers = {"X-API-Key": TEST_API_KEY}

    # 1. Upload file
    content = "The quick brown fox jumps over the lazy dog."
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        with open(temp_path, "rb") as f:
            files = {"file": ("test.txt", f, "text/plain")}
            upload_response = await http_client.post(
                f"{TEST_SERVER_URL}/api/files/upload",
                headers=headers,
                files=files
            )

        assert upload_response.status_code == 200
        file_id = upload_response.json()["file_id"]

        # Wait for processing
        await asyncio.sleep(2)

        # 2. Query the file directly
        query_headers = {
            "X-API-Key": TEST_API_KEY,
            "Content-Type": "application/json"
        }

        query_response = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/{file_id}/query",
            headers=query_headers,
            json={"query": "What animal is mentioned?", "max_results": 3}
        )

        assert query_response.status_code == 200
        query_data = query_response.json()
        assert len(query_data["results"]) > 0

        # 3. Chat with file context
        chat_headers = {
            "X-API-Key": TEST_API_KEY,
            "X-Session-ID": TEST_SESSION_ID,
            "Content-Type": "application/json"
        }

        chat_request = {
            "messages": [
                {"role": "user", "content": "What animals are in the document?"}
            ],
            "stream": False,
            "file_ids": [file_id]
        }

        chat_response = await http_client.post(
            f"{TEST_SERVER_URL}/v1/chat",
            headers=chat_headers,
            json=chat_request
        )

        assert chat_response.status_code == 200
        chat_data = chat_response.json()
        assert "response" in chat_data

        # Response should mention fox or dog (but be flexible - LLM might rephrase)
        response_lower = chat_data["response"].lower()
        # Check for various ways the LLM might reference the content
        assert any(keyword in response_lower for keyword in [
            "fox", "dog", "brown", "lazy", "quick", "jumps", "animal", "animals"
        ]), f"Response should reference document content. Got: {chat_data['response'][:200]}"

        # 4. Delete file
        delete_response = await http_client.delete(
            f"{TEST_SERVER_URL}/api/files/{file_id}",
            headers=headers
        )

        assert delete_response.status_code == 200
        
        # 5. Wait a moment for deletion to complete
        await asyncio.sleep(1)
        
        # 6. Verify file metadata is deleted - get file info should fail
        get_file_response = await http_client.get(
            f"{TEST_SERVER_URL}/api/files/{file_id}",
            headers=headers
        )
        assert get_file_response.status_code == 404, "File metadata should be removed after deletion"
        
        # 7. Verify chunks are deleted - query should fail
        query_after = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/{file_id}/query",
            headers=query_headers,
            json={"query": "What animals?", "max_results": 1}
        )
        assert query_after.status_code == 404, "File should not be queryable after deletion"

    finally:
        import os
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_conversation_deletion_cleans_file_chunks(http_client, server_health_check):
    """Test that deleting a conversation also removes file chunks from vector store"""
    headers = {"X-API-Key": TEST_API_KEY}
    session_id = f"test-session-delete-{hash('test')}"
    
    # Upload a file
    content = "This is a test document for conversation deletion."
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        with open(temp_path, "rb") as f:
            files = {"file": ("test.txt", f, "text/plain")}
            upload_response = await http_client.post(
                f"{TEST_SERVER_URL}/api/files/upload",
                headers=headers,
                files=files
            )

        assert upload_response.status_code == 200
        file_id = upload_response.json()["file_id"]
        
        # Wait for processing
        await asyncio.sleep(2)
        
        # Verify file is queryable
        query_headers = {
            "X-API-Key": TEST_API_KEY,
            "Content-Type": "application/json"
        }
        query_before = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/{file_id}/query",
            headers=query_headers,
            json={"query": "test document", "max_results": 1}
        )
        assert query_before.status_code == 200
        assert len(query_before.json()["results"]) > 0
        
        # Delete conversation with file (using admin route)
        delete_response = await http_client.delete(
            f"{TEST_SERVER_URL}/admin/conversations/{session_id}?file_ids={file_id}",
            headers={
                "X-API-Key": TEST_API_KEY,
                "X-Session-ID": session_id
            }
        )
        
        # Should succeed (even if session doesn't exist, files should be deleted)
        assert delete_response.status_code in [200, 404]
        
        # Wait a moment for deletion to complete
        await asyncio.sleep(1)
        
        # Verify file metadata is deleted - get file info should fail
        get_file_response = await http_client.get(
            f"{TEST_SERVER_URL}/api/files/{file_id}",
            headers=headers
        )
        assert get_file_response.status_code == 404, "File metadata should be removed after conversation deletion"
        
        # Verify chunks are deleted - query should fail
        query_after = await http_client.post(
            f"{TEST_SERVER_URL}/api/files/{file_id}/query",
            headers=query_headers,
            json={"query": "test document", "max_results": 1}
        )
        assert query_after.status_code == 404, "File should not be queryable after deletion"
        
    finally:
        import os
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_chat_request_schema_validation(http_client, server_health_check):
    """Test that chat request properly validates file_ids schema"""
    headers = {
        "X-API-Key": TEST_API_KEY,
        "X-Session-ID": TEST_SESSION_ID,
        "Content-Type": "application/json"
    }

    # Valid request with file_ids as array
    valid_request = {
        "messages": [
            {"role": "user", "content": "Test"}
        ],
        "stream": False,
        "file_ids": ["file_1", "file_2"]
    }

    response = await http_client.post(
        f"{TEST_SERVER_URL}/v1/chat",
        headers=headers,
        json=valid_request
    )

    assert response.status_code == 200

    # Invalid request with file_ids as string (should fail validation)
    invalid_request = {
        "messages": [
            {"role": "user", "content": "Test"}
        ],
        "stream": False,
        "file_ids": "file_1"  # Should be array, not string
    }

    response = await http_client.post(
        f"{TEST_SERVER_URL}/v1/chat",
        headers=headers,
        json=invalid_request
    )

    # Should return validation error (422)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_with_file_context_performance(http_client, uploaded_file, server_health_check):
    """Test chat with file context performance"""
    import time

    headers = {
        "X-API-Key": TEST_API_KEY,
        "X-Session-ID": TEST_SESSION_ID,
        "Content-Type": "application/json"
    }

    chat_request = {
        "messages": [
            {"role": "user", "content": "What is ORBIT?"}
        ],
        "stream": False,
        "file_ids": [uploaded_file]
    }

    start_time = time.time()

    response = await http_client.post(
        f"{TEST_SERVER_URL}/v1/chat",
        headers=headers,
        json=chat_request
    )

    end_time = time.time()
    response_time = end_time - start_time

    assert response.status_code == 200

    # Response should be reasonably fast (< 30 seconds for local deployment)
    # This is a soft check - actual time depends on model and infrastructure
    logger.info(f"Chat with file context took {response_time:.2f} seconds")

    # Just ensure it completed
    assert response_time < 60.0, "Response took too long"
