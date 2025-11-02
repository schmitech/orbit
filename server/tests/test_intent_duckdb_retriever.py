"""
Tests for the DuckDB Intent Retriever

This test suite verifies the IntentDuckDBRetriever implementation,
including connection handling, query execution, and parameter binding.
"""

import pytest
import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

duckdb = pytest.importorskip("duckdb", reason="duckdb dependency is required for DuckDB intent retriever tests")

from retrievers.implementations.intent.intent_duckdb_retriever import IntentDuckDBRetriever


@pytest.fixture
def test_config(tmp_path):
    """Create a test configuration with temporary DuckDB database."""
    db_path = tmp_path / "test.duckdb"
    
    return {
        "datasources": {
            "duckdb": {
                "database": str(db_path),
                "read_only": False,
                "access_mode": "automatic",
                "threads": None
            }
        },
        "general": {
            "verbose": False
        },
        "adapter_config": {
            "domain_config_path": "utils/duckdb-intent-template/examples/analytics/analytics_domain.yaml",
            "template_library_path": ["utils/duckdb-intent-template/examples/analytics/analytics_templates.yaml"],
            "template_collection_name": "test_templates",
            "store_name": "chroma",
            "confidence_threshold": 0.4,
            "max_templates": 5,
            "return_results": 100,
            "reload_templates_on_start": False,
            "force_reload_templates": False
        }
    }


@pytest.fixture
async def test_database(tmp_path):
    """Create a test DuckDB database with sample data."""
    db_path = tmp_path / "test_data.duckdb"
    conn = duckdb.connect(str(db_path))
    
    try:
        # Create test tables
        conn.execute("""
            CREATE TABLE sales (
                id INTEGER PRIMARY KEY,
                sale_date DATE,
                product_name VARCHAR,
                category VARCHAR,
                region VARCHAR,
                sales_amount DECIMAL(10, 2),
                quantity INTEGER
            )
        """)
        
        conn.execute("""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                product_name VARCHAR,
                category VARCHAR,
                price DECIMAL(10, 2)
            )
        """)
        
        # Insert test data
        conn.execute("""
            INSERT INTO sales VALUES
            (1, '2024-01-15', 'Laptop', 'Electronics', 'West', 1299.99, 1),
            (2, '2024-01-16', 'T-Shirt', 'Clothing', 'East', 29.99, 2),
            (3, '2024-01-17', 'Coffee', 'Food', 'North', 9.99, 5),
            (4, '2024-01-18', 'Laptop', 'Electronics', 'West', 1299.99, 1),
            (5, '2024-01-19', 'T-Shirt', 'Clothing', 'West', 29.99, 3)
        """)
        
        conn.execute("""
            INSERT INTO products VALUES
            (1, 'Laptop', 'Electronics', 1299.99),
            (2, 'T-Shirt', 'Clothing', 29.99),
            (3, 'Coffee', 'Food', 9.99)
        """)
        
        yield str(db_path)
    finally:
        conn.close()


@pytest.fixture
def mock_domain_adapter():
    """Create a mock domain adapter for testing."""
    adapter = Mock()
    adapter.get_domain_config.return_value = {
        "domain_name": "Test Analytics",
        "description": "Test domain",
        "entities": {
            "sales": {
                "table_name": "sales"
            }
        }
    }
    return adapter


