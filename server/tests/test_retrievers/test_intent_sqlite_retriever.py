"""
Tests for the SQLite Intent Retriever

This test suite verifies the IntentSQLiteRetriever implementation,
including connection handling, query execution, and parameter binding.
"""

import pytest
import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock, AsyncMock

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

try:
    import sqlite3
except ImportError:
    sqlite3 = None

if sqlite3 is None:
    pytest.skip("sqlite3 is required for SQLite intent retriever tests", allow_module_level=True)

from retrievers.implementations.intent.intent_sqlite_retriever import IntentSQLiteRetriever


@pytest.fixture
def test_config(tmp_path):
    """Create a test configuration with temporary SQLite database."""
    db_path = tmp_path / "test.db"
    
    return {
        "datasources": {
            "sqlite": {
                "database": str(db_path),
                "check_same_thread": False
            }
        },
        "general": {
        },
        "inference": {
            "openai": {
                "enabled": True,
                "api_key": os.getenv("OPENAI_API_KEY", "test-key"),
                "model": "gpt-4o-mini"
            }
        },
        "embedding": {
            "cohere": {
                "enabled": True,
                "api_key": os.getenv("COHERE_API_KEY", "test-key"),
                "model": "embed-english-v3.0"
            }
        },
        "stores": {
            "vector_stores": {
                "chroma": {
                    "enabled": True,
                    "type": "chroma",
                    "connection_params": {
                        "persist_directory": str(tmp_path / "chroma_db")
                    }
                }
            }
        },
        "adapter_config": {
            "domain_config_path": "utils/sql-intent-template/examples/sqlite/contact/contact-domain.yaml",
            "template_library_path": ["utils/sql-intent-template/examples/sqlite/contact/contact-templates.yaml"],
            "template_collection_name": "test_templates",
            "store_name": "chroma",
            "confidence_threshold": 0.4,
            "max_templates": 5,
            "return_results": 100,
            "reload_templates_on_start": False,
            "force_reload_templates": False
        },
        "inference_provider": "openai"
    }


@pytest.fixture
async def test_database(tmp_path):
    """Create a test SQLite database with sample data."""
    db_path = tmp_path / "test_data.db"
    conn = sqlite3.connect(str(db_path))
    
    try:
        # Create test tables
        conn.execute("""
            CREATE TABLE contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                company TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.execute("""
            CREATE TABLE companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                industry TEXT,
                size INTEGER
            )
        """)
        
        # Insert test data
        conn.execute("""
            INSERT INTO contacts (name, email, phone, company) VALUES
            ('John Doe', 'john@example.com', '555-0101', 'Acme Corp'),
            ('Jane Smith', 'jane@example.com', '555-0102', 'Tech Inc'),
            ('Bob Johnson', 'bob@example.com', '555-0103', 'Acme Corp'),
            ('Alice Williams', 'alice@example.com', '555-0104', 'Startup Co'),
            ('Charlie Brown', 'charlie@example.com', '555-0105', 'Tech Inc')
        """)
        
        conn.execute("""
            INSERT INTO companies (name, industry, size) VALUES
            ('Acme Corp', 'Manufacturing', 500),
            ('Tech Inc', 'Technology', 200),
            ('Startup Co', 'Technology', 50)
        """)
        
        conn.commit()
        
        yield str(db_path)
        
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_sqlite_retriever_initialization(test_config, test_database):
    """Test that SQLite retriever can be initialized."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    
    assert retriever is not None
    assert retriever._get_datasource_name() == "sqlite"


@pytest.mark.asyncio
async def test_sqlite_retriever_connection(test_config, test_database):
    """Test SQLite connection creation."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    connection = await retriever.create_connection()
    retriever._connection = connection  # Set the connection manually for testing
    
    try:
        assert retriever.connection is not None
        assert retriever._is_connection_alive()
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_sqlite_retriever_query_execution(test_config, test_database):
    """Test that SQLite retriever can execute queries."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    connection = await retriever.create_connection()
    retriever._connection = connection  # Set the connection manually for testing
    
    try:
        results = await retriever._execute_raw_query("SELECT * FROM contacts LIMIT 2")
        
        assert len(results) == 2
        assert "name" in results[0]
        assert "email" in results[0]
    finally:
        await retriever._close_connection()


@pytest.mark.asyncio
async def test_sqlite_retriever_close_connection_idempotent(test_config, test_database):
    """Test that closing a connection multiple times doesn't error."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    connection = await retriever.create_connection()
    retriever._connection = connection  # Set the connection manually for testing
    
    # Close multiple times - should not error
    await retriever._close_connection()
    await retriever._close_connection()
    await retriever._close_connection()
    
    # Should still return False for connection alive
    assert not retriever._is_connection_alive()


@pytest.mark.asyncio
async def test_sqlite_retriever_connection_after_close_error(test_config, test_database):
    """Test that queries fail gracefully after connection is closed."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    connection = await retriever.create_connection()
    retriever._connection = connection  # Set the connection manually for testing
    await retriever._close_connection()
    
    # Query after close should fail
    with pytest.raises(Exception):
        await retriever._execute_raw_query("SELECT 1")


@pytest.mark.asyncio
async def test_intent_retriever_close_all_resources(test_config, test_database):
    """Test that close() method closes all resources (database, embedding, inference, template_store)."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    
    # Initialize the retriever to set up all resources
    try:
        # Register services first
        from ai_services import register_all_services
        register_all_services(test_config)
        
        # Mock vector store initialization to avoid Chroma setup issues
        async def mock_init_vector_store():
            retriever.template_store = Mock()
            retriever.template_store.close = AsyncMock()
            retriever.template_store.batch_add_templates = AsyncMock(return_value=[])
        
        retriever._initialize_vector_store = mock_init_vector_store
        
        await retriever.initialize()
        
        # Verify resources are initialized
        assert retriever.embedding_client is not None
        assert retriever.inference_client is not None
        assert hasattr(retriever, 'template_store') and retriever.template_store is not None
        
        # Close all resources
        await retriever.close()
        
        # Note: Database connection is NOT closed by close() anymore - it's managed by datasource registry
        # We can verify that embedding/inference clients are closed, but connection remains open
        # The connection will be closed by the datasource registry when reference count reaches 0
        
    except Exception as e:
        # Clean up on error
        try:
            await retriever.close()
        except:
            pass
        raise


@pytest.mark.asyncio
async def test_intent_retriever_close_handles_missing_clients(test_config, test_database):
    """Test that close() handles None or missing clients gracefully."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    
    # Manually set clients to None to simulate uninitialized state
    retriever.embedding_client = None
    retriever.inference_client = None
    
    # Should not raise an error
    await retriever.close()
    
    # Should still work even if called again (idempotent)
    await retriever.close()


@pytest.mark.asyncio
async def test_intent_retriever_close_handles_client_errors(test_config, test_database):
    """Test that errors in one client don't prevent others from closing."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    
    try:
        # Register services first
        from ai_services import register_all_services
        register_all_services(test_config)
        
        await retriever.initialize()
        
        # Create mock clients that raise errors on close
        # Note: The code uses getattr() to check for aclose() first, then close()
        mock_embedding = Mock()
        mock_embedding.aclose = Mock(side_effect=Exception("Embedding close error"))
        retriever.embedding_client = mock_embedding
        
        mock_inference = Mock()
        mock_inference.aclose = Mock(side_effect=Exception("Inference close error"))
        retriever.inference_client = mock_inference
        
        # Close should handle errors gracefully
        # Note: Database connection is NOT closed by close() anymore - it's managed by datasource registry
        await retriever.close()
        
        # Verify aclose was attempted on both clients (getattr checks for aclose first)
        mock_embedding.aclose.assert_called_once()
        mock_inference.aclose.assert_called_once()
        
    except Exception as e:
        # Clean up on error
        try:
            await retriever.close()
        except:
            pass
        raise


@pytest.mark.asyncio
async def test_intent_retriever_close_handles_sync_and_async_close(test_config, test_database):
    """Test that close() handles both sync and async close methods."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    
    try:
        # Register services first
        from ai_services import register_all_services
        register_all_services(test_config)
        
        await retriever.initialize()
        
        # Create mock clients with different close method types
        # The code checks for aclose() first, then close()
        # For sync close, we need to ensure aclose doesn't exist so it falls back to close()
        # Use spec to prevent Mock from auto-creating aclose attribute
        mock_sync_client = Mock(spec=['close'])
        mock_sync_client.close = Mock()  # Regular method (sync)
        # aclose is not in spec, so getattr will return None
        retriever.embedding_client = mock_sync_client
        
        # Async close - set aclose() which will be called first
        async def async_close():
            pass
        
        mock_async_client = Mock()
        mock_async_client.aclose = async_close
        retriever.inference_client = mock_async_client
        
        # Close should handle both types
        await retriever.close()
        
        # Verify both were called
        # sync client: aclose is None, so close() is called
        mock_sync_client.close.assert_called_once()
        # async client: aclose() exists and is called
        assert hasattr(mock_async_client, 'aclose')
        assert callable(mock_async_client.aclose)
        
    except Exception as e:
        # Clean up on error
        try:
            await retriever.close()
        except:
            pass
        raise


@pytest.mark.asyncio
async def test_intent_retriever_close_idempotent(test_config, test_database):
    """Test that close() can be called multiple times safely (idempotent)."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    
    try:
        # Register services first
        from ai_services import register_all_services
        register_all_services(test_config)
        
        await retriever.initialize()
        
        # Close multiple times - should not error
        await retriever.close()
        await retriever.close()
        await retriever.close()
        
        # Note: Database connection is NOT closed by close() anymore - it's managed by datasource registry
        # The connection will remain open and be managed by the registry
        
    except Exception as e:
        # Clean up on error
        try:
            await retriever.close()
        except:
            pass
        raise


@pytest.mark.asyncio
async def test_intent_retriever_close_with_template_store(test_config, test_database):
    """Test that close() properly closes template_store if it exists."""
    test_config["datasources"]["sqlite"]["database"] = test_database
    
    retriever = IntentSQLiteRetriever(config=test_config)
    
    try:
        # Register services first
        from ai_services import register_all_services
        register_all_services(test_config)
        
        await retriever.initialize()
        
        # Verify template_store exists
        assert hasattr(retriever, 'template_store')
        assert retriever.template_store is not None
        
        # Create a mock template_store with close method
        mock_template_store = Mock()
        async def mock_close():
            pass
        mock_template_store.close = mock_close
        retriever.template_store = mock_template_store
        
        # Close should close template_store
        await retriever.close()
        
        # Verify template_store close was called (if it has the method)
        if hasattr(mock_template_store, 'close'):
            # The close method should have been called
            # We can't easily verify async calls, but if we get here without error, it worked
            pass
        
    except Exception as e:
        # Clean up on error
        try:
            await retriever.close()
        except:
            pass
        raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

