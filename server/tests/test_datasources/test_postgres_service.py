"""
Test PostgreSQL Service
========================

This script tests the PostgreSQL service implementation to ensure it provides
the same functionality as the SQLite/MongoDB services.

Prerequisites:
1. A running PostgreSQL server reachable with the INTERNAL_SERVICES_POSTGRES_*
   environment variables (see env.example). Tests are skipped automatically if
   these are not set or the connection fails.
2. Tests use a unique table-name prefix and drop those tables on teardown.
"""

import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv
from pytest_asyncio import fixture
from datetime import datetime, UTC

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.postgres_service import PostgresService

# Load environment variables from .env file in project root, if present
env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Test table names - use a unique prefix to avoid colliding with the fixed schema
TEST_COLLECTION_PREFIX = "test_"
TEST_COLLECTION = f"{TEST_COLLECTION_PREFIX}users"
TEST_COLLECTION_POSTS = f"{TEST_COLLECTION_PREFIX}posts"


@fixture(scope="function")
async def postgres_service():
    """Fixture to create and cleanup Postgres service"""
    postgres_config = {
        'internal_services': {
            'backend': {
                'type': 'postgres',
                'postgres': {
                    'host': os.getenv("INTERNAL_SERVICES_POSTGRES_HOST"),
                    'port': int(os.getenv("INTERNAL_SERVICES_POSTGRES_PORT", 5432)),
                    'database': os.getenv("INTERNAL_SERVICES_POSTGRES_DB", "test_db"),
                    'username': os.getenv("INTERNAL_SERVICES_POSTGRES_USERNAME"),
                    'password': os.getenv("INTERNAL_SERVICES_POSTGRES_PASSWORD"),
                    'sslmode': os.getenv("INTERNAL_SERVICES_POSTGRES_SSLMODE", "prefer"),
                }
            }
        },
        'general': {}
    }

    required_vars = ["INTERNAL_SERVICES_POSTGRES_HOST", "INTERNAL_SERVICES_POSTGRES_USERNAME"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        pytest.skip(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Bypass the singleton cache so each test gets an isolated instance/connection
    PostgresService.clear_cache()
    service = PostgresService(postgres_config)

    try:
        await service.initialize()
    except Exception as e:
        pytest.skip(f"Failed to connect to PostgreSQL: {e}")

    yield service

    # Cleanup: drop any tables created by these tests
    def _drop_test_tables():
        with service._db_lock:
            cursor = service.connection.cursor()
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE %s",
                (f"{TEST_COLLECTION_PREFIX}%",)
            )
            tables = [row['table_name'] for row in cursor.fetchall()]
            for table in tables:
                cursor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            service.connection.commit()

    try:
        _drop_test_tables()
    except Exception:
        pass

    service.close()
    PostgresService.clear_cache()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_initialization(postgres_service: PostgresService):
    """Test Postgres service initialization"""
    assert postgres_service._initialized is True
    assert postgres_service.connection is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_insert_and_find_one(postgres_service: PostgresService):
    """Test inserting and finding a single document (exercises dynamic table creation)"""
    test_doc = {
        "name": "Test User",
        "email": "test@example.com",
        "age": 30,
        "active": True,
    }

    inserted_id = await postgres_service.insert_one(TEST_COLLECTION, test_doc)
    assert inserted_id is not None
    assert isinstance(inserted_id, str)

    found_doc = await postgres_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert found_doc is not None
    assert found_doc["name"] == test_doc["name"]
    assert found_doc["email"] == test_doc["email"]
    assert found_doc["age"] == test_doc["age"]
    assert found_doc["_id"] == inserted_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_many(postgres_service: PostgresService):
    """Test finding multiple documents"""
    docs = [
        {"name": f"User {i}", "age": 20 + i, "category": "test"}
        for i in range(5)
    ]

    for doc in docs:
        await postgres_service.insert_one(TEST_COLLECTION, doc)

    found_docs = await postgres_service.find_many(TEST_COLLECTION, {"category": "test"})
    assert len(found_docs) == 5

    limited_docs = await postgres_service.find_many(TEST_COLLECTION, {"category": "test"}, limit=3)
    assert len(limited_docs) == 3

    sorted_docs = await postgres_service.find_many(
        TEST_COLLECTION,
        {"category": "test"},
        sort=[("age", -1)]
    )
    assert sorted_docs[0]["age"] == 24
    assert sorted_docs[-1]["age"] == 20


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_one(postgres_service: PostgresService):
    """Test updating a document"""
    original_doc = {
        "name": "Update Test",
        "status": "active",
        "score": 100
    }
    inserted_id = await postgres_service.insert_one(TEST_COLLECTION, original_doc)

    update_result = await postgres_service.update_one(
        TEST_COLLECTION,
        {"_id": inserted_id},
        {"$set": {"status": "inactive", "score": 150}}
    )
    assert update_result is True

    updated_doc = await postgres_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert updated_doc["status"] == "inactive"
    assert updated_doc["score"] == 150
    assert updated_doc["name"] == "Update Test"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_one(postgres_service: PostgresService):
    """Test deleting a document"""
    doc = {"name": "To Be Deleted", "temporary": True}
    inserted_id = await postgres_service.insert_one(TEST_COLLECTION, doc)

    found = await postgres_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert found is not None

    delete_result = await postgres_service.delete_one(TEST_COLLECTION, {"_id": inserted_id})
    assert delete_result is True

    not_found = await postgres_service.find_one(TEST_COLLECTION, {"_id": inserted_id})
    assert not_found is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_many(postgres_service: PostgresService):
    """Test deleting multiple documents"""
    for i in range(4):
        await postgres_service.insert_one(TEST_COLLECTION, {"name": f"Bulk {i}", "group": "bulk"})

    deleted_count = await postgres_service.delete_many(TEST_COLLECTION, {"group": "bulk"})
    assert deleted_count == 4

    remaining = await postgres_service.find_many(TEST_COLLECTION, {"group": "bulk"})
    assert len(remaining) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_count(postgres_service: PostgresService):
    """Test counting documents"""
    for i in range(3):
        await postgres_service.insert_one(TEST_COLLECTION, {"name": f"Count {i}", "group": "count_test"})

    count = await postgres_service.count(TEST_COLLECTION, {"group": "count_test"})
    assert count == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clear_collection(postgres_service: PostgresService):
    """Test clearing all rows from a table"""
    for i in range(3):
        await postgres_service.insert_one(TEST_COLLECTION, {"name": f"Clear {i}"})

    deleted_count = await postgres_service.clear_collection(TEST_COLLECTION)
    assert deleted_count == 3

    remaining = await postgres_service.find_many(TEST_COLLECTION, {})
    assert len(remaining) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_index(postgres_service: PostgresService):
    """Test creating indexes, including the pending-index path for not-yet-created tables"""
    # Table doesn't exist yet - index should be queued
    index_name = await postgres_service.create_index(
        TEST_COLLECTION,
        "email",
        unique=True
    )
    assert isinstance(index_name, str)
    assert TEST_COLLECTION in postgres_service._pending_indexes

    # Creating the table should apply the queued index
    doc1 = {"name": "User 1", "email": "unique@example.com"}
    await postgres_service.insert_one(TEST_COLLECTION, doc1)
    assert TEST_COLLECTION not in postgres_service._pending_indexes

    # Unique constraint should now be enforced
    doc2 = {"name": "User 2", "email": "unique@example.com"}
    with pytest.raises(Exception):
        await postgres_service.insert_one(TEST_COLLECTION, doc2)

    # Compound index on an existing table
    compound_index = await postgres_service.create_index(
        TEST_COLLECTION,
        [("name", 1), ("email", -1)]
    )
    assert isinstance(compound_index, str)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ensure_id_is_object_id(postgres_service: PostgresService):
    """Test UUID validation/conversion"""
    import uuid

    valid_uuid = str(uuid.uuid4())
    result = await postgres_service.ensure_id_is_object_id(valid_uuid)
    assert result == valid_uuid

    with pytest.raises(ValueError):
        await postgres_service.ensure_id_is_object_id("not-a-uuid")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_collection(postgres_service: PostgresService):
    """Test getting a collection/table name"""
    collection = postgres_service.get_collection(TEST_COLLECTION)
    assert collection == TEST_COLLECTION


@pytest.mark.integration
@pytest.mark.asyncio
async def test_skip_and_pagination(postgres_service: PostgresService):
    """Test skip functionality for pagination"""
    for i in range(10):
        await postgres_service.insert_one(
            TEST_COLLECTION_POSTS,
            {"title": f"Post {i}", "order": i}
        )

    page1 = await postgres_service.find_many(
        TEST_COLLECTION_POSTS,
        {},
        limit=5,
        skip=0,
        sort=[("order", 1)]
    )
    assert len(page1) == 5
    assert page1[0]["title"] == "Post 0"
    assert page1[4]["title"] == "Post 4"

    page2 = await postgres_service.find_many(
        TEST_COLLECTION_POSTS,
        {},
        limit=5,
        skip=5,
        sort=[("order", 1)]
    )
    assert len(page2) == 5
    assert page2[0]["title"] == "Post 5"
    assert page2[4]["title"] == "Post 9"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_transaction_commit(postgres_service: PostgresService):
    """Test transaction functionality commits all operations together"""
    async def transaction_operations(session):
        user_doc = {"name": "Transaction User", "balance": 1000}
        user_id = await postgres_service.insert_one(TEST_COLLECTION, user_doc)

        log_doc = {
            "user_id": user_id,
            "action": "account_created",
            "timestamp": datetime.now(UTC).isoformat()
        }
        await postgres_service.insert_one(TEST_COLLECTION_POSTS, log_doc)

        return user_id

    user_id = await postgres_service.execute_transaction(transaction_operations)

    user = await postgres_service.find_one(TEST_COLLECTION, {"_id": user_id})
    assert user is not None
    assert user["name"] == "Transaction User"

    log = await postgres_service.find_one(TEST_COLLECTION_POSTS, {"user_id": user_id})
    assert log is not None
    assert log["action"] == "account_created"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_transaction_rollback(postgres_service: PostgresService):
    """Test that a failing transaction rolls back its operations"""
    # Pre-create the table outside the transaction
    await postgres_service.insert_one(TEST_COLLECTION, {"name": "seed"})

    async def failing_operations(session):
        await postgres_service.insert_one(TEST_COLLECTION, {"name": "Should Not Persist"})
        raise RuntimeError("Simulated failure")

    with pytest.raises(RuntimeError):
        await postgres_service.execute_transaction(failing_operations)

    found = await postgres_service.find_one(TEST_COLLECTION, {"name": "Should Not Persist"})
    assert found is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_write_not_swept_into_transaction(postgres_service: PostgresService):
    """
    A concurrent insert from another task must not be silently committed/rolled-back
    by an unrelated in-flight transaction on the same service instance - it should
    block on the operation lock until the transaction finishes, then auto-commit
    independently.
    """
    import asyncio

    # Pre-create the table outside the transaction
    await postgres_service.insert_one(TEST_COLLECTION, {"name": "seed"})

    started = asyncio.Event()
    proceed = asyncio.Event()

    async def long_failing_transaction(session):
        await postgres_service.insert_one(TEST_COLLECTION, {"name": "Transaction Write"})
        started.set()
        await proceed.wait()
        raise RuntimeError("Simulated failure")

    async def concurrent_independent_insert():
        await started.wait()
        return await postgres_service.insert_one(TEST_COLLECTION, {"name": "Concurrent Write"})

    tx_task = asyncio.create_task(postgres_service.execute_transaction(long_failing_transaction))
    concurrent_task = asyncio.create_task(concurrent_independent_insert())

    await started.wait()
    # The concurrent insert must still be blocked behind the operation lock
    await asyncio.sleep(0.2)
    assert not concurrent_task.done()

    proceed.set()

    with pytest.raises(RuntimeError):
        await tx_task
    concurrent_id = await concurrent_task

    # The transaction's own write was rolled back
    assert await postgres_service.find_one(TEST_COLLECTION, {"name": "Transaction Write"}) is None
    # The unrelated concurrent write persisted independently
    found = await postgres_service.find_one(TEST_COLLECTION, {"_id": concurrent_id})
    assert found is not None
    assert found["name"] == "Concurrent Write"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_query_operators(postgres_service: PostgresService):
    """Test $gt/$lt/$in/$regex query translation"""
    for i in range(5):
        await postgres_service.insert_one(TEST_COLLECTION, {"name": f"Op User {i}", "age": 20 + i})

    gt_docs = await postgres_service.find_many(TEST_COLLECTION, {"age": {"$gt": 22}})
    assert all(doc["age"] > 22 for doc in gt_docs)

    in_docs = await postgres_service.find_many(TEST_COLLECTION, {"age": {"$in": [20, 24]}})
    assert {doc["age"] for doc in in_docs} == {20, 24}

    regex_docs = await postgres_service.find_many(TEST_COLLECTION, {"name": {"$regex": "Op User"}})
    assert len(regex_docs) == 5