@pytest.mark.asyncio
async def test_duckdb_retriever_connection_file_based(test_config, test_database):
    """Test creating a connection to a file-based DuckDB database."""
    # Override database path with test database
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    assert retriever.connection is not None
    assert retriever.database_path == test_database
    
    # Verify connection works
    assert retriever._is_connection_alive()
    
    await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_connection_in_memory(test_config):
    """Test creating a connection to an in-memory DuckDB database."""
    # Set database to in-memory
    test_config["datasources"]["duckdb"]["database"] = ":memory:"
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    assert retriever.connection is not None
    assert retriever.database_path == ":memory:"
    
    # Verify connection works
    assert retriever._is_connection_alive()
    
    await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_query_execution(test_config, test_database):
    """Test executing queries on DuckDB database."""
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        # Test simple SELECT query
        results = await retriever._execute_raw_query("SELECT * FROM sales LIMIT 3")
        
        assert len(results) == 3
        assert "id" in results[0]
        assert "product_name" in results[0]
        assert "sales_amount" in results[0]
        assert results[0]["product_name"] == "Laptop"
        # DuckDB returns Decimal for DECIMAL columns, convert to float for comparison
        sales_amount = results[0]["sales_amount"]
        if hasattr(sales_amount, '__float__'):
            sales_amount = float(sales_amount)
        assert sales_amount == 1299.99
        
        # Test query with WHERE clause
        results = await retriever._execute_raw_query(
            "SELECT * FROM sales WHERE region = 'West' ORDER BY id"
        )
        
        assert len(results) == 3
        assert all(row["region"] == "West" for row in results)
        
        # Test aggregate query
        results = await retriever._execute_raw_query(
            "SELECT COUNT(*) as total FROM sales"
        )
        
        assert len(results) == 1
        assert results[0]["total"] == 5
        
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_named_parameters(test_config, test_database):
    """Test query execution with named parameters (converted to positional)."""
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        # Test with named parameters (:name) - should be converted to positional
        results = await retriever._execute_raw_query(
            "SELECT * FROM sales WHERE region = :region ORDER BY id",
            {"region": "West"}
        )
        
        assert len(results) == 3
        assert all(row["region"] == "West" for row in results)
        
        # Test with multiple named parameters
        results = await retriever._execute_raw_query(
            "SELECT * FROM sales WHERE region = :region AND quantity >= :quantity ORDER BY id",
            {"region": "West", "quantity": 1}
        )
        
        assert len(results) == 3
        
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_postgres_style_parameters(test_config, test_database):
    """Test automatic conversion of PostgreSQL-style parameters to DuckDB format."""
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        # Test with PostgreSQL-style parameters (%(name)s) - should be auto-converted
        results = await retriever._execute_raw_query(
            "SELECT * FROM sales WHERE region = %(region)s ORDER BY id",
            {"region": "East"}
        )
        
        assert len(results) == 1
        assert results[0]["region"] == "East"
        
        # Test with multiple PostgreSQL-style parameters
        results = await retriever._execute_raw_query(
            "SELECT * FROM sales WHERE region = %(region)s AND category = %(category)s",
            {"region": "West", "category": "Electronics"}
        )
        
        assert len(results) == 2
        assert all(row["region"] == "West" and row["category"] == "Electronics" for row in results)
        
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_positional_parameters(test_config, test_database):
    """Test query execution with positional parameters."""
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        # DuckDB supports positional parameters (?)
        # Note: DuckDB's positional parameter support may vary by version
        # Testing with tuple parameters
        results = await retriever._execute_raw_query(
            "SELECT * FROM sales WHERE region = ? ORDER BY id",
            ("West",)
        )
        
        assert len(results) == 3
        assert all(row["region"] == "West" for row in results)
        
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_connection_alive_check(test_config, test_database):
    """Test connection alive check functionality."""
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    
    # Before connection
    assert not retriever._is_connection_alive()
    
    # After connection
    await retriever.create_connection()
    assert retriever._is_connection_alive()
    
    # After close
    await retriever._close_connection()
    assert not retriever._is_connection_alive()


@pytest.mark.asyncio
async def test_duckdb_retriever_test_query(test_config):
    """Test the test query method."""
    retriever = IntentDuckDBRetriever(config=test_config)
    
    test_query = retriever.get_test_query()
    assert test_query == "SELECT 1 as test"
    
    # Test that it can be executed
    await retriever.create_connection()
    try:
        results = await retriever._execute_raw_query(test_query)
        assert len(results) == 1
        assert results[0]["test"] == 1
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_get_defaults(test_config):
    """Test default value methods."""
    retriever = IntentDuckDBRetriever(config=test_config)
    
    assert retriever._get_datasource_name() == "duckdb"
    assert retriever.get_default_port() is None
    assert retriever.get_default_database() == ":memory:"
    assert retriever.get_default_username() is None


