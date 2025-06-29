"""
Test script for the Authentication Service
=========================================

This script tests the basic functionality of the authentication service
to ensure it works correctly before integrating with the rest of the system.
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if not env_path.exists():
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)

from services.auth_service import AuthService
from services.mongodb_service import MongoDBService

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Test configuration using environment variables
TEST_CONFIG = {
    'general': {'verbose': True},
    'internal_services': {
        'mongodb': {
            'host': os.getenv("INTERNAL_SERVICES_MONGODB_HOST"),
            'port': int(os.getenv("INTERNAL_SERVICES_MONGODB_PORT", 27017)),
            'database': os.getenv("INTERNAL_SERVICES_MONGODB_DATABASE", "orbit_test"),
            'username': os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME"),
            'password': os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD")
        }
    },
    'mongodb': {
        'users_collection': 'test_users',
        'sessions_collection': 'test_sessions'
    },
    'auth': {
        'session_duration_hours': 12,
        'default_admin_username': 'admin',
        'default_admin_password': 'admin123',
        'pbkdf2_iterations': 600000
    }
}

# Validate required environment variables
required_vars = ["INTERNAL_SERVICES_MONGODB_HOST", "INTERNAL_SERVICES_MONGODB_USERNAME", 
                 "INTERNAL_SERVICES_MONGODB_PASSWORD"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    logger.error("Please check your .env file and ensure all required MongoDB variables are set")
    sys.exit(1)

async def test_auth_service():
    """Test the authentication service functionality"""
    
    # Use the test configuration
    config = TEST_CONFIG
    
    # Clean up test collections before running tests
    mongodb = MongoDBService(config)
    await mongodb.initialize()
    await mongodb.database.drop_collection('test_users')
    await mongodb.database.drop_collection('test_sessions')
    mongodb.close()
    
    # Log configuration info (with sensitive data masked)
    logger.info(f"Testing with MongoDB at: {config['internal_services']['mongodb']['host']}:{config['internal_services']['mongodb']['port']}")
    logger.info(f"Using database: {config['internal_services']['mongodb']['database']}")
    username = config['internal_services']['mongodb']['username']
    if username:
        masked_username = username[:2] + '*' * (len(username) - 2) if len(username) > 2 else '*****'
        logger.info(f"Using username: {masked_username}")
    
    # Initialize the service
    auth_service = AuthService(config)
    await auth_service.initialize()
    
    try:
        # Test 1: Login with default admin credentials
        logger.info("\n=== Test 1: Login with default admin ===")
        success, token, user_info = await auth_service.authenticate_user('admin', 'admin123')
        assert success, "Default admin login should succeed"
        assert token is not None, "Should receive a token"
        assert user_info['username'] == 'admin', "Username should be admin"
        assert user_info['role'] == 'admin', "Role should be admin"
        logger.info(f"✓ Login successful. Token: {token[:8]}...")
        logger.info(f"✓ User info: {user_info}")
        
        # Test 2: Validate the token
        logger.info("\n=== Test 2: Validate token ===")
        is_valid, validated_user = await auth_service.validate_token(token)
        assert is_valid, "Token should be valid"
        assert validated_user['username'] == 'admin', "Should get correct user info"
        logger.info(f"✓ Token is valid. User: {validated_user}")
        
        # Test 3: Invalid login
        logger.info("\n=== Test 3: Invalid login ===")
        success, bad_token, bad_user = await auth_service.authenticate_user('admin', 'wrongpassword')
        assert not success, "Login with wrong password should fail"
        assert bad_token is None, "Should not receive a token"
        logger.info("✓ Invalid login correctly rejected")
        
        # Test 4: Create a new user
        logger.info("\n=== Test 4: Create new user ===")
        # Use unique username to avoid conflicts with existing test data
        unique_username = f"testuser_{int(time.time())}"
        new_user_id = await auth_service.create_user(unique_username, 'testpass123', 'admin')
        assert new_user_id is not None, "Should create user successfully"
        logger.info(f"✓ Created new user with ID: {new_user_id}")
        
        # Test 4.5: Create a user with default role (should be "user")
        logger.info("\n=== Test 4.5: Create user with default role ===")
        default_username = f"defaultuser_{int(time.time())}"
        default_user_id = await auth_service.create_user(default_username, 'testpass123')
        assert default_user_id is not None, "Should create user with default role successfully"
        
        # Verify the default role is "user"
        success, _, default_user_info = await auth_service.authenticate_user(default_username, 'testpass123')
        assert success, "Default user login should succeed"
        assert default_user_info['role'] == 'user', "Default role should be 'user'"
        logger.info(f"✓ Created user with default role: {default_user_info['role']}")
        
        # Test 5: Login with new user
        logger.info("\n=== Test 5: Login with new user ===")
        success, new_token, new_user_info = await auth_service.authenticate_user(unique_username, 'testpass123')
        assert success, "New user login should succeed"
        assert new_token is not None, "Should receive a token"
        logger.info(f"✓ New user login successful. Token: {new_token[:8]}...")
        
        # Test 6: Change password
        logger.info("\n=== Test 6: Change password ===")
        success = await auth_service.change_password(new_user_info['id'], 'testpass123', 'newpass456')
        assert success, "Password change should succeed"
        logger.info("✓ Password changed successfully")
        
        # Verify old password no longer works
        success, _, _ = await auth_service.authenticate_user(unique_username, 'testpass123')
        assert not success, "Old password should not work"
        logger.info("✓ Old password correctly rejected")
        
        # Verify new password works
        success, _, _ = await auth_service.authenticate_user(unique_username, 'newpass456')
        assert success, "New password should work"
        logger.info("✓ New password accepted")
        
        # Test 7: List users
        logger.info("\n=== Test 7: List users ===")
        users = await auth_service.list_users()
        assert len(users) >= 2, "Should have at least 2 users"
        logger.info(f"✓ Found {len(users)} users:")
        for user in users:
            logger.info(f"  - {user['username']} ({user['role']})")
        
        # Test 8: Deactivate user
        logger.info("\n=== Test 8: Deactivate user ===")
        success = await auth_service.update_user_status(new_user_id, False)
        assert success, "Should deactivate user successfully"
        logger.info("✓ User deactivated")
        
        # Verify deactivated user cannot login
        success, _, _ = await auth_service.authenticate_user(unique_username, 'newpass456')
        assert not success, "Deactivated user should not be able to login"
        logger.info("✓ Deactivated user correctly rejected")
        
        # Test 9: Logout
        logger.info("\n=== Test 9: Logout ===")
        success = await auth_service.logout(token)
        assert success, "Logout should succeed"
        logger.info("✓ Logged out successfully")
        
        # Verify token is no longer valid
        is_valid, _ = await auth_service.validate_token(token)
        assert not is_valid, "Token should be invalid after logout"
        logger.info("✓ Token correctly invalidated")
        
        # Test 10: Exception handling with invalid ObjectId
        logger.info("\n=== Test 10: Exception handling with invalid ObjectId ===")
        # Test change_password with invalid ObjectId
        success = await auth_service.change_password("invalid_object_id", "oldpass", "newpass")
        assert not success, "Should fail with invalid ObjectId"
        logger.info("✓ Invalid ObjectId correctly handled in change_password")
        
        # Test update_user_status with invalid ObjectId
        success = await auth_service.update_user_status("invalid_object_id", True)
        assert not success, "Should fail with invalid ObjectId"
        logger.info("✓ Invalid ObjectId correctly handled in update_user_status")
        
        logger.info("\n✅ All tests passed!")
        
    except AssertionError as e:
        logger.error(f"❌ Test failed: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        raise
    finally:
        # Clean up test data
        logger.info("\n=== Cleaning up test data ===")
        await auth_service.mongodb.database.drop_collection('test_users')
        await auth_service.mongodb.database.drop_collection('test_sessions')
        await auth_service.close()
        logger.info("✓ Test data cleaned up")


if __name__ == "__main__":
    asyncio.run(test_auth_service())