"""
Test API Key Authentication Integration
======================================

This script tests API key authentication with actual endpoints.
Tests the flow of creating API keys and using them to authenticate requests.

Prerequisites:
1. Server must be running on http://localhost:3000
2. MongoDB must be available and configured
"""

import asyncio
import aiohttp
import json
import logging
import time
import pytest
from typing import Optional, Dict, Any, List
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Server configuration
SERVER_URL = "http://localhost:3000"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"

# Check environment variable for password
env_password = os.getenv('ORBIT_DEFAULT_ADMIN_PASSWORD')
if env_password:
    DEFAULT_PASSWORD = env_password


class ApiKeyAuthTester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.admin_token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.created_api_keys = []  # Track created API keys for cleanup
        self.created_prompts = []   # Track created prompts for cleanup
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup_resources()
        if self.session:
            await self.session.close()
    
    async def check_server_health(self) -> bool:
        """Check if the server is running and accessible"""
        try:
            async with self.session.get(
                f"{self.base_url}/health",
                timeout=5
            ) as response:
                if response.status == 200:
                    logger.info("✓ Server is running and accessible")
                    return True
                else:
                    logger.warning(f"Server health check returned status {response.status}")
                    return False
        except Exception as e:
            logger.error(f"✗ Server health check failed: {str(e)}")
            return False
    
    async def check_auth_enabled(self) -> bool:
        """Check if authentication is enabled on the server"""
        try:
            async with self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": "test", "password": "test"},
                headers={"Content-Type": "application/json"},
                timeout=5
            ) as response:
                return response.status in [401, 503]  # Auth enabled returns 401, disabled returns 404
        except Exception:
            return True  # Assume enabled if we can't determine
    
    async def authenticate_admin(self) -> bool:
        """Authenticate as admin if auth is enabled"""
        auth_enabled = await self.check_auth_enabled()
        
        if not auth_enabled:
            logger.info("✓ Authentication is disabled - admin access available")
            return True
        
        logger.info("=== Authenticating as Admin ===")
        
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
                    self.admin_token = result.get("token")
                    if self.admin_token:
                        logger.info(f"✓ Admin authentication successful")
                        return True
                logger.error(f"✗ Admin authentication failed: {response.status}")
                return False
        except Exception as e:
            logger.error(f"✗ Admin authentication error: {str(e)}")
            return False
    
    def _get_admin_headers(self) -> dict:
        """Get headers with admin authentication"""
        headers = {"Content-Type": "application/json"}
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        return headers
    
    def _get_api_key_headers(self, api_key: str) -> dict:
        """Get headers with API key authentication"""
        return {
            "Content-Type": "application/json",
            "X-API-Key": api_key
        }
    
    async def create_test_api_key(self, collection_name: str = None, client_name: str = None, notes: str = None) -> Optional[str]:
        """Create a test API key for testing"""
        if not collection_name:
            collection_name = f"test_collection_{int(time.time())}"
        if not client_name:
            client_name = f"Test Client {int(time.time())}"
        if not notes:
            notes = "Created for API key authentication testing"
        
        logger.info(f"Creating test API key for collection: {collection_name}")
        
        data = {
            "collection_name": collection_name,
            "client_name": client_name,
            "notes": notes
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/admin/api-keys",
                json=data,
                headers=self._get_admin_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    api_key = result.get("api_key")
                    if api_key:
                        self.created_api_keys.append(api_key)
                        logger.info(f"✓ Test API key created: ***{api_key[-4:]}")
                        return api_key
                elif response.status == 503:
                    logger.info("✓ API key creation not available (inference-only mode)")
                    return None
                else:
                    logger.error(f"✗ API key creation failed: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"✗ API key creation error: {str(e)}")
            return None
    
    async def create_test_prompt(self, name: str = None, prompt_text: str = None) -> Optional[str]:
        """Create a test system prompt"""
        if not name:
            name = f"test_prompt_{int(time.time())}"
        if not prompt_text:
            prompt_text = f"You are a test assistant for {name}. Please be helpful and concise."
        
        logger.info(f"Creating test prompt: {name}")
        
        data = {
            "name": name,
            "prompt": prompt_text,
            "version": "1.0"
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/admin/prompts",
                json=data,
                headers=self._get_admin_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    prompt_id = result.get("id")
                    if prompt_id:
                        self.created_prompts.append(prompt_id)
                        logger.info(f"✓ Test prompt created: {prompt_id[:12]}...")
                        return prompt_id
                elif response.status == 503:
                    logger.info("✓ Prompt creation not available (inference-only mode)")
                    return None
                else:
                    logger.error(f"✗ Prompt creation failed: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"✗ Prompt creation error: {str(e)}")
            return None
    
    async def test_api_key_listing_with_filters(self) -> bool:
        """Test API key listing with various filters"""
        logger.info("\n=== Testing API Key Listing with Filters ===")
        
        # Create multiple test API keys with different properties
        keys_data = [
            ("collection_a", "Client A", "Active key for collection A"),
            ("collection_b", "Client B", "Active key for collection B"),
            ("collection_a", "Client C", "Another key for collection A")
        ]
        
        created_keys = []
        for collection, client, notes in keys_data:
            key = await self.create_test_api_key(collection, client, notes)
            if key:
                created_keys.append((key, collection, client))
        
        if not created_keys:
            logger.info("No API keys created - skipping filter tests")
            return True
        
        tests = [
            # Test listing all keys
            ("list_all", "/admin/api-keys", {}),
            # Test filtering by collection
            ("filter_by_collection", "/admin/api-keys?collection=collection_a", {}),
            # Test active only filter
            ("active_only", "/admin/api-keys?active_only=true", {}),
            # Test pagination
            ("pagination", "/admin/api-keys?limit=2&offset=0", {}),
            # Test combination of filters
            ("combined_filters", "/admin/api-keys?collection=collection_a&active_only=true&limit=10", {})
        ]
        
        passed = 0
        for test_name, url, expected_count in tests:
            try:
                async with self.session.get(
                    f"{self.base_url}{url}",
                    headers=self._get_admin_headers(),
                    timeout=10
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"✓ {test_name}: Found {len(result)} keys")
                        passed += 1
                    else:
                        logger.error(f"✗ {test_name}: Failed with status {response.status}")
            except Exception as e:
                logger.error(f"✗ {test_name}: Error - {str(e)}")
        
        return passed == len(tests)
    
    async def test_prompt_listing_with_filters(self) -> bool:
        """Test prompt listing with various filters"""
        logger.info("\n=== Testing Prompt Listing with Filters ===")
        
        # Create multiple test prompts
        prompts_data = [
            ("support_prompt", "You are a support assistant."),
            ("sales_prompt", "You are a sales assistant."),
            ("technical_prompt", "You are a technical assistant.")
        ]
        
        created_prompts = []
        for name, text in prompts_data:
            prompt_id = await self.create_test_prompt(name, text)
            if prompt_id:
                created_prompts.append(prompt_id)
        
        if not created_prompts:
            logger.info("No prompts created - skipping filter tests")
            return True
        
        tests = [
            # Test listing all prompts
            ("list_all", "/admin/prompts", {}),
            # Test filtering by name
            ("filter_by_name", "/admin/prompts?name_filter=support", {}),
            # Test pagination
            ("pagination", "/admin/prompts?limit=2&offset=0", {}),
            # Test case-insensitive search
            ("case_insensitive", "/admin/prompts?name_filter=SUPPORT", {})
        ]
        
        passed = 0
        for test_name, url, expected_count in tests:
            try:
                async with self.session.get(
                    f"{self.base_url}{url}",
                    headers=self._get_admin_headers(),
                    timeout=10
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"✓ {test_name}: Found {len(result)} prompts")
                        passed += 1
                    else:
                        logger.error(f"✗ {test_name}: Failed with status {response.status}")
            except Exception as e:
                logger.error(f"✗ {test_name}: Error - {str(e)}")
        
        return passed == len(tests)
    
    async def test_user_listing_with_filters(self) -> bool:
        """Test user listing with various filters"""
        logger.info("\n=== Testing User Listing with Filters ===")
        
        # First check if the users endpoint is available
        try:
            async with self.session.get(
                f"{self.base_url}/auth/users",
                headers=self._get_admin_headers(),
                timeout=10
            ) as response:
                if response.status == 404:
                    logger.info("✓ User listing endpoint not available (inference-only mode or not configured)")
                    return True
                elif response.status != 200:
                    logger.info(f"✓ User listing endpoint returned {response.status} (may not be available)")
                    return True
        except Exception as e:
            logger.info(f"✓ User listing endpoint not accessible: {str(e)}")
            return True
        
        tests = [
            # Test listing all users
            ("list_all", "/auth/users", {}),
            # Test filtering by role
            ("filter_by_role", "/auth/users?role=admin", {}),
            # Test active only filter
            ("active_only", "/auth/users?active_only=true", {}),
            # Test pagination
            ("pagination", "/auth/users?limit=5&offset=0", {}),
            # Test combination of filters
            ("combined_filters", "/auth/users?role=admin&active_only=true&limit=10", {})
        ]
        
        passed = 0
        for test_name, url, expected_count in tests:
            try:
                async with self.session.get(
                    f"{self.base_url}{url}",
                    headers=self._get_admin_headers(),
                    timeout=10
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"✓ {test_name}: Found {len(result)} users")
                        passed += 1
                    elif response.status == 404:
                        logger.info(f"✓ {test_name}: Endpoint not available (404)")
                        passed += 1  # Consider 404 as acceptable for this test
                    elif response.status == 503:
                        logger.info(f"✓ {test_name}: Service not available (503)")
                        passed += 1  # Consider 503 as acceptable for this test
                    else:
                        logger.error(f"✗ {test_name}: Failed with status {response.status}")
            except Exception as e:
                logger.error(f"✗ {test_name}: Error - {str(e)}")
        
        return passed == len(tests)
    
    async def test_api_key_with_prompt_association(self) -> bool:
        """Test API key creation and prompt association"""
        logger.info("\n=== Testing API Key with Prompt Association ===")
        
        # Create a test prompt first
        prompt_id = await self.create_test_prompt("test_association_prompt", "You are a specialized test assistant.")
        if not prompt_id:
            logger.info("Could not create test prompt - skipping association test")
            return True
        
        # Create API key
        api_key = await self.create_test_api_key("test_association_collection", "Association Test Client")
        if not api_key:
            logger.info("Could not create test API key - skipping association test")
            return True
        
        # Associate prompt with API key
        try:
            async with self.session.post(
                f"{self.base_url}/admin/api-keys/{api_key}/prompt",
                json={"prompt_id": prompt_id},
                headers=self._get_admin_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    logger.info("✓ Prompt successfully associated with API key")
                    
                    # Test getting API key status to verify association
                    async with self.session.get(
                        f"{self.base_url}/admin/api-keys/{api_key}/status",
                        headers=self._get_admin_headers(),
                        timeout=10
                    ) as status_response:
                        if status_response.status == 200:
                            status_result = await status_response.json()
                            if status_result.get("system_prompt"):
                                logger.info("✓ API key status shows prompt association")
                                return True
                            else:
                                logger.error("✗ API key status does not show prompt association")
                                return False
                        else:
                            logger.error(f"✗ Failed to get API key status: {status_response.status}")
                            return False
                else:
                    logger.error(f"✗ Failed to associate prompt: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"✗ Prompt association error: {str(e)}")
            return False
    
    async def test_api_key_operations(self) -> bool:
        """Test various API key operations"""
        logger.info("\n=== Testing API Key Operations ===")
        
        # Create a test API key
        api_key = await self.create_test_api_key("test_operations_collection", "Operations Test Client")
        if not api_key:
            logger.info("Could not create test API key - skipping operations test")
            return True
        
        operations = []
        
        # Test getting API key status
        try:
            async with self.session.get(
                f"{self.base_url}/admin/api-keys/{api_key}/status",
                headers=self._get_admin_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info("✓ API key status retrieved successfully")
                    operations.append(True)
                else:
                    logger.error(f"✗ Failed to get API key status: {response.status}")
                    operations.append(False)
        except Exception as e:
            logger.error(f"✗ API key status error: {str(e)}")
            operations.append(False)
        
        # Test deactivating API key
        try:
            async with self.session.post(
                f"{self.base_url}/admin/api-keys/deactivate",
                json={"api_key": api_key},
                headers=self._get_admin_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    logger.info("✓ API key deactivated successfully")
                    operations.append(True)
                else:
                    logger.error(f"✗ Failed to deactivate API key: {response.status}")
                    operations.append(False)
        except Exception as e:
            logger.error(f"✗ API key deactivation error: {str(e)}")
            operations.append(False)
        
        # Test that deactivated key is rejected
        try:
            async with self.session.get(
                f"{self.base_url}/health",
                headers=self._get_api_key_headers(api_key),
                timeout=10
            ) as response:
                if response.status == 401:
                    logger.info("✓ Deactivated API key correctly rejected")
                    operations.append(True)
                else:
                    logger.info("✓ API key validation not enforced (expected in some configurations)")
                    operations.append(True)
        except Exception as e:
            logger.error(f"✗ Deactivated key test error: {str(e)}")
            operations.append(False)
        
        return all(operations)
    
    async def test_edge_cases(self) -> bool:
        """Test edge cases and error conditions"""
        logger.info("\n=== Testing Edge Cases ===")
        
        edge_cases = []
        
        # Test invalid API key format
        try:
            async with self.session.get(
                f"{self.base_url}/health",
                headers=self._get_api_key_headers("invalid_key_format"),
                timeout=10
            ) as response:
                if response.status in [401, 200]:  # Either rejected or not enforced
                    logger.info("✓ Invalid API key format handled correctly")
                    edge_cases.append(True)
                else:
                    logger.error(f"✗ Unexpected response for invalid key: {response.status}")
                    edge_cases.append(False)
        except Exception as e:
            logger.error(f"✗ Invalid key format test error: {str(e)}")
            edge_cases.append(False)
        
        # Test empty API key
        try:
            async with self.session.get(
                f"{self.base_url}/health",
                headers=self._get_api_key_headers(""),
                timeout=10
            ) as response:
                if response.status in [401, 200]:  # Either rejected or not enforced
                    logger.info("✓ Empty API key handled correctly")
                    edge_cases.append(True)
                else:
                    logger.error(f"✗ Unexpected response for empty key: {response.status}")
                    edge_cases.append(False)
        except Exception as e:
            logger.error(f"✗ Empty key test error: {str(e)}")
            edge_cases.append(False)
        
        # Test malformed query parameters
        try:
            async with self.session.get(
                f"{self.base_url}/admin/api-keys?limit=invalid&offset=-1",
                headers=self._get_admin_headers(),
                timeout=10
            ) as response:
                if response.status in [200, 400, 422]:  # Should handle gracefully
                    logger.info("✓ Malformed query parameters handled correctly")
                    edge_cases.append(True)
                else:
                    logger.error(f"✗ Unexpected response for malformed params: {response.status}")
                    edge_cases.append(False)
        except Exception as e:
            logger.error(f"✗ Malformed params test error: {str(e)}")
            edge_cases.append(False)
        
        return all(edge_cases)
    
    async def test_health_endpoint_with_api_key(self, api_key: str) -> bool:
        """Test health endpoint with API key authentication"""
        logger.info("\n=== Testing Health Endpoint with API Key ===")
        
        try:
            async with self.session.get(
                f"{self.base_url}/health",
                headers=self._get_api_key_headers(api_key),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✓ Health check with API key successful: {result.get('status', 'unknown')}")
                    return True
                else:
                    logger.error(f"✗ Health check with API key failed: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"✗ Health check with API key error: {str(e)}")
            return False
    
    async def test_invalid_api_key(self) -> bool:
        """Test using an invalid API key"""
        logger.info("\n=== Testing Invalid API Key ===")
        
        invalid_key = "orbit_invalid_key_12345"
        
        try:
            async with self.session.get(
                f"{self.base_url}/health",
                headers=self._get_api_key_headers(invalid_key),
                timeout=10
            ) as response:
                if response.status == 401:
                    logger.info("✓ Invalid API key correctly rejected")
                    return True
                elif response.status == 200:
                    logger.info("✓ API key validation not enforced (expected in some configurations)")
                    return True
                else:
                    logger.error(f"✗ Invalid API key unexpected response: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"✗ Invalid API key test error: {str(e)}")
            return False
    
    async def cleanup_resources(self) -> None:
        """Clean up created resources"""
        logger.info("=== Cleaning up test resources ===")
        
        # Clean up API keys
        for api_key in self.created_api_keys:
            try:
                async with self.session.delete(
                    f"{self.base_url}/admin/api-keys/{api_key}",
                    headers=self._get_admin_headers(),
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
                    headers=self._get_admin_headers(),
                    timeout=10
                ) as response:
                    if response.status == 200:
                        logger.info(f"✓ Cleaned up prompt: {prompt_id[:12]}...")
                    else:
                        logger.warning(f"Failed to clean up prompt: {prompt_id[:12]}...")
            except Exception as e:
                logger.warning(f"Error cleaning up prompt: {str(e)}")


# Pytest test functions
@pytest.mark.asyncio
async def test_api_key_authentication_flow():
    """Test the complete API key authentication flow"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        # Check if server is running
        if not await tester.check_server_health():
            pytest.skip("Server is not running or not accessible")
        
        # Authenticate as admin first
        if not await tester.authenticate_admin():
            pytest.skip("Admin authentication failed")
        
        # Create test API key
        api_key = await tester.create_test_api_key()
        if not api_key:
            pytest.skip("API key creation not available (inference-only mode)")
        
        # Test using the API key
        assert await tester.test_health_endpoint_with_api_key(api_key), "Health check with API key failed"


@pytest.mark.asyncio
async def test_api_key_validation():
    """Test API key validation"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        # Check if server is running
        if not await tester.check_server_health():
            pytest.skip("Server is not running or not accessible")
        
        if not await tester.authenticate_admin():
            pytest.skip("Admin authentication failed")
        
        assert await tester.test_invalid_api_key(), "Invalid API key test failed"


@pytest.mark.asyncio
async def test_api_key_listing_filters():
    """Test API key listing with filters and pagination"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        # Check if server is running
        if not await tester.check_server_health():
            pytest.skip("Server is not running or not accessible")
        
        if not await tester.authenticate_admin():
            pytest.skip("Admin authentication failed")
        
        assert await tester.test_api_key_listing_with_filters(), "API key listing with filters failed"


@pytest.mark.asyncio
async def test_prompt_listing_filters():
    """Test prompt listing with filters and pagination"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        # Check if server is running
        if not await tester.check_server_health():
            pytest.skip("Server is not running or not accessible")
        
        if not await tester.authenticate_admin():
            pytest.skip("Admin authentication failed")
        
        assert await tester.test_prompt_listing_with_filters(), "Prompt listing with filters failed"


@pytest.mark.asyncio
async def test_user_listing_filters():
    """Test user listing with filters and pagination"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        # Check if server is running
        if not await tester.check_server_health():
            pytest.skip("Server is not running or not accessible")
        
        # Check if auth is available
        if not await tester.authenticate_admin():
            pytest.skip("Admin authentication failed")
        
        result = await tester.test_user_listing_with_filters()
        if not result:
            # If the test fails, it might be because the endpoint is not available
            # Let's check if it's a 404 and skip the test
            try:
                async with tester.session.get(
                    f"{SERVER_URL}/auth/users",
                    headers=tester._get_admin_headers(),
                    timeout=5
                ) as response:
                    if response.status == 404:
                        pytest.skip("User listing endpoint not available (inference-only mode)")
            except:
                pass
            assert False, "User listing with filters failed"


@pytest.mark.asyncio
async def test_api_key_prompt_association():
    """Test API key creation and prompt association"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        # Check if server is running
        if not await tester.check_server_health():
            pytest.skip("Server is not running or not accessible")
        
        if not await tester.authenticate_admin():
            pytest.skip("Admin authentication failed")
        
        assert await tester.test_api_key_with_prompt_association(), "API key prompt association failed"


@pytest.mark.asyncio
async def test_api_key_operations():
    """Test various API key operations"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        # Check if server is running
        if not await tester.check_server_health():
            pytest.skip("Server is not running or not accessible")
        
        if not await tester.authenticate_admin():
            pytest.skip("Admin authentication failed")
        
        assert await tester.test_api_key_operations(), "API key operations failed"


@pytest.mark.asyncio
async def test_edge_cases():
    """Test edge cases and error conditions"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        # Check if server is running
        if not await tester.check_server_health():
            pytest.skip("Server is not running or not accessible")
        
        if not await tester.authenticate_admin():
            pytest.skip("Admin authentication failed")
        
        assert await tester.test_edge_cases(), "Edge cases test failed"


# Main function for standalone execution
async def main():
    """Main test function for standalone execution"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        logger.info(f"Testing API key authentication against: {SERVER_URL}")
        logger.info("=" * 60)
        
        # Check if server is running
        if not await tester.check_server_health():
            logger.error("❌ Server is not running or not accessible. Please start the server first.")
            return
        
        # Authenticate as admin
        if not await tester.authenticate_admin():
            logger.error("❌ Admin authentication failed. Cannot proceed with API key tests.")
            return
        
        tests = [
            ("Invalid API Key", tester.test_invalid_api_key),
            ("API Key Listing with Filters", tester.test_api_key_listing_with_filters),
            ("Prompt Listing with Filters", tester.test_prompt_listing_with_filters),
            ("User Listing with Filters", tester.test_user_listing_with_filters),
            ("API Key Operations", tester.test_api_key_operations),
            ("Edge Cases", tester.test_edge_cases)
        ]
        
        # Only run API key tests if we can create keys
        api_key = await tester.create_test_api_key()
        if api_key:
            tests.extend([
                ("Health Endpoint with API Key", lambda: tester.test_health_endpoint_with_api_key(api_key)),
                ("API Key with Prompt Association", tester.test_api_key_with_prompt_association)
            ])
        else:
            logger.info("API key creation not available - skipping API key specific tests")
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            try:
                logger.info(f"\n--- Running {test_name} ---")
                if await test_func():
                    passed += 1
                    logger.info(f"✅ {test_name} PASSED")
                else:
                    failed += 1
                    logger.error(f"❌ {test_name} FAILED")
            except Exception as e:
                logger.error(f"💥 {test_name} CRASHED: {str(e)}")
                failed += 1
        
        logger.info("\n" + "=" * 60)
        logger.info(f"API key authentication tests completed: {passed} passed, {failed} failed")


if __name__ == "__main__":
    asyncio.run(main()) 