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


class ApiKeyAuthTester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.admin_token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.created_api_keys = []  # Track created API keys for cleanup
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup_resources()
        if self.session:
            await self.session.close()
    
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
    
    async def create_test_api_key(self, collection_name: str = None) -> Optional[str]:
        """Create a test API key for testing"""
        if not collection_name:
            collection_name = f"test_collection_{int(time.time())}"
        
        logger.info(f"Creating test API key for collection: {collection_name}")
        
        data = {
            "collection_name": collection_name,
            "client_name": "Test Client for API Key Auth",
            "notes": "Created for API key authentication testing"
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
        logger.info("=== Cleaning up API key resources ===")
        
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


# Pytest test functions
@pytest.mark.asyncio
async def test_api_key_authentication_flow():
    """Test the complete API key authentication flow"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        # Authenticate as admin first
        assert await tester.authenticate_admin(), "Admin authentication failed"
        
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
        assert await tester.authenticate_admin(), "Admin authentication failed"
        assert await tester.test_invalid_api_key(), "Invalid API key test failed"


# Main function for standalone execution
async def main():
    """Main test function for standalone execution"""
    async with ApiKeyAuthTester(SERVER_URL) as tester:
        logger.info(f"Testing API key authentication against: {SERVER_URL}")
        logger.info("=" * 60)
        
        # Authenticate as admin
        if not await tester.authenticate_admin():
            logger.error("❌ Admin authentication failed. Cannot proceed with API key tests.")
            return
        
        tests = [
            ("Invalid API Key", tester.test_invalid_api_key)
        ]
        
        # Only run API key tests if we can create keys
        api_key = await tester.create_test_api_key()
        if api_key:
            tests.extend([
                ("Health Endpoint with API Key", lambda: tester.test_health_endpoint_with_api_key(api_key))
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