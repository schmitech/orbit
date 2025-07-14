"""
Test Admin Integration
======================

This script tests the admin endpoints with a running server.
Make sure the server is running before executing this test.

Prerequisites:
1. Server must be running on http://localhost:3000
2. Authentication must be enabled in the server configuration
3. MongoDB must be available and configured
4. Admin user must exist and be accessible
"""

import asyncio
import aiohttp
import json
import logging
import time
import pytest
from typing import Optional, Dict, Any
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
    logger.info(f"Using admin password from environment variable: {DEFAULT_PASSWORD[:3]}***")
else:
    logger.info("Using default admin password: admin123")


class AdminTester:
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
        # Only include auth header if we have a token and auth is requested
        if include_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    async def check_auth_enabled(self) -> bool:
        """Check if authentication is enabled on the server"""
        try:
            # Try to access the login endpoint to see if auth is enabled
            async with self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": "test", "password": "test"},
                headers={"Content-Type": "application/json"},
                timeout=5
            ) as response:
                if response.status == 401:
                    # Auth service is available, just wrong credentials
                    logger.info("✓ Authentication is enabled on server")
                    return True
                elif response.status == 404:
                    # Auth endpoints not found - auth is disabled
                    logger.info("✓ Authentication is disabled on server")
                    return False
                elif response.status == 503:
                    # Auth service not available
                    logger.info("✓ Authentication service not available (may be disabled)")
                    return False
                else:
                    logger.info(f"Authentication status unclear (got {response.status}), assuming enabled")
                    return True
        except Exception as e:
            logger.error(f"Error checking auth status: {str(e)}")
            # Assume auth is enabled if we can't determine
            return True

    async def authenticate(self) -> bool:
        """Authenticate and get a token (only if auth is enabled)"""
        logger.info("=== Checking Authentication Status ===")
        
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
                        logger.info(f"✓ Authentication successful. Token: {self.token[:8]}...")
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
        # If auth is enabled and we don't have a token, we can't clean up
        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.warning("Cannot clean up resources: no authentication token")
            return
        
        logger.info("=== Cleaning up created resources ===")
        
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
    
    async def test_create_api_key(self) -> bool:
        """Test creating a new API key"""
        logger.info("\n=== Testing API Key Creation ===")
        
        # Check if auth is enabled - if so, we need a token
        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.error("✗ No authentication token available (auth is enabled)")
            return False
        
        # Use an existing adapter from the configuration
        existing_adapter = "qa-vector-chroma"
        
        data = {
            "adapter_name": existing_adapter,
            "client_name": "Test Client",
            "notes": "Created by integration test"
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
                        logger.info(f"✓ API key created: ***{api_key[-4:]} for adapter '{existing_adapter}'")
                        return True
                    else:
                        logger.error("✗ API key creation response missing api_key")
                        return False
                elif response.status == 503:
                    error = await response.text()
                    logger.info(f"✓ Expected response in inference-only mode: {error}")
                    return True  # This is expected behavior
                else:
                    error = await response.text()
                    logger.error(f"✗ API key creation failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ API key creation error: {str(e)}")
            return False
    
    async def test_list_api_keys(self) -> bool:
        """Test listing API keys"""
        logger.info("\n=== Testing API Key Listing ===")
        
        # Check if auth is enabled - if so, we need a token
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
                    logger.info(f"✓ Listed {len(result)} API keys")
                    
                    # Verify response format
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
                    return True  # This is expected behavior
                else:
                    error = await response.text()
                    logger.error(f"✗ API key listing failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ API key listing error: {str(e)}")
            return False
    
    async def test_api_key_status(self) -> bool:
        """Test checking API key status"""
        logger.info("\n=== Testing API Key Status Check ===")
        
        # Check if auth is enabled - if so, we need a token
        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.error("✗ No authentication token available (auth is enabled)")
            return False
        
        if not self.created_api_keys:
            logger.info("✓ No API keys to check status (expected in inference-only mode)")
            return True
        
        api_key = self.created_api_keys[0]
        
        try:
            async with self.session.get(
                f"{self.base_url}/admin/api-keys/{api_key}/status",
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✓ Got API key status: {result}")
                    return True
                elif response.status == 503:
                    error = await response.text()
                    logger.info(f"✓ Expected response in inference-only mode: {error}")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"✗ API key status check failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ API key status check error: {str(e)}")
            return False
    
    async def test_create_system_prompt(self) -> bool:
        """Test creating a system prompt"""
        logger.info("\n=== Testing System Prompt Creation ===")
        
        # Check if auth is enabled - if so, we need a token
        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.error("✗ No authentication token available (auth is enabled)")
            return False
        
        # Use unique prompt name with timestamp
        unique_name = f"test_prompt_{int(time.time())}"
        
        data = {
            "name": unique_name,
            "prompt": "You are a helpful assistant created for testing purposes.",
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
                        logger.info(f"✓ System prompt created: {prompt_id} ('{unique_name}')")
                        return True
                    else:
                        logger.error("✗ System prompt creation response missing id")
                        return False
                elif response.status == 503:
                    error = await response.text()
                    logger.info(f"✓ Expected response in inference-only mode: {error}")
                    return True  # This is expected behavior
                else:
                    error = await response.text()
                    logger.error(f"✗ System prompt creation failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ System prompt creation error: {str(e)}")
            return False
    
    async def test_list_system_prompts(self) -> bool:
        """Test listing system prompts"""
        logger.info("\n=== Testing System Prompt Listing ===")
        
        # Check if auth is enabled - if so, we need a token
        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.error("✗ No authentication token available (auth is enabled)")
            return False
        
        try:
            async with self.session.get(
                f"{self.base_url}/admin/prompts",
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✓ Listed {len(result)} system prompts")
                    
                    # Verify response format
                    if isinstance(result, list):
                        for prompt in result:
                            if not all(field in prompt for field in ["_id", "name", "prompt"]):
                                logger.warning("System prompt response missing expected fields")
                                break
                        else:
                            logger.info("✓ System prompt response format is correct")
                    
                    return True
                elif response.status == 503:
                    error = await response.text()
                    logger.info(f"✓ Expected response in inference-only mode: {error}")
                    return True  # This is expected behavior
                else:
                    error = await response.text()
                    logger.error(f"✗ System prompt listing failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ System prompt listing error: {str(e)}")
            return False
    
    async def test_get_system_prompt(self) -> bool:
        """Test getting a specific system prompt"""
        logger.info("\n=== Testing System Prompt Retrieval ===")
        
        # Check if auth is enabled - if so, we need a token
        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.error("✗ No authentication token available (auth is enabled)")
            return False
        
        if not self.created_prompts:
            logger.info("✓ No system prompts to retrieve (expected in inference-only mode)")
            return True
        
        prompt_id = self.created_prompts[0]
        
        try:
            async with self.session.get(
                f"{self.base_url}/admin/prompts/{prompt_id}",
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✓ Retrieved system prompt: {result.get('name', 'Unknown')}")
                    return True
                elif response.status == 404:
                    logger.error("✗ System prompt not found")
                    return False
                elif response.status == 503:
                    error = await response.text()
                    logger.info(f"✓ Expected response in inference-only mode: {error}")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"✗ System prompt retrieval failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ System prompt retrieval error: {str(e)}")
            return False
    
    async def test_update_system_prompt(self) -> bool:
        """Test updating a system prompt"""
        logger.info("\n=== Testing System Prompt Update ===")
        
        # Check if auth is enabled - if so, we need a token
        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.error("✗ No authentication token available (auth is enabled)")
            return False
        
        if not self.created_prompts:
            logger.info("✓ No system prompts to update (expected in inference-only mode)")
            return True
        
        prompt_id = self.created_prompts[0]
        
        data = {
            "prompt": "You are a helpful assistant that has been updated for testing purposes.",
            "version": "1.1"
        }
        
        try:
            async with self.session.put(
                f"{self.base_url}/admin/prompts/{prompt_id}",
                json=data,
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✓ Updated system prompt: {result.get('name', 'Unknown')} (v{result.get('version', 'Unknown')})")
                    return True
                elif response.status == 404:
                    logger.error("✗ System prompt not found for update")
                    return False
                elif response.status == 503:
                    error = await response.text()
                    logger.info(f"✓ Expected response in inference-only mode: {error}")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"✗ System prompt update failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ System prompt update error: {str(e)}")
            return False
    
    async def test_associate_prompt_with_api_key(self) -> bool:
        """Test associating a system prompt with an API key"""
        logger.info("\n=== Testing Prompt-API Key Association ===")
        
        # Check if auth is enabled - if so, we need a token
        auth_enabled = await self.check_auth_enabled()
        if auth_enabled and not self.token:
            logger.error("✗ No authentication token available (auth is enabled)")
            return False
        
        if not self.created_api_keys or not self.created_prompts:
            logger.info("✓ No API keys or prompts to associate (expected in inference-only mode)")
            return True
        
        api_key = self.created_api_keys[0]
        prompt_id = self.created_prompts[0]
        
        data = {
            "prompt_id": prompt_id
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/admin/api-keys/{api_key}/prompt",
                json=data,
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✓ Associated prompt {prompt_id} with API key ***{api_key[-4:]}")
                    return True
                elif response.status == 404:
                    logger.error("✗ API key or prompt not found for association")
                    return False
                elif response.status == 503:
                    error = await response.text()
                    logger.info(f"✓ Expected response in inference-only mode: {error}")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"✗ Prompt-API key association failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ Prompt-API key association error: {str(e)}")
            return False
    
    async def test_unauthorized_access(self) -> bool:
        """Test admin endpoint access behavior with/without authentication"""
        logger.info("\n=== Testing Unauthorized Access ===")
        
        # First check if auth is enabled
        auth_enabled = await self.check_auth_enabled()
        
        # Test without token
        try:
            async with self.session.get(
                f"{self.base_url}/admin/api-keys",
                headers={"Content-Type": "application/json"},
                timeout=10
            ) as response:
                if auth_enabled:
                    # When auth is enabled, should require authentication
                    if response.status == 401:
                        logger.info("✓ Admin endpoint correctly requires authentication (auth enabled)")
                        return True
                    elif response.status == 503:
                        logger.info("✓ Service unavailable (expected in inference-only mode)")
                        return True
                    else:
                        logger.error(f"✗ Admin endpoint should require authentication but got: {response.status}")
                        return False
                else:
                    # When auth is disabled, should allow access
                    if response.status in [200, 503]:  # 503 for inference-only mode
                        logger.info("✓ Admin endpoint allows access without authentication (auth disabled)")
                        return True
                    else:
                        logger.error(f"✗ Admin endpoint should allow access when auth disabled but got: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"✗ Unauthorized access test error: {str(e)}")
            return False


# Pytest test functions
@pytest.mark.asyncio
async def test_admin_authentication():
    """Test admin authentication for admin endpoints"""
    async with AdminTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Admin authentication failed"


@pytest.mark.asyncio
async def test_api_key_management():
    """Test API key management endpoints"""
    async with AdminTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Admin authentication failed"
        assert await tester.test_create_api_key(), "API key creation failed"
        assert await tester.test_list_api_keys(), "API key listing failed"
        assert await tester.test_api_key_status(), "API key status check failed"


@pytest.mark.asyncio
async def test_system_prompt_management():
    """Test system prompt management endpoints"""
    async with AdminTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Admin authentication failed"
        assert await tester.test_create_system_prompt(), "System prompt creation failed"
        assert await tester.test_list_system_prompts(), "System prompt listing failed"
        assert await tester.test_get_system_prompt(), "System prompt retrieval failed"
        assert await tester.test_update_system_prompt(), "System prompt update failed"


@pytest.mark.asyncio
async def test_prompt_api_key_association():
    """Test associating prompts with API keys"""
    async with AdminTester(SERVER_URL) as tester:
        assert await tester.authenticate(), "Admin authentication failed"
        assert await tester.test_create_api_key(), "API key creation failed"
        assert await tester.test_create_system_prompt(), "System prompt creation failed"
        assert await tester.test_associate_prompt_with_api_key(), "Prompt-API key association failed"


@pytest.mark.asyncio
async def test_admin_security():
    """Test admin endpoint security"""
    async with AdminTester(SERVER_URL) as tester:
        assert await tester.test_unauthorized_access(), "Unauthorized access test failed"


@pytest.mark.asyncio
async def test_complete_admin_flow():
    """Test the complete admin management flow"""
    async with AdminTester(SERVER_URL) as tester:
        # Authenticate
        assert await tester.authenticate(), "Admin authentication failed"
        
        # Test API key management
        assert await tester.test_create_api_key(), "API key creation failed"
        assert await tester.test_list_api_keys(), "API key listing failed"
        assert await tester.test_api_key_status(), "API key status check failed"
        
        # Test system prompt management
        assert await tester.test_create_system_prompt(), "System prompt creation failed"
        assert await tester.test_list_system_prompts(), "System prompt listing failed"
        assert await tester.test_get_system_prompt(), "System prompt retrieval failed"
        assert await tester.test_update_system_prompt(), "System prompt update failed"
        
        # Test association
        assert await tester.test_associate_prompt_with_api_key(), "Prompt-API key association failed"
        
        # Test security
        assert await tester.test_unauthorized_access(), "Unauthorized access test failed"


# Main function for standalone execution
async def main():
    """Main test function for standalone execution"""
    async with AdminTester(SERVER_URL) as tester:
        logger.info(f"Testing admin endpoints against: {SERVER_URL}")
        logger.info("=" * 60)
        
        # Authenticate first
        if not await tester.authenticate():
            logger.error("❌ Authentication failed. Cannot proceed with admin tests.")
            return
        
        tests = [
            ("API Key Creation", tester.test_create_api_key),
            ("API Key Listing", tester.test_list_api_keys),
            ("API Key Status", tester.test_api_key_status),
            ("System Prompt Creation", tester.test_create_system_prompt),
            ("System Prompt Listing", tester.test_list_system_prompts),
            ("System Prompt Retrieval", tester.test_get_system_prompt),
            ("System Prompt Update", tester.test_update_system_prompt),
            ("Prompt-API Key Association", tester.test_associate_prompt_with_api_key),
            ("Unauthorized Access", tester.test_unauthorized_access)
        ]
        
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
        logger.info(f"Admin tests completed: {passed} passed, {failed} failed")
        
        if failed == 0:
            logger.info("✅ All admin tests passed!")
        else:
            logger.error("❌ Some admin tests failed")
            logger.info("\nTroubleshooting tips:")
            logger.info("1. Make sure the server is running: python -m server.main")
            logger.info("2. Check that authentication is enabled in your config.yaml")
            logger.info("3. Ensure MongoDB is running and accessible")
            logger.info("4. Check if the server is in inference-only mode (some features may be disabled)")
            logger.info("5. Verify admin user credentials are correct")
            logger.info("6. Check server logs for detailed error information")


if __name__ == "__main__":
    asyncio.run(main()) 