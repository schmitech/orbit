import asyncio
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb", reason="duckdb dependency is required for DuckDBStore tests")

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from vector_stores.base.base_store import StoreConfig
from vector_stores.implementations.duckdb_store import DuckDBStore


@pytest.mark.asyncio
async def test_duckdb_store_import_export_csv(tmp_path, monkeypatch):
    """Test basic CSV import/export functionality."""
    db_path = tmp_path / "test.duckdb"
    config = StoreConfig(
        name="duckdb-test",
        connection_params={"database_path": str(db_path), "read_only": False},
    )
    store = DuckDBStore(config)

    try:
        assert await store.connect()

        csv_path = tmp_path / "people.csv"
        csv_path.write_text("id,name,active\n1,Alice,true\n2,Bob,false\n")

        assert await store.import_from_csv(str(csv_path), "people", create_table=True)

        rows = await store.query("SELECT * FROM people ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"
        assert rows[0]["active"] in (True, 1)

        assert await store.create_table("flags", "id INTEGER, active BOOLEAN")
        assert await store.insert_data(
            "flags",
            [
                {"id": 1, "active": True},
                {"id": 2, "active": False},
            ],
        )

        flag_rows = await store.query("SELECT id, active FROM flags ORDER BY id")
        assert [row["active"] for row in flag_rows] == [True, False]

        monkeypatch.chdir(tmp_path)
        export_filename = "people_export.csv"
        assert await store.export_to_csv("people", export_filename)

        exported = Path(tmp_path / export_filename).read_text().splitlines()
        assert exported[0] == "id,name,active"
        assert "1,Alice,true" in exported[1:]
    finally:
        await store.disconnect()


@pytest.mark.asyncio
async def test_duckdb_store_connection_lifecycle(tmp_path):
    """Test connection, disconnection, and health check."""
    db_path = tmp_path / "test_lifecycle.duckdb"
    config = StoreConfig(
        name="duckdb-lifecycle",
        connection_params={"database_path": str(db_path), "read_only": False},
    )
    store = DuckDBStore(config)

    # Initially not connected
    assert not await store.health_check()

    # Connect
    assert await store.connect()
    assert await store.health_check()

    # Disconnect
    await store.disconnect()
    assert not await store.health_check()


@pytest.mark.asyncio
async def test_duckdb_store_context_manager(tmp_path):
    """Test using DuckDBStore as an async context manager."""
    db_path = tmp_path / "test_context.duckdb"
    config = StoreConfig(
        name="duckdb-context",
        connection_params={"database_path": str(db_path), "read_only": False},
    )

    async with DuckDBStore(config) as store:
        assert await store.health_check()
        await store.create_table("test", "id INTEGER")
        tables = await store.list_tables()
        assert "test" in tables

    # After exiting context, should be disconnected
    assert not await store.health_check()


@pytest.mark.asyncio
async def test_duckdb_store_table_operations(tmp_path):
    """Test table creation, listing, info, and dropping."""
    db_path = tmp_path / "test_tables.duckdb"
    config = StoreConfig(
        name="duckdb-tables",
        connection_params={"database_path": str(db_path), "read_only": False},
    )
    store = DuckDBStore(config)

    try:
        await store.connect()

        # Create tables
        assert await store.create_table("users", "id INTEGER, name VARCHAR(100)")
        assert await store.create_table("products", "id INTEGER, price DOUBLE")

        # List tables
        tables = await store.list_tables()
        assert "users" in tables
        assert "products" in tables

        # Insert some data
        await store.insert_data("users", [{"id": 1, "name": "Alice"}])

        # Get table info
        info = await store.get_table_info("users")
        assert info["table_name"] == "users"
        assert info["row_count"] == 1
        assert len(info["schema"]) > 0

        # Drop table
        assert await store.drop_table("products")
        tables = await store.list_tables()
        assert "products" not in tables
        assert "users" in tables
    finally:
        await store.disconnect()


@pytest.mark.asyncio
async def test_duckdb_store_data_types(tmp_path):
    """Test handling of various data types including nulls and special characters."""
    db_path = tmp_path / "test_datatypes.duckdb"
    config = StoreConfig(
        name="duckdb-datatypes",
        connection_params={"database_path": str(db_path), "read_only": False},
    )
    store = DuckDBStore(config)

    try:
        await store.connect()

        # Create table with various types
        await store.create_table(
            "mixed_data",
            "id INTEGER, name VARCHAR(100), score DOUBLE, active BOOLEAN, notes VARCHAR(500)"
        )

        # Insert data with nulls and special characters
        test_data = [
            {"id": 1, "name": "Alice", "score": 95.5, "active": True, "notes": "Great work!"},
            {"id": 2, "name": "Bob's", "score": 87.3, "active": False, "notes": "Quote test: \"hello\""},
            {"id": 3, "name": None, "score": None, "active": None, "notes": None},
            {"id": 4, "name": "Carol, Smith", "score": 92.0, "active": True, "notes": "Comma in name"},
        ]

        assert await store.insert_data("mixed_data", test_data)

        # Query and verify
        rows = await store.query("SELECT * FROM mixed_data ORDER BY id")
        assert len(rows) == 4

        # Check first row
        assert rows[0]["name"] == "Alice"
        assert rows[0]["score"] == 95.5
        assert rows[0]["active"] is True

        # Check special characters (single quote)
        assert rows[1]["name"] == "Bob's"
        assert '"hello"' in rows[1]["notes"]

        # Check nulls
        assert rows[2]["name"] is None
        assert rows[2]["score"] is None
        assert rows[2]["active"] is None

        # Check comma in name
        assert rows[3]["name"] == "Carol, Smith"
    finally:
        await store.disconnect()


@pytest.mark.asyncio
async def test_duckdb_store_csv_append(tmp_path):
    """Test appending CSV data to existing table."""
    db_path = tmp_path / "test_append.duckdb"
    config = StoreConfig(
        name="duckdb-append",
        connection_params={"database_path": str(db_path), "read_only": False},
    )
    store = DuckDBStore(config)

    try:
        await store.connect()

        # Create initial table
        csv_path1 = tmp_path / "data1.csv"
        csv_path1.write_text("id,value\n1,first\n2,second\n")
        assert await store.import_from_csv(str(csv_path1), "data", create_table=True)

        # Append more data
        csv_path2 = tmp_path / "data2.csv"
        csv_path2.write_text("id,value\n3,third\n4,fourth\n")
        assert await store.import_from_csv(str(csv_path2), "data", create_table=False)

        # Verify combined data
        rows = await store.query("SELECT * FROM data ORDER BY id")
        assert len(rows) == 4
        assert rows[0]["value"] == "first"
        assert rows[3]["value"] == "fourth"
    finally:
        await store.disconnect()


@pytest.mark.asyncio
async def test_duckdb_store_parquet_import_export(tmp_path):
    """Test Parquet import and export functionality."""
    parquet = pytest.importorskip("pyarrow", reason="pyarrow required for parquet tests")

    db_path = tmp_path / "test_parquet.duckdb"
    config = StoreConfig(
        name="duckdb-parquet",
        connection_params={"database_path": str(db_path), "read_only": False},
    )
    store = DuckDBStore(config)

    try:
        await store.connect()

        # Create and populate a table
        await store.create_table("products", "id INTEGER, name VARCHAR(100), price DOUBLE")
        await store.insert_data(
            "products",
            [
                {"id": 1, "name": "Widget", "price": 19.99},
                {"id": 2, "name": "Gadget", "price": 29.99},
            ]
        )

        # Export to Parquet
        parquet_path = tmp_path / "products.parquet"
        assert await store.export_to_parquet("products", str(parquet_path))
        assert parquet_path.exists()

        # Drop original table and re-import from Parquet
        await store.drop_table("products")
        assert await store.import_from_parquet(str(parquet_path), "products", create_table=True)

        # Verify data
        rows = await store.query("SELECT * FROM products ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["name"] == "Widget"
        assert rows[1]["price"] == 29.99
    finally:
        await store.disconnect()


@pytest.mark.asyncio
async def test_duckdb_store_empty_table(tmp_path):
    """Test operations on empty tables."""
    db_path = tmp_path / "test_empty.duckdb"
    config = StoreConfig(
        name="duckdb-empty",
        connection_params={"database_path": str(db_path), "read_only": False},
    )
    store = DuckDBStore(config)

    try:
        await store.connect()

        # Create empty table
        await store.create_table("empty_table", "id INTEGER, name VARCHAR(100)")

        # Query empty table
        rows = await store.query("SELECT * FROM empty_table")
        assert len(rows) == 0

        # Get info on empty table
        info = await store.get_table_info("empty_table")
        assert info["row_count"] == 0

        # Insert empty list (should not fail)
        assert await store.insert_data("empty_table", [])

        # Export empty table
        export_path = tmp_path / "empty_export.csv"
        assert await store.export_to_csv("empty_table", str(export_path))
        assert export_path.exists()

        # Verify export has only header
        content = export_path.read_text().strip()
        assert content == "id,name"
    finally:
        await store.disconnect()


@pytest.mark.asyncio
async def test_duckdb_store_error_handling(tmp_path):
    """Test error handling for various failure scenarios."""
    db_path = tmp_path / "test_errors.duckdb"
    config = StoreConfig(
        name="duckdb-errors",
        connection_params={"database_path": str(db_path), "read_only": False},
    )
    store = DuckDBStore(config)

    try:
        await store.connect()

        # Test invalid SQL query
        with pytest.raises(Exception):
            await store.query("SELECT * FROM nonexistent_table")

        # Test invalid table creation
        with pytest.raises(Exception):
            await store.execute("CREATE TABLE invalid syntax here")

        # Test import from non-existent file
        result = await store.import_from_csv("/nonexistent/file.csv", "test_table", create_table=True)
        assert result is False

        # Test export from non-existent table
        result = await store.export_to_csv("nonexistent_table", str(tmp_path / "out.csv"))
        assert result is False
    finally:
        await store.disconnect()


@pytest.mark.asyncio
async def test_duckdb_store_stats(tmp_path):
    """Test statistics tracking."""
    db_path = tmp_path / "test_stats.duckdb"
    config = StoreConfig(
        name="duckdb-stats",
        connection_params={"database_path": str(db_path), "read_only": False},
    )
    store = DuckDBStore(config)

    try:
        await store.connect()

        # Perform some operations
        await store.create_table("test", "id INTEGER")
        await store.query("SELECT 1")

        # Get stats
        stats = await store.get_stats()
        assert stats["store_name"] == "duckdb-stats"
        assert stats["status"] == "connected"
        assert stats["operation_count"] >= 2  # At least 2 operations performed
        assert "created_at" in stats
        assert "last_accessed" in stats
    finally:
        await store.disconnect()


@pytest.mark.asyncio
async def test_duckdb_store_in_memory(tmp_path):
    """Test using in-memory database."""
    config = StoreConfig(
        name="duckdb-memory",
        connection_params={"database_path": ":memory:", "read_only": False},
    )
    store = DuckDBStore(config)

    try:
        await store.connect()

        # Create and query in-memory table
        await store.create_table("temp_data", "id INTEGER, value VARCHAR(50)")
        await store.insert_data("temp_data", [{"id": 1, "value": "test"}])

        rows = await store.query("SELECT * FROM temp_data")
        assert len(rows) == 1
        assert rows[0]["value"] == "test"
    finally:
        await store.disconnect()
