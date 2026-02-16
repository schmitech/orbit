#!/usr/bin/env python3
"""
Test Elasticsearch Datasource Connectivity

This tests the datasource layer (not the adapter/retriever) to verify
that the Elasticsearch connection is working correctly with the datasource registry.

Run: pytest server/tests/test_elasticsearch_datasource.py -v
"""

import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv
from pytest_asyncio import fixture

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from config.config_manager import load_config
from datasources.registry import get_registry

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    load_dotenv(env_path)


@fixture(scope="function")
async def elasticsearch_config():
    """Fixture to provide Elasticsearch configuration."""

    # Check required environment variables
    node = os.getenv('DATASOURCE_ELASTICSEARCH_NODE')
    username = os.getenv('DATASOURCE_ELASTICSEARCH_USERNAME')
    password = os.getenv('DATASOURCE_ELASTICSEARCH_PASSWORD')

    if not all([node, username, password]):
        pytest.skip("Missing required Elasticsearch environment variables")

    # Load config using the config manager (which does env var substitution)
    config_path = PROJECT_ROOT / 'config' / 'config.yaml'
    config = load_config(str(config_path))

    return {
        'config': config,
        'node': node,
        'username': username,
        'has_password': bool(password)
    }


@fixture(scope="function")
async def elasticsearch_datasource(elasticsearch_config):
    """Fixture to create and cleanup Elasticsearch datasource."""

    registry = get_registry()

    # Create full config structure that the datasource expects
    full_config = {
        'datasources': elasticsearch_config['config'].get('datasources', {})
    }

    # Get or create the datasource
    datasource = registry.get_or_create_datasource(
        datasource_name='elasticsearch',
        config=full_config,
        logger_instance=None
    )

    if not datasource:
        pytest.skip("Failed to create datasource instance")

    # Initialize the connection
    await datasource.initialize()

    if not datasource.is_initialized:
        pytest.skip("Datasource failed to initialize")

    # Yield the datasource for use in tests
    yield datasource

    # Cleanup
    try:
        await datasource.close()
    except Exception as e:
        print(f"Error closing datasource: {e}")


@pytest.mark.asyncio
async def test_direct_connection(elasticsearch_config):
    """Test direct Elasticsearch connection (validates credentials work)."""
    from elasticsearch import AsyncElasticsearch

    node = elasticsearch_config['node']
    username = elasticsearch_config['username']
    password = os.getenv('DATASOURCE_ELASTICSEARCH_PASSWORD')

    print("\n=== Testing Direct Connection ===")
    print(f"Node: {node}")
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password) if password else 'NOT SET'}")

    client = AsyncElasticsearch(
        node,
        basic_auth=(username, password),
        verify_certs=True,
        request_timeout=30,
        retry_on_timeout=True,
        max_retries=3
    )

    try:
        # Test ping
        ping_result = await client.ping()
        assert ping_result, "Elasticsearch ping failed"
        print("✓ Ping successful")

        # Get cluster info
        info = await client.info()
        assert 'cluster_name' in info, "Failed to get cluster info"

        print(f"✓ Connected to cluster: {info.get('cluster_name')}")
        print(f"  Version: {info.get('version', {}).get('number')}")

    finally:
        await client.close()


@pytest.mark.asyncio
async def test_datasource_creation(elasticsearch_config):
    """Test that datasource can be created with correct configuration."""
    from datasources.registry import get_registry

    print("\n=== Testing Datasource Creation ===")

    registry = get_registry()

    # Create full config structure
    full_config = {
        'datasources': elasticsearch_config['config'].get('datasources', {})
    }

    # Create datasource
    datasource = registry.get_or_create_datasource(
        datasource_name='elasticsearch',
        config=full_config,
        logger_instance=None
    )

    assert datasource is not None, "Failed to create datasource instance"
    print(f"✓ Datasource instance created: {type(datasource).__name__}")

    # Check configuration was loaded correctly
    assert datasource.node == elasticsearch_config['node'], "Node URL mismatch"
    assert datasource.username == elasticsearch_config['username'], "Username mismatch"
    assert datasource.password, "Password not set"

    print(f"  Node: {datasource.node}")
    print(f"  Username: {datasource.username}")
    print(f"  Has password: {bool(datasource.password)}")


@pytest.mark.asyncio
async def test_datasource_connection(elasticsearch_datasource):
    """Test Elasticsearch datasource connection and operations."""

    print("\n=== Testing Datasource Connection ===")

    # Verify datasource is initialized
    assert elasticsearch_datasource.is_initialized, "Datasource not initialized"
    print("✓ Datasource initialized")

    # Get cluster info
    cluster_info = await elasticsearch_datasource.client.info()
    assert 'cluster_name' in cluster_info, "Failed to get cluster info"

    print("✓ Connected to Elasticsearch cluster")
    print(f"  Cluster name: {cluster_info.get('cluster_name', 'unknown')}")
    print(f"  Version: {cluster_info.get('version', {}).get('number', 'unknown')}")
    print(f"  Tagline: {cluster_info.get('tagline', 'unknown')}")


@pytest.mark.asyncio
async def test_datasource_health_check(elasticsearch_datasource):
    """Test datasource health check functionality."""

    print("\n=== Testing Health Check ===")

    is_healthy = await elasticsearch_datasource.health_check()
    assert is_healthy, "Health check failed"

    print("✓ Health check passed")


@pytest.mark.asyncio
async def test_datasource_query(elasticsearch_datasource):
    """Test querying indices through the datasource."""

    print("\n=== Testing Query Operations ===")

    # List indices
    indices = await elasticsearch_datasource.client.cat.indices(format='json')

    # ES 9.x returns ListApiResponse, convert to list for testing
    indices_list = list(indices) if hasattr(indices, '__iter__') else []
    assert len(indices_list) > 0, "Failed to get indices list"

    print(f"✓ Query successful - found {len(indices_list)} indices")

    if indices_list:
        print("\nSample indices:")
        for idx in indices_list[:5]:
            print(f"  - {idx.get('index')}: {idx.get('docs.count', 0)} docs")


@pytest.mark.asyncio
async def test_config_loading():
    """Test that config manager properly loads and substitutes environment variables."""

    print("\n=== Testing Config Loading ===")

    # Load config
    config_path = PROJECT_ROOT / 'config' / 'config.yaml'
    config = load_config(str(config_path))

    # Check Elasticsearch config
    es_config = config.get('datasources', {}).get('elasticsearch', {})
    assert es_config, "Elasticsearch config not found"

    print("✓ Config loaded successfully")
    print(f"  Node: {es_config.get('node')}")
    print(f"  Verify certs: {es_config.get('verify_certs')}")
    print(f"  Timeout: {es_config.get('timeout')}")

    # Check auth config
    auth_config = es_config.get('auth', {})
    assert 'username' in auth_config, "Username not in auth config"
    assert 'password' in auth_config, "Password not in auth config"

    # Verify environment variables were substituted (not ${VAR} format)
    username = auth_config.get('username', '')
    password = auth_config.get('password', '')

    assert not username.startswith('${'), "Username not substituted"
    assert not password.startswith('${'), "Password not substituted"
    assert username, "Username is empty after substitution"
    assert password, "Password is empty after substitution"

    print("✓ Environment variables properly substituted")
    print(f"  Username: {username}")
    print(f"  Password: {'*' * len(password)}")


if __name__ == "__main__":
    # Run with pytest when executed directly
    pytest.main([__file__, '-v', '-s'])
