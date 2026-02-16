"""
Test Admin Integration with SQLite Backend
==========================================

This script tests the admin endpoints with a running server using SQLite backend.
Make sure the server is running with SQLite configured before executing this test.

Prerequisites:
1. Server must be running on http://localhost:3000
2. Authentication must be enabled in the server configuration
3. SQLite backend must be configured (backend.type = "sqlite")
4. Admin user must exist and be accessible

Note: This test mirrors test_admin_integration.py but ensures SQLite backend is used.
"""

import asyncio
import aiohttp
import logging
import time
import pytest
from typing import Optional
import os
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load server port from config
def get_server_url() -> str:
    """Get server URL from config file"""
    try:
        import yaml
        # Look for config.yaml in the config directory
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent
        config_path = project_root / "config" / "config.yaml"

        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                port = config.get('general', {}).get('port', 3000)

                # Verify SQLite is configured
                backend_type = config.get('internal_services', {}).get('backend', {}).get('type')
                if backend_type != 'sqlite':
                    logger.warning(f"Backend is configured as '{backend_type}', expected 'sqlite'")
                    logger.warning("This test is designed for SQLite backend testing")

                return f"http://localhost:{port}"
    except Exception as e:
        logger.warning(f"Failed to read config file: {e}")

    # Fallback to default
    return "http://localhost:3000"

# Server configuration
SERVER_URL = get_server_url()
logger.info(f"Using server URL: {SERVER_URL}")
logger.info("NOTE: This test validates SQLite backend functionality")
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"

# Check environment variable for password
env_password = os.getenv('ORBIT_DEFAULT_ADMIN_PASSWORD')
if env_password:
    DEFAULT_PASSWORD = env_password
    logger.info(f"Using admin password from environment variable: {DEFAULT_PASSWORD[:3]}***")
else:
    logger.info("Using default admin password: admin123")


class AdminTesterSQLite:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.created_api_keys = []  # Track created API keys for cleanup
        self.created_prompts = []   # Track created prompts for cleanup

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Cleanup created resources
        await self.cleanup_resources()
        if self.session:
            await self.session.close()

    def _get_headers(self, include_auth: bool = True) -> dict:
        """Get headers with optional authentication"""
        headers = {"Content-Type": "application/json"}
        if include_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def check_auth_enabled(self) -> bool:
        """Check if authentication is enabled on the server"""
        try:
            async with self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": "test", "password": "test"},
                headers={"Content-Type": "application/json"},
                timeout=5
            ) as response:
                if response.status == 401:
                    logger.info("✓ Authentication is enabled on server")
                    return True
                elif response.status == 404:
                    logger.info("✓ Authentication is disabled on server")
                    return False
                elif response.status == 503:
                    logger.info("✓ Authentication service not available (may be disabled)")
                    return False
                else:
                    logger.info(f"Authentication status unclear (got {response.status}), assuming enabled")
                    return True
        except Exception as e:
            logger.error(f"Error checking auth status: {str(e)}")
            return True

    async def authenticate(self) -> bool:
        """Authenticate and get a token (only if auth is enabled)"""
        logger.info("=== Checking Authentication Status (SQLite Backend) ===")

        # First check if auth is enabled
        auth_enabled = await self.check_auth_enabled()

        if not auth_enabled:
            logger.info("✓ Authentication is disabled - proceeding without token")
            return True

        logger.info("=== Authenticating for Admin Tests ===")

        data = {
            "username": DEFAULT_USERNAME,
            "password": DEFAULT_PASSWORD
        }

        try:
            async with self.session.post(
                f"{self.base_url}/auth/login",
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    self.token = result.get("token")
                    if self.token:
                        logger.info(f"✓ Authentication successful with SQLite backend. Token: {self.token[:8]}...")
                        return True
                    else:
                        logger.error("✗ Authentication response missing token")
                        return False
                else:
                    error = await response.text()
                    logger.error(f"✗ Authentication failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ Authentication error: {str(e)}")
            return False

    async def cleanup_resources(self) -> None:
        """Clean up created resources"""
        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.warning("Cannot clean up resources: no authentication token")
            return

        logger.info("=== Cleaning up created resources (SQLite) ===")

        # Clean up API keys
        for api_key in self.created_api_keys:
            try:
                async with self.session.delete(
                    f"{self.base_url}/admin/api-keys/{api_key}",
                    headers=self._get_headers(),
                    timeout=10
                ) as response:
                    if response.status == 200:
                        logger.info(f"✓ Cleaned up API key: ***{api_key[-4:]}")
                    else:
                        logger.warning(f"Failed to clean up API key: ***{api_key[-4:]}")
            except Exception as e:
                logger.warning(f"Error cleaning up API key: {str(e)}")

        # Clean up prompts
        for prompt_id in self.created_prompts:
            try:
                async with self.session.delete(
                    f"{self.base_url}/admin/prompts/{prompt_id}",
                    headers=self._get_headers(),
                    timeout=10
                ) as response:
                    if response.status == 200:
                        logger.info(f"✓ Cleaned up prompt: {prompt_id}")
                    else:
                        logger.warning(f"Failed to clean up prompt: {prompt_id}")
            except Exception as e:
                logger.warning(f"Error cleaning up prompt: {str(e)}")

    async def test_sqlite_backend_verification(self) -> bool:
        """Verify that the server is actually using SQLite backend"""
        logger.info("\\n=== Verifying SQLite Backend ===")

        # Check if orbit.db file exists in project root
        try:
            script_dir = Path(__file__).parent
            project_root = script_dir.parent.parent
            db_path = project_root / "orbit.db"

            if db_path.exists():
                logger.info(f"✓ SQLite database file found: {db_path}")
                # Check file size to ensure it's being used
                size = db_path.stat().st_size
                logger.info(f"  Database size: {size} bytes")
                return True
            else:
                logger.warning(f"✗ SQLite database file not found at: {db_path}")
                logger.warning("  Server may not be using SQLite backend")
                return False
        except Exception as e:
            logger.error(f"Error checking SQLite database: {str(e)}")
            return False

    async def test_create_api_key(self) -> bool:
        """Test creating a new API key with SQLite backend"""
        logger.info("\\n=== Testing API Key Creation (SQLite) ===")

        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.error("✗ No authentication token available (auth is enabled)")
            return False

        existing_adapter = "qa-sql"

        data = {
            "adapter_name": existing_adapter,
            "client_name": "Test Client SQLite",
            "notes": "Created by SQLite integration test"
        }

        logger.info(f"Creating API key for adapter: {existing_adapter}")

        try:
            async with self.session.post(
                f"{self.base_url}/admin/api-keys",
                json=data,
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    api_key = result.get("api_key")
                    if api_key:
                        self.created_api_keys.append(api_key)
                        logger.info(f"✓ API key created in SQLite: ***{api_key[-4:]} for adapter '{existing_adapter}'")
                        return True
                    else:
                        logger.error("✗ API key creation response missing api_key")
                        return False
                elif response.status == 503:
                    error = await response.text()
                    logger.info(f"✓ Expected response in inference-only mode: {error}")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"✗ API key creation failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ API key creation error: {str(e)}")
            return False

    async def test_create_system_prompt(self) -> bool:
        """Test creating a system prompt with SQLite backend"""
        logger.info("\\n=== Testing System Prompt Creation (SQLite) ===")

        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.error("✗ No authentication token available (auth is enabled)")
            return False

        unique_name = f"test_prompt_sqlite_{int(time.time())}"

        data = {
            "name": unique_name,
            "prompt": "You are a helpful assistant created for SQLite testing purposes.",
            "version": "1.0"
        }

        logger.info(f"Creating system prompt: {unique_name}")

        try:
            async with self.session.post(
                f"{self.base_url}/admin/prompts",
                json=data,
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result.get("id")
                    if prompt_id:
                        self.created_prompts.append(prompt_id)
                        logger.info(f"✓ System prompt created in SQLite: {prompt_id} ('{unique_name}')")
                        return True
                    else:
                        logger.error("✗ System prompt creation response missing id")
                        return False
                elif response.status == 503:
                    error = await response.text()
                    logger.info(f"✓ Expected response in inference-only mode: {error}")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"✗ System prompt creation failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ System prompt creation error: {str(e)}")
            return False

    async def test_list_api_keys(self) -> bool:
        """Test listing API keys from SQLite"""
        logger.info("\\n=== Testing API Key Listing (SQLite) ===")

        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.error("✗ No authentication token available (auth is enabled)")
            return False

        try:
            async with self.session.get(
                f"{self.base_url}/admin/api-keys",
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✓ Listed {len(result)} API keys from SQLite")

                    if isinstance(result, list):
                        for key in result:
                            if not all(field in key for field in ["_id", "api_key", "adapter_name"]):
                                logger.warning("API key response missing expected fields")
                                break
                        else:
                            logger.info("✓ API key response format is correct")

                    return True
                elif response.status == 503:
                    error = await response.text()
                    logger.info(f"✓ Expected response in inference-only mode: {error}")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"✗ API key listing failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ API key listing error: {str(e)}")
            return False


# Pytest test functions
@pytest.mark.asyncio
async def test_sqlite_backend_admin_operations():
    """Test complete admin operations flow with SQLite backend"""
    async with AdminTesterSQLite(SERVER_URL) as tester:
        # Verify SQLite backend
        assert await tester.test_sqlite_backend_verification(), "SQLite backend verification failed"

        # Authenticate
        assert await tester.authenticate(), "Admin authentication failed"

        # Test API key operations
        assert await tester.test_create_api_key(), "API key creation failed"
        assert await tester.test_list_api_keys(), "API key listing failed"

        # Test system prompt operations
        assert await tester.test_create_system_prompt(), "System prompt creation failed"


# Main function for standalone execution
async def main():
    """Main test function for standalone execution"""
    async with AdminTesterSQLite(SERVER_URL) as tester:
        logger.info(f"Testing admin endpoints with SQLite backend against: {SERVER_URL}")
        logger.info("=" * 60)

        tests = [
            ("SQLite Backend Verification", tester.test_sqlite_backend_verification),
            ("Authentication", tester.authenticate),
            ("API Key Creation", tester.test_create_api_key),
            ("API Key Listing", tester.test_list_api_keys),
            ("System Prompt Creation", tester.test_create_system_prompt),
        ]

        passed = 0
        failed = 0

        for test_name, test_func in tests:
            try:
                logger.info(f"\\n--- Running {test_name} ---")
                if await test_func():
                    passed += 1
                    logger.info(f"✅ {test_name} PASSED")
                else:
                    failed += 1
                    logger.error(f"❌ {test_name} FAILED")
            except Exception as e:
                logger.error(f"💥 {test_name} CRASHED: {str(e)}")
                failed += 1

        logger.info("\\n" + "=" * 60)
        logger.info(f"SQLite admin tests completed: {passed} passed, {failed} failed")

        if failed == 0:
            logger.info("✅ All SQLite admin tests passed!")
        else:
            logger.error("❌ Some SQLite admin tests failed")
            logger.info("\\nTroubleshooting tips:")
            logger.info("1. Make sure the server is running: python -m server.main")
            logger.info("2. Check that SQLite backend is configured (backend.type = 'sqlite')")
            logger.info("3. Verify orbit.db file exists in project root")
            logger.info("4. Ensure authentication is enabled in your config.yaml")
            logger.info("5. Check if the server is in inference-only mode")
            logger.info("6. Verify admin user credentials are correct")


if __name__ == "__main__":
    asyncio.run(main())