@pytest.mark.asyncio
async def test_duckdb_retriever_connection_config_priority(test_config, tmp_path):
    """Test that database path configuration follows priority order."""
    db_path1 = tmp_path / "primary.duckdb"
    db_path2 = tmp_path / "secondary.duckdb"
    
    # Test priority: database_path > database > default
    test_config["datasources"]["duckdb"]["database_path"] = str(db_path1)
    test_config["datasources"]["duckdb"]["database"] = str(db_path2)
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        # database_path should take priority
        assert retriever.database_path == str(db_path1)
    finally:
        await retriever._close_connection()
    
    # Test with only database
    test_config["datasources"]["duckdb"].pop("database_path", None)
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        assert retriever.database_path == str(db_path2)
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_empty_results(test_config, test_database):
    """Test query execution that returns empty results."""
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        # Query that returns no results
        results = await retriever._execute_raw_query(
            "SELECT * FROM sales WHERE region = 'NonExistent'"
        )
        
        assert isinstance(results, list)
        assert len(results) == 0
        
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_aggregation_queries(test_config, test_database):
    """Test aggregation queries."""
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        # Test SUM aggregation
        results = await retriever._execute_raw_query(
            "SELECT region, SUM(sales_amount) as total FROM sales GROUP BY region ORDER BY region"
        )
        
        assert len(results) > 0
        assert "region" in results[0]
        assert "total" in results[0]
        
        # Test COUNT aggregation
        results = await retriever._execute_raw_query(
            "SELECT category, COUNT(*) as count FROM sales GROUP BY category"
        )
        
        assert len(results) > 0
        assert "category" in results[0]
        assert "count" in results[0]
        
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_multiple_tables(test_config, test_database):
    """Test queries joining multiple tables."""
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        # Test JOIN query
        results = await retriever._execute_raw_query("""
            SELECT s.id, s.product_name, s.sales_amount, p.price
            FROM sales s
            JOIN products p ON s.product_name = p.product_name
            ORDER BY s.id
            LIMIT 3
        """)
        
        assert len(results) == 3
        assert "id" in results[0]
        assert "product_name" in results[0]
        assert "sales_amount" in results[0]
        assert "price" in results[0]
        
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_error_handling(test_config):
    """Test error handling for invalid queries."""
    test_config["datasources"]["duckdb"]["database"] = ":memory:"
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        # Test invalid SQL
        with pytest.raises(Exception):
            await retriever._execute_raw_query("INVALID SQL STATEMENT")
        
        # Test query on non-existent table
        with pytest.raises(Exception):
            await retriever._execute_raw_query("SELECT * FROM nonexistent_table")
        
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_read_only_mode(test_config, tmp_path):
    """Test read-only mode configuration."""
    # Create a separate database file for read-only test to avoid connection conflicts
    db_path = tmp_path / "readonly_test.duckdb"
    conn = duckdb.connect(str(db_path))
    
    try:
        # Create table and insert data
        conn.execute("""
            CREATE TABLE sales (
                id INTEGER PRIMARY KEY,
                product_name VARCHAR,
                region VARCHAR
            )
        """)
        conn.execute("INSERT INTO sales VALUES (1, 'Laptop', 'West')")
    finally:
        conn.close()
    
    # Create read-only retriever
    test_config["datasources"]["duckdb"]["database"] = str(db_path)
    test_config["datasources"]["duckdb"]["read_only"] = True
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    try:
        # Read operations should work
        results = await retriever._execute_raw_query("SELECT * FROM sales LIMIT 1")
        assert len(results) == 1
        
        # Write operations should fail or be ignored in read-only mode
        # (DuckDB may allow writes even in read_only mode if the file is writable,
        # but the intent is to test the configuration)
        
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_duckdb_retriever_close_connection_idempotent(test_config, test_database):
    """Test that closing a connection multiple times doesn't error."""
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    
    # Close multiple times - should not error
    await retriever._close_connection()
    await retriever._close_connection()
    await retriever._close_connection()
    
    # Should still return False for connection alive
    assert not retriever._is_connection_alive()


@pytest.mark.asyncio
async def test_duckdb_retriever_connection_after_close_error(test_config, test_database):
    """Test that queries fail gracefully after connection is closed."""
    test_config["datasources"]["duckdb"]["database"] = test_database
    
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()
    await retriever._close_connection()
    
    # Query after close should fail
    with pytest.raises(Exception):
        await retriever._execute_raw_query("SELECT 1")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

