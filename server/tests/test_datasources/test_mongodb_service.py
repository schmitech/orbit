import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv
from pytest_asyncio import fixture
from bson import ObjectId
from datetime import datetime, UTC

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.mongodb_service import MongoDBService

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if not env_path.exists():
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)

# Test collection name - use a unique prefix to avoid conflicts
TEST_COLLECTION_PREFIX = "test_"
TEST_COLLECTION = f"{TEST_COLLECTION_PREFIX}users"
TEST_COLLECTION_POSTS = f"{TEST_COLLECTION_PREFIX}posts"

@fixture(scope="function")
async def mongodb_service():
    """Fixture to create and cleanup MongoDB service"""
    # Create MongoDB configuration
    mongodb_config = {
        'internal_services': {
            'mongodb': {
                'host': os.getenv("INTERNAL_SERVICES_MONGODB_HOST"),
                'port': int(os.getenv("INTERNAL_SERVICES_MONGODB_PORT", 27017)),
                'username': os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME"),
                'password': os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD"),
                'database': os.getenv("INTERNAL_SERVICES_MONGODB_DATABASE", "test_db")
            }
        },
        'general': {
        }
    }

    # Validate required environment variables
    required_vars = ["INTERNAL_SERVICES_MONGODB_HOST", "INTERNAL_SERVICES_MONGODB_USERNAME", 
                     "INTERNAL_SERVICES_MONGODB_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        pytest.skip(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Initialize MongoDB service
    service = MongoDBService(mongodb_config)
    
    try:
        await service.initialize()
    except Exception as e:
        pytest.skip(f"Failed to connect to MongoDB: {e}")

    # Yield the service for use in tests
    yield service
    
    # Cleanup: Delete all test collections
    if service.database is not None:
        collections = await service.database.list_collection_names()
        for collection_name in collections:
            if collection_name.startswith(TEST_COLLECTION_PREFIX):
                await service.database[collection_name].drop()
    
    # Close connection
    service.close()

@pytest.mark.asyncio
async def test_initialization(mongodb_service: MongoDBService):
    """Test MongoDB service initialization"""
    assert mongodb_service._initialized is True
    assert mongodb_service.client is not None
    assert mongodb_service.database is not None

@pytest.mark.asyncio
async def test_insert_and_find_one(mongodb_service: MongoDBService):
    """Test inserting and finding a single document"""
    # Create test document
    test_doc = {
        "name": "Test User",
        "email": "test@example.com",
        "age": 30,
        "created_at": datetime.now(UTC)
    }

    # Insert document - should return string ID (not ObjectId)
    inserted_id = await mongodb_service.insert_one(TEST_COLLECTION, test_doc)
    assert inserted_id is not None
    assert isinstance(inserted_id, str)  # Changed: now returns string
    assert len(inserted_id) == 24  # ObjectId string format is 24 characters

    # Find the document by ID (can query with string)
    found_doc = await mongodb_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert found_doc is not None
    assert found_doc["name"] == test_doc["name"]
    assert found_doc["email"] == test_doc["email"]
    assert found_doc["age"] == test_doc["age"]
    # Verify _id is also a string in returned document
    assert isinstance(found_doc["_id"], str)
    assert found_doc["_id"] == inserted_id

@pytest.mark.asyncio
async def test_find_many(mongodb_service: MongoDBService):
    """Test finding multiple documents"""
    # Insert multiple documents
    docs = [
        {"name": f"User {i}", "age": 20 + i, "category": "test"}
        for i in range(5)
    ]

    for doc in docs:
        await mongodb_service.insert_one(TEST_COLLECTION, doc)

    # Find all documents with category "test"
    found_docs = await mongodb_service.find_many(TEST_COLLECTION, {"category": "test"})
    assert len(found_docs) == 5
    # Verify all _id fields are strings
    for doc in found_docs:
        assert isinstance(doc["_id"], str)
        assert len(doc["_id"]) == 24

    # Test with limit
    limited_docs = await mongodb_service.find_many(TEST_COLLECTION, {"category": "test"}, limit=3)
    assert len(limited_docs) == 3
    for doc in limited_docs:
        assert isinstance(doc["_id"], str)

    # Test with sorting
    sorted_docs = await mongodb_service.find_many(
        TEST_COLLECTION,
        {"category": "test"},
        sort=[("age", -1)]  # Sort by age descending
    )
    assert sorted_docs[0]["age"] == 24  # Oldest user
    assert sorted_docs[-1]["age"] == 20  # Youngest user
    for doc in sorted_docs:
        assert isinstance(doc["_id"], str)

@pytest.mark.asyncio
async def test_update_one(mongodb_service: MongoDBService):
    """Test updating a document"""
    # Insert a document
    original_doc = {
        "name": "Update Test",
        "status": "active",
        "score": 100
    }
    inserted_id = await mongodb_service.insert_one(TEST_COLLECTION, original_doc)
    
    # Update the document
    update_result = await mongodb_service.update_one(
        TEST_COLLECTION,
        {"_id": inserted_id},
        {"$set": {"status": "inactive", "score": 150}}
    )
    assert update_result is True
    
    # Verify the update
    updated_doc = await mongodb_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert updated_doc["status"] == "inactive"
    assert updated_doc["score"] == 150
    assert updated_doc["name"] == "Update Test"  # Unchanged field

@pytest.mark.asyncio
async def test_delete_one(mongodb_service: MongoDBService):
    """Test deleting a document"""
    # Insert a document
    doc = {"name": "To Be Deleted", "temporary": True}
    inserted_id = await mongodb_service.insert_one(TEST_COLLECTION, doc)
    
    # Verify it exists
    found = await mongodb_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert found is not None
    
    # Delete the document
    delete_result = await mongodb_service.delete_one(TEST_COLLECTION, {"_id": inserted_id})
    assert delete_result is True
    
    # Verify it's deleted
    not_found = await mongodb_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert not_found is None

@pytest.mark.asyncio
async def test_create_index(mongodb_service: MongoDBService):
    """Test creating indexes"""
    # Create a unique index on email
    index_name = await mongodb_service.create_index(
        TEST_COLLECTION, 
        "email", 
        unique=True
    )
    assert isinstance(index_name, str)
    
    # Test unique constraint by trying to insert duplicate emails
    doc1 = {"name": "User 1", "email": "unique@example.com"}
    await mongodb_service.insert_one(TEST_COLLECTION, doc1)
    
    doc2 = {"name": "User 2", "email": "unique@example.com"}
    # This should fail due to unique constraint
    # MongoDB will raise an exception for duplicate key
    try:
        result = await mongodb_service.insert_one(TEST_COLLECTION, doc2)
        assert False, "Should have raised an exception for duplicate email"
    except Exception as e:
        # Expected behavior - duplicate key error
        assert "duplicate key" in str(e).lower() or result is None
    
    # Create compound index
    compound_index = await mongodb_service.create_index(
        TEST_COLLECTION,
        [("category", 1), ("created_at", -1)]
    )
    assert isinstance(compound_index, str)

@pytest.mark.asyncio
async def test_ensure_id_is_object_id(mongodb_service: MongoDBService):
    """Test ObjectId conversion"""
    # Test with string ID
    string_id = "507f1f77bcf86cd799439011"
    object_id = await mongodb_service.ensure_id_is_object_id(string_id)
    assert isinstance(object_id, ObjectId)
    assert str(object_id) == string_id
    
    # Test with existing ObjectId
    existing_oid = ObjectId()
    result = await mongodb_service.ensure_id_is_object_id(existing_oid)
    assert result == existing_oid
    
    # Test with invalid string
    with pytest.raises(ValueError):
        await mongodb_service.ensure_id_is_object_id("invalid_id")

@pytest.mark.asyncio
async def test_get_collection(mongodb_service: MongoDBService):
    """Test getting a collection"""
    collection = mongodb_service.get_collection(TEST_COLLECTION)
    assert collection is not None
    assert collection.name == TEST_COLLECTION
    
    # Getting the same collection again should return cached instance
    collection2 = mongodb_service.get_collection(TEST_COLLECTION)
    assert collection is collection2

@pytest.mark.asyncio
async def test_skip_and_pagination(mongodb_service: MongoDBService):
    """Test skip functionality for pagination"""
    # Insert 10 documents
    for i in range(10):
        await mongodb_service.insert_one(
            TEST_COLLECTION_POSTS,
            {"title": f"Post {i}", "order": i}
        )
    
    # Get first page (items 0-4)
    page1 = await mongodb_service.find_many(
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
    page2 = await mongodb_service.find_many(
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
async def test_transaction(mongodb_service: MongoDBService):
    """Test transaction functionality"""
    # Define a transaction that inserts into two collections
    async def transaction_operations(session):
        # Insert into first collection
        user_doc = {"name": "Transaction User", "balance": 1000}
        user_result = await mongodb_service.database[TEST_COLLECTION].insert_one(
            user_doc, session=session
        )
        
        # Insert into second collection
        log_doc = {
            "user_id": user_result.inserted_id,
            "action": "account_created",
            "timestamp": datetime.now(UTC)
        }
        await mongodb_service.database[TEST_COLLECTION_POSTS].insert_one(
            log_doc, session=session
        )
        
        return user_result.inserted_id
    
    # Execute transaction
    try:
        user_id = await mongodb_service.execute_transaction(transaction_operations)
        
        # Verify both documents were created
        user = await mongodb_service.find_one(TEST_COLLECTION, {"_id": user_id})
        assert user is not None
        assert user["name"] == "Transaction User"
        
        log = await mongodb_service.find_one(TEST_COLLECTION_POSTS, {"user_id": user_id})
        assert log is not None
        assert log["action"] == "account_created"
    except Exception as e:
        # Some MongoDB deployments don't support transactions (e.g., standalone servers)
        if "Transaction numbers" in str(e):
            pytest.skip("MongoDB deployment doesn't support transactions")
        else:
            raise

@pytest.mark.asyncio
async def test_sparse_index(mongodb_service: MongoDBService):
    """Test sparse index functionality"""
    # Create sparse index on optional field
    await mongodb_service.create_index(
        TEST_COLLECTION,
        "optional_field",
        sparse=True
    )

    # Insert documents with and without the field
    doc_with_field = {"name": "Has Field", "optional_field": "value"}
    doc_without_field = {"name": "No Field"}

    await mongodb_service.insert_one(TEST_COLLECTION, doc_with_field)
    await mongodb_service.insert_one(TEST_COLLECTION, doc_without_field)

    # Both documents should exist
    assert await mongodb_service.find_one(TEST_COLLECTION, {"name": "Has Field"}) is not None
    assert await mongodb_service.find_one(TEST_COLLECTION, {"name": "No Field"}) is not None

@pytest.mark.asyncio
async def test_objectid_to_string_conversion(mongodb_service: MongoDBService):
    """Test that ObjectIds are properly converted to strings for JSON serialization"""
    # Insert a document with nested structure
    test_doc = {
        "name": "Conversion Test",
        "metadata": {
            "created_by": "admin",
            "tags": ["test", "conversion"]
        },
        "items": [
            {"item_name": "Item 1", "value": 100},
            {"item_name": "Item 2", "value": 200}
        ]
    }

    # Insert and get the ID (should be string)
    inserted_id = await mongodb_service.insert_one(TEST_COLLECTION, test_doc)
    assert isinstance(inserted_id, str)
    assert len(inserted_id) == 24  # ObjectId string format

    # Find the document
    found_doc = await mongodb_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert found_doc is not None

    # Verify _id is a string (not ObjectId) for JSON serialization
    assert isinstance(found_doc["_id"], str)
    assert found_doc["_id"] == inserted_id

    # Verify nested structures are preserved
    assert found_doc["metadata"]["created_by"] == "admin"
    assert len(found_doc["items"]) == 2

    # Test find_many also returns string IDs
    many_docs = await mongodb_service.find_many(TEST_COLLECTION, {"name": "Conversion Test"})
    assert len(many_docs) == 1
    assert isinstance(many_docs[0]["_id"], str)

    # Verify JSON serialization works (this would fail with ObjectId)
    import json
    try:
        json_str = json.dumps(found_doc)
        assert inserted_id in json_str  # ID should be in JSON as string
    except TypeError as e:
        pytest.fail(f"Failed to serialize document to JSON: {e}")