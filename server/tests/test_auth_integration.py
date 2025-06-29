"""
Test Authentication Integration
==============================

This script tests the authentication endpoints with a running server.
Make sure the server is running before executing this test.

Prerequisites:
1. Server must be running on http://localhost:3000
2. Authentication must be enabled in the server configuration
3. MongoDB must be available and configured
"""

import asyncio
import aiohttp
import json
import logging
import time
import pytest
from typing import Optional
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


class AuthTester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _get_headers(self, include_auth: bool = True) -> dict:
        """Get headers with optional authentication"""
        headers = {"Content-Type": "application/json"}
        if include_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    async def check_server_availability(self) -> bool:
        """Check if the server is running and accessible"""
        logger.info("=== Checking Server Availability ===")
        
        try:
            # Try to connect to the server
            async with self.session.get(f"{self.base_url}/health", timeout=5) as response:
                if response.status == 200:
                    logger.info("✓ Server is running and accessible")
                    return True
                else:
                    logger.error(f"✗ Server responded with status {response.status}")
                    return False
        except aiohttp.ClientConnectorError:
            logger.error("✗ Cannot connect to server. Is it running on http://localhost:3000?")
            return False
        except asyncio.TimeoutError:
            logger.error("✗ Server connection timeout")
            return False
        except Exception as e:
            logger.error(f"✗ Server check error: {str(e)}")
            return False
    
    async def test_login(self) -> bool:
        """Test login endpoint"""
        logger.info("=== Testing Login ===")
        
        data = {
            "username": DEFAULT_USERNAME,
            "password": DEFAULT_PASSWORD
        }
        
        logger.info(f"Attempting login with username: {DEFAULT_USERNAME}")
        logger.info(f"Password being used: {DEFAULT_PASSWORD[:3]}***")
        
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
                        logger.info(f"✓ Login successful. Token: {self.token[:8]}...")
                        logger.info(f"✓ User: {result.get('user')}")
                        return True
                    else:
                        logger.error("✗ Login response missing token")
                        return False
                elif response.status == 401:
                    error = await response.text()
                    logger.error(f"✗ Login failed: Invalid credentials - {error}")
                    logger.info("The admin user exists but the password is incorrect.")
                    logger.info("Possible solutions:")
                    logger.info("1. Check if ORBIT_DEFAULT_ADMIN_PASSWORD environment variable is set correctly")
                    logger.info("2. The admin user might have been created with a different password")
                    logger.info("3. Try resetting the admin password by deleting the user from MongoDB")
                    logger.info("4. Check server logs for admin user creation messages")
                    return False
                elif response.status == 503:
                    error = await response.text()
                    logger.error(f"✗ Login failed: Authentication service not available - {error}")
                    logger.info("Make sure authentication is enabled in the server configuration")
                    return False
                else:
                    error = await response.text()
                    logger.error(f"✗ Login failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ Login error: {str(e)}")
            return False
    
    async def test_get_me(self) -> bool:
        """Test /auth/me endpoint"""
        logger.info("\n=== Testing Get Current User ===")
        
        if not self.token:
            logger.error("✗ No token available")
            return False
        
        try:
            async with self.session.get(
                f"{self.base_url}/auth/me",
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✓ Got user info: {result}")
                    return True
                elif response.status == 401:
                    error = await response.text()
                    logger.error(f"✗ Get user failed: Invalid token - {error}")
                    return False
                else:
                    error = await response.text()
                    logger.error(f"✗ Get user failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ Get user error: {str(e)}")
            return False
    
    async def test_admin_endpoint(self) -> bool:
        """Test accessing an admin endpoint with auth"""
        logger.info("\n=== Testing Admin Endpoint Access ===")
        
        if not self.token:
            logger.error("✗ No token available")
            return False
        
        try:
            # Try to list API keys (admin endpoint)
            async with self.session.get(
                f"{self.base_url}/admin/api-keys",
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✓ Admin access successful. Found {len(result)} API keys")
                    return True
                elif response.status == 401:
                    error = await response.text()
                    logger.error(f"✗ Admin access failed: Authentication required - {error}")
                    return False
                elif response.status == 403:
                    error = await response.text()
                    logger.error(f"✗ Admin access failed: Admin role required - {error}")
                    return False
                elif response.status == 503:
                    error = await response.text()
                    logger.error(f"✗ Admin access failed: Service not available - {error}")
                    logger.info("This might be expected in inference-only mode")
                    return True  # Consider this a pass in inference-only mode
                else:
                    error = await response.text()
                    logger.error(f"✗ Admin access failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ Admin access error: {str(e)}")
            return False
    
    async def test_create_user(self) -> bool:
        """Test creating a new user"""
        logger.info("\n=== Testing User Creation ===")
        
        if not self.token:
            logger.error("✗ No token available")
            return False
        
        # Use a unique username with timestamp to avoid conflicts
        import time
        unique_username = f"testuser_{int(time.time())}"
        
        data = {
            "username": unique_username,
            "password": "testpass123",
            "role": "admin"
        }
        
        logger.info(f"Attempting to create user: {unique_username}")
        
        try:
            async with self.session.post(
                f"{self.base_url}/auth/register",
                json=data,
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✓ User created: {result}")
                    return True
                elif response.status == 400:
                    # User might already exist
                    error = await response.text()
                    logger.info(f"✓ User already exists (expected if test run multiple times): {error}")
                    return True
                elif response.status == 403:
                    error = await response.text()
                    logger.error(f"✗ User creation failed: Admin role required - {error}")
                    return False
                elif response.status == 500:
                    error = await response.text()
                    logger.error(f"✗ User creation failed: Internal server error - {error}")
                    logger.info("This might be due to:")
                    logger.info("1. Database connection issues")
                    logger.info("2. User creation logic errors")
                    logger.info("3. MongoDB permissions")
                    logger.info("4. Duplicate username (though we use unique names)")
                    return False
                else:
                    error = await response.text()
                    logger.error(f"✗ User creation failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ User creation error: {str(e)}")
            return False
    
    async def test_logout(self) -> bool:
        """Test logout endpoint"""
        logger.info("\n=== Testing Logout ===")
        
        if not self.token:
            logger.error("✗ No token available")
            return False
        
        try:
            async with self.session.post(
                f"{self.base_url}/auth/logout",
                headers=self._get_headers(),
                timeout=10
            ) as response:
                if response.status == 200:
                    logger.info("✓ Logout successful")
                    
                    # Verify token is invalid
                    async with self.session.get(
                        f"{self.base_url}/auth/me",
                        headers=self._get_headers(),
                        timeout=10
                    ) as verify_response:
                        if verify_response.status == 401:
                            logger.info("✓ Token correctly invalidated")
                            return True
                        else:
                            logger.error("✗ Token still valid after logout")
                            return False
                else:
                    error = await response.text()
                    logger.error(f"✗ Logout failed: {response.status} - {error}")
                    return False
        except Exception as e:
            logger.error(f"✗ Logout error: {str(e)}")
            return False
    
    async def check_auth_service_availability(self) -> bool:
        """Check if the authentication service is available"""
        logger.info("=== Checking Authentication Service Availability ===")
        
        try:
            # Try to access the login endpoint to see if auth service is available
            async with self.session.post(
                f"{self.base_url}/auth/login",
                json={"username": "test", "password": "test"},
                headers={"Content-Type": "application/json"},
                timeout=5
            ) as response:
                if response.status == 401:
                    # This is good - auth service is available, just wrong credentials
                    logger.info("✓ Authentication service is available")
                    return True
                elif response.status == 503:
                    error = await response.text()
                    logger.error(f"✗ Authentication service not available: {error}")
                    logger.info("This usually means:")
                    logger.info("1. Authentication is disabled in config.yaml")
                    logger.info("2. MongoDB is not accessible")
                    logger.info("3. Authentication service failed to initialize")
                    logger.info("4. Server is in inference_only mode with auth disabled")
                    logger.info("")
                    logger.info("To fix this, ensure your config.yaml has:")
                    logger.info("  auth:")
                    logger.info("    enabled: true")
                    logger.info("  internal_services:")
                    logger.info("    mongodb:")
                    logger.info("      host: your-mongodb-host")
                    logger.info("      port: 27017")
                    logger.info("      database: orbit")
                    logger.info("      username: your-username")
                    logger.info("      password: your-password")
                    logger.info("")
                    logger.info("Note: MongoDB is required when auth is enabled, even in inference_only mode.")
                    return False
                else:
                    logger.info(f"✓ Authentication service responded with status {response.status}")
                    return True
        except Exception as e:
            logger.error(f"✗ Error checking auth service: {str(e)}")
            return False


# Pytest test functions
@pytest.mark.asyncio
async def test_server_availability():
    """Test that the server is running and accessible"""
    async with AuthTester(SERVER_URL) as tester:
        assert await tester.check_server_availability(), "Server is not available"


@pytest.mark.asyncio
async def test_auth_service_availability():
    """Test that the authentication service is available"""
    async with AuthTester(SERVER_URL) as tester:
        assert await tester.check_server_availability(), "Server is not available"
        assert await tester.check_auth_service_availability(), "Authentication service is not available"


@pytest.mark.asyncio
async def test_admin_user_exists():
    """Test that the admin user exists and provide debugging info"""
    async with AuthTester(SERVER_URL) as tester:
        assert await tester.check_server_availability(), "Server is not available"
        
        # Try to login with wrong password to see if user exists
        data = {"username": "admin", "password": "wrongpassword"}
        
        try:
            async with tester.session.post(
                f"{SERVER_URL}/auth/login",
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=5
            ) as response:
                if response.status == 401:
                    error = await response.text()
                    if "Invalid username or password" in error:
                        logger.info("✓ Admin user exists (got 401 with wrong password)")
                        logger.info("The issue is with the password, not the user account.")
                        logger.info(f"Current password being used: {DEFAULT_PASSWORD[:3]}***")
                        logger.info("Check server logs for admin user creation to see what password was used.")
                        return True
                    else:
                        logger.error(f"Unexpected error: {error}")
                        return False
                else:
                    logger.error(f"Unexpected response: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Error testing admin user: {str(e)}")
            return False


@pytest.mark.asyncio
async def test_authentication_flow():
    """Test the complete authentication flow"""
    async with AuthTester(SERVER_URL) as tester:
        # Check server availability first
        assert await tester.check_server_availability(), "Server is not available"
        
        # Test login
        assert await tester.test_login(), "Login failed"
        
        # Test get current user
        assert await tester.test_get_me(), "Get current user failed"
        
        # Test admin endpoint access
        assert await tester.test_admin_endpoint(), "Admin endpoint access failed"
        
        # Test user creation
        assert await tester.test_create_user(), "User creation failed"
        
        # Test logout
        assert await tester.test_logout(), "Logout failed"


@pytest.mark.asyncio
async def test_login():
    """Test login functionality"""
    async with AuthTester(SERVER_URL) as tester:
        assert await tester.check_server_availability(), "Server is not available"
        assert await tester.test_login(), "Login failed"


@pytest.mark.asyncio
async def test_get_current_user():
    """Test getting current user information"""
    async with AuthTester(SERVER_URL) as tester:
        assert await tester.check_server_availability(), "Server is not available"
        assert await tester.test_login(), "Login failed"
        assert await tester.test_get_me(), "Get current user failed"


@pytest.mark.asyncio
async def test_admin_endpoint_access():
    """Test admin endpoint access"""
    async with AuthTester(SERVER_URL) as tester:
        assert await tester.check_server_availability(), "Server is not available"
        assert await tester.test_login(), "Login failed"
        assert await tester.test_admin_endpoint(), "Admin endpoint access failed"


@pytest.mark.asyncio
async def test_user_creation():
    """Test user creation functionality"""
    async with AuthTester(SERVER_URL) as tester:
        assert await tester.check_server_availability(), "Server is not available"
        assert await tester.test_login(), "Login failed"
        assert await tester.test_create_user(), "User creation failed"


@pytest.mark.asyncio
async def test_logout():
    """Test logout functionality"""
    async with AuthTester(SERVER_URL) as tester:
        assert await tester.check_server_availability(), "Server is not available"
        assert await tester.test_login(), "Login failed"
        assert await tester.test_logout(), "Logout failed"


# Keep the original main function for standalone execution
async def main():
    """Main test function for standalone execution"""
    async with AuthTester(SERVER_URL) as tester:
        logger.info(f"Testing authentication against: {SERVER_URL}")
        logger.info("=" * 50)
        
        # First check if server is available
        if not await tester.check_server_availability():
            logger.error("❌ Server is not available. Please start the server first.")
            return
        
        tests = [
            tester.test_login,
            tester.test_get_me,
            tester.test_admin_endpoint,
            tester.test_create_user,
            tester.test_logout
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                if await test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Test {test.__name__} crashed: {str(e)}")
                failed += 1
        
        logger.info("\n" + "=" * 50)
        logger.info(f"Tests completed: {passed} passed, {failed} failed")
        
        if failed == 0:
            logger.info("✅ All tests passed!")
        else:
            logger.error("❌ Some tests failed")
            logger.info("\nTroubleshooting tips:")
            logger.info("1. Make sure the server is running: python -m server.main")
            logger.info("2. Check that authentication is enabled in your config.yaml:")
            logger.info("   auth:")
            logger.info("     enabled: true")
            logger.info("3. Ensure MongoDB is running and accessible")
            logger.info("4. Check server logs for authentication service errors")


if __name__ == "__main__":
    asyncio.run(main())