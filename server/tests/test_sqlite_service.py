"""
Test SQLite Service
===================

This script tests the SQLite service implementation to ensure it provides
the same functionality as the MongoDB service.

Prerequisites:
1. No external dependencies required (SQLite is built-in)
2. Tests create temporary database files
3. Automatic cleanup after tests
"""

import asyncio
import os
import sys
import pytest
from pathlib import Path
from pytest_asyncio import fixture
from datetime import datetime, UTC
import tempfile
import shutil

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

from services.sqlite_service import SQLiteService
from utils.id_utils import generate_id

# Test collection name
TEST_COLLECTION = "test_users"
TEST_COLLECTION_POSTS = "test_posts"


@fixture(scope="function")
async def sqlite_service():
    """Fixture to create and cleanup SQLite service"""
    # Create temporary directory for test database
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_orbit.db")

    # Create SQLite configuration
    sqlite_config = {
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': db_path
                }
            }
        },
        'general': {
            'verbose': False
        }
    }

    # Initialize SQLite service
    service = SQLiteService(sqlite_config)

    try:
        await service.initialize()
    except Exception as e:
        pytest.fail(f"Failed to initialize SQLite: {e}")

    # Yield the service for use in tests
    yield service

    # Cleanup: Close connection and remove temp directory
    service.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_initialization(sqlite_service: SQLiteService):
    """Test SQLite service initialization"""
    assert sqlite_service._initialized is True
    assert sqlite_service.connection is not None


@pytest.mark.asyncio
async def test_insert_and_find_one(sqlite_service: SQLiteService):
    """Test inserting and finding a single document"""
    # Create test document
    test_doc = {
        "name": "Test User",
        "email": "test@example.com",
        "age": 30,
        "created_at": datetime.now(UTC)
    }

    # Insert document
    inserted_id = await sqlite_service.insert_one(TEST_COLLECTION, test_doc)
    assert inserted_id is not None
    assert isinstance(inserted_id, str)  # UUID string

    # Find the document by ID
    found_doc = await sqlite_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert found_doc is not None
    assert found_doc["name"] == test_doc["name"]
    assert found_doc["email"] == test_doc["email"]
    assert found_doc["age"] == test_doc["age"]


@pytest.mark.asyncio
async def test_find_many(sqlite_service: SQLiteService):
    """Test finding multiple documents"""
    # Insert multiple documents
    docs = [
        {"name": f"User {i}", "age": 20 + i, "category": "test"}
        for i in range(5)
    ]

    for doc in docs:
        await sqlite_service.insert_one(TEST_COLLECTION, doc)

    # Find all documents with category "test"
    found_docs = await sqlite_service.find_many(TEST_COLLECTION, {"category": "test"})
    assert len(found_docs) >= 5

    # Test with limit
    limited_docs = await sqlite_service.find_many(TEST_COLLECTION, {"category": "test"}, limit=3)
    assert len(limited_docs) == 3

    # Test with sorting
    sorted_docs = await sqlite_service.find_many(
        TEST_COLLECTION,
        {"category": "test"},
        sort=[("age", -1)]  # Sort by age descending
    )
    # Verify sorting (ages should be in descending order)
    assert sorted_docs[0]["age"] >= sorted_docs[1]["age"]


@pytest.mark.asyncio
async def test_update_one(sqlite_service: SQLiteService):
    """Test updating a document"""
    # Insert a document
    original_doc = {
        "name": "Update Test",
        "status": "active",
        "score": 100
    }
    inserted_id = await sqlite_service.insert_one(TEST_COLLECTION, original_doc)

    # Update the document
    update_result = await sqlite_service.update_one(
        TEST_COLLECTION,
        {"_id": inserted_id},
        {"$set": {"status": "inactive", "score": 150}}
    )
    assert update_result is True

    # Verify the update
    updated_doc = await sqlite_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert updated_doc["status"] == "inactive"
    assert updated_doc["score"] == 150
    assert updated_doc["name"] == "Update Test"  # Unchanged field


@pytest.mark.asyncio
async def test_delete_one(sqlite_service: SQLiteService):
    """Test deleting a document"""
    # Insert a document
    doc = {"name": "To Be Deleted", "temporary": True}
    inserted_id = await sqlite_service.insert_one(TEST_COLLECTION, doc)

    # Verify it exists
    found = await sqlite_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert found is not None

    # Delete the document
    delete_result = await sqlite_service.delete_one(TEST_COLLECTION, {"_id": inserted_id})
    assert delete_result is True

    # Verify it's deleted
    not_found = await sqlite_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert not_found is None


@pytest.mark.asyncio
async def test_delete_many(sqlite_service: SQLiteService):
    """Test deleting multiple documents"""
    # Insert multiple documents
    docs = [
        {"name": f"Delete Test {i}", "category": "to_delete"}
        for i in range(5)
    ]

    for doc in docs:
        await sqlite_service.insert_one(TEST_COLLECTION, doc)

    # Delete all documents with category "to_delete"
    deleted_count = await sqlite_service.delete_many(TEST_COLLECTION, {"category": "to_delete"})
    assert deleted_count >= 5

    # Verify they're deleted
    remaining = await sqlite_service.find_many(TEST_COLLECTION, {"category": "to_delete"})
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_create_index(sqlite_service: SQLiteService):
    """Test creating indexes"""
    # Create a unique index on email
    index_name = await sqlite_service.create_index(
        TEST_COLLECTION,
        "email",
        unique=True
    )
    assert isinstance(index_name, str)

    # Test unique constraint by trying to insert duplicate emails
    doc1 = {"name": "User 1", "email": "unique@example.com"}
    await sqlite_service.insert_one(TEST_COLLECTION, doc1)

    doc2 = {"name": "User 2", "email": "unique@example.com"}
    # This should fail due to unique constraint
    try:
        result = await sqlite_service.insert_one(TEST_COLLECTION, doc2)
        assert False, "Should have raised an exception for duplicate email"
    except Exception as e:
        # Expected behavior - unique constraint error
        assert "UNIQUE constraint" in str(e) or result is None

    # Create compound index
    compound_index = await sqlite_service.create_index(
        TEST_COLLECTION,
        [("category", 1), ("created_at", -1)]
    )
    assert isinstance(compound_index, str)


@pytest.mark.asyncio
async def test_ensure_id_is_object_id(sqlite_service: SQLiteService):
    """Test ID conversion for SQLite (UUID strings)"""
    # Test with UUID string
    import uuid
    string_id = str(uuid.uuid4())
    result_id = await sqlite_service.ensure_id_is_object_id(string_id)
    assert isinstance(result_id, str)
    assert result_id == string_id

    # Test with existing UUID
    existing_uuid = str(uuid.uuid4())
    result = await sqlite_service.ensure_id_is_object_id(existing_uuid)
    assert result == existing_uuid


@pytest.mark.asyncio
async def test_get_collection(sqlite_service: SQLiteService):
    """Test getting a collection"""
    collection = sqlite_service.get_collection(TEST_COLLECTION)
    assert collection is not None
    assert collection == TEST_COLLECTION

    # Getting the same collection again should return same name
    collection2 = sqlite_service.get_collection(TEST_COLLECTION)
    assert collection == collection2


@pytest.mark.asyncio
async def test_skip_and_pagination(sqlite_service: SQLiteService):
    """Test skip functionality for pagination"""
    # Insert 10 documents
    for i in range(10):
        await sqlite_service.insert_one(
            TEST_COLLECTION_POSTS,
            {"title": f"Post {i}", "order": i}
        )

    # Get first page (items 0-4)
    page1 = await sqlite_service.find_many(
        TEST_COLLECTION_POSTS,
        {},
        limit=5,
        skip=0,
        sort=[("order", 1)]
    )
    assert len(page1) == 5
    assert page1[0]["title"] == "Post 0"
    assert page1[4]["title"] == "Post 4"

    # Get second page (items 5-9)
    page2 = await sqlite_service.find_many(
        TEST_COLLECTION_POSTS,
        {},
        limit=5,
        skip=5,
        sort=[("order", 1)]
    )
    assert len(page2) == 5
    assert page2[0]["title"] == "Post 5"
    assert page2[4]["title"] == "Post 9"


@pytest.mark.asyncio
async def test_transaction(sqlite_service: SQLiteService):
    """Test transaction functionality"""
    # Define a transaction that inserts into two collections
    async def transaction_operations(session):
        # Insert into first collection
        user_doc = {"name": "Transaction User", "balance": 1000}
        user_id = await sqlite_service.insert_one(TEST_COLLECTION, user_doc)

        # Insert into second collection
        log_doc = {
            "user_id": user_id,
            "action": "account_created",
            "timestamp": datetime.now(UTC)
        }
        await sqlite_service.insert_one(TEST_COLLECTION_POSTS, log_doc)

        return user_id

    # Execute transaction
    user_id = await sqlite_service.execute_transaction(transaction_operations)

    # Verify both documents were created
    user = await sqlite_service.find_one(TEST_COLLECTION, {"_id": user_id})
    assert user is not None
    assert user["name"] == "Transaction User"

    log = await sqlite_service.find_one(TEST_COLLECTION_POSTS, {"user_id": user_id})
    assert log is not None
    assert log["action"] == "account_created"


@pytest.mark.asyncio
async def test_sparse_index(sqlite_service: SQLiteService):
    """Test sparse index functionality (SQLite doesn't enforce sparse, but should not error)"""
    # Create sparse index on optional field
    await sqlite_service.create_index(
        TEST_COLLECTION,
        "optional_field",
        sparse=True  # SQLite will ignore this but shouldn't error
    )

    # Insert documents with and without the field
    doc_with_field = {"name": "Has Field", "optional_field": "value"}
    doc_without_field = {"name": "No Field"}

    await sqlite_service.insert_one(TEST_COLLECTION, doc_with_field)
    await sqlite_service.insert_one(TEST_COLLECTION, doc_without_field)

    # Both documents should exist
    assert await sqlite_service.find_one(TEST_COLLECTION, {"name": "Has Field"}) is not None
    assert await sqlite_service.find_one(TEST_COLLECTION, {"name": "No Field"}) is not None


@pytest.mark.asyncio
async def test_query_operators(sqlite_service: SQLiteService):
    """Test various query operators"""
    # Insert test documents
    for i in range(10):
        await sqlite_service.insert_one(
            TEST_COLLECTION,
            {"name": f"User {i}", "score": i * 10}
        )

    # Test $gt operator
    results = await sqlite_service.find_many(
        TEST_COLLECTION,
        {"score": {"$gt": 50}}
    )
    assert len(results) >= 4  # scores 60, 70, 80, 90

    # Test $lt operator
    results = await sqlite_service.find_many(
        TEST_COLLECTION,
        {"score": {"$lt": 30}}
    )
    assert len(results) >= 3  # scores 0, 10, 20

    # Test $in operator
    results = await sqlite_service.find_many(
        TEST_COLLECTION,
        {"score": {"$in": [10, 20, 30]}}
    )
    assert len(results) >= 3


@pytest.mark.asyncio
async def test_datetime_handling(sqlite_service: SQLiteService):
    """Test datetime serialization and deserialization"""
    now = datetime.now(UTC)
    doc = {
        "name": "DateTime Test",
        "created_at": now,
        "updated_at": now
    }

    # Insert document with datetime
    doc_id = await sqlite_service.insert_one(TEST_COLLECTION, doc)

    # Retrieve and verify datetime fields
    retrieved = await sqlite_service.find_one(TEST_COLLECTION, {"_id": doc_id})
    assert retrieved is not None
    assert isinstance(retrieved["created_at"], datetime)
    assert isinstance(retrieved["updated_at"], datetime)


@pytest.mark.asyncio
async def test_boolean_handling(sqlite_service: SQLiteService):
    """Test boolean value storage and retrieval"""
    doc = {
        "name": "Boolean Test",
        "active": True,
        "verified": False
    }

    # Insert document with booleans
    doc_id = await sqlite_service.insert_one(TEST_COLLECTION, doc)

    # Retrieve and verify boolean fields
    retrieved = await sqlite_service.find_one(TEST_COLLECTION, {"_id": doc_id})
    assert retrieved is not None
    assert retrieved["active"] is True
    assert retrieved["verified"] is False


@pytest.mark.asyncio
async def test_json_metadata_handling(sqlite_service: SQLiteService):
    """Test JSON metadata serialization for chat_history table"""
    metadata = {
        "adapter": "test-adapter",
        "model": "gpt-4",
        "tokens": 150
    }

    doc = {
        "session_id": "test-session",
        "role": "user",
        "content": "Hello",
        "timestamp": datetime.now(UTC),
        "metadata": metadata
    }

    # Insert into chat_history collection
    doc_id = await sqlite_service.insert_one("chat_history", doc)

    # Retrieve and verify metadata
    retrieved = await sqlite_service.find_one("chat_history", {"_id": doc_id})
    assert retrieved is not None
    assert "metadata" in retrieved
    assert retrieved["metadata"]["adapter"] == "test-adapter"
    assert retrieved["metadata"]["model"] == "gpt-4"
    assert retrieved["metadata"]["tokens"] == 150


@pytest.mark.asyncio
async def test_empty_query(sqlite_service: SQLiteService):
    """Test querying with empty query (should return all documents)"""
    # Insert test documents
    for i in range(3):
        await sqlite_service.insert_one(
            TEST_COLLECTION,
            {"name": f"User {i}"}
        )

    # Query with empty dict
    results = await sqlite_service.find_many(TEST_COLLECTION, {})
    assert len(results) >= 3


@pytest.mark.asyncio
async def test_concurrent_operations(sqlite_service: SQLiteService):
    """Test concurrent database operations"""
    # Run multiple inserts concurrently
    async def insert_doc(i):
        return await sqlite_service.insert_one(
            TEST_COLLECTION,
            {"name": f"Concurrent User {i}", "index": i}
        )

    # Execute 10 concurrent inserts
    tasks = [insert_doc(i) for i in range(10)]
    results = await asyncio.gather(*tasks)

    # All should succeed
    assert len(results) == 10
    assert all(r is not None for r in results)

    # Verify all documents were inserted
    docs = await sqlite_service.find_many(
        TEST_COLLECTION,
        {"name": {"$regex": "Concurrent User"}}
    )
    assert len(docs) >= 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
