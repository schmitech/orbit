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
import yaml
import pytest
import pytest_asyncio

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
from services.database_service import create_database_service

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def resolve_env_variables(config_dict):
    """
    Recursively resolve environment variable placeholders in config dictionary.
    Replaces ${VAR_NAME} with the actual environment variable value.
    """
    if isinstance(config_dict, dict):
        return {key: resolve_env_variables(value) for key, value in config_dict.items()}
    elif isinstance(config_dict, list):
        return [resolve_env_variables(item) for item in config_dict]
    elif isinstance(config_dict, str):
        # Check if it's an environment variable placeholder
        if config_dict.startswith('${') and config_dict.endswith('}'):
            env_var_name = config_dict[2:-1]  # Extract variable name
            resolved_value = os.getenv(env_var_name)
            if resolved_value is None:
                logger.warning(f"Environment variable {env_var_name} not found, keeping placeholder")
                return config_dict
            return resolved_value
        return config_dict
    else:
        return config_dict

# Load config.yaml to detect backend type and configure tests
config_path = PROJECT_ROOT / 'config' / 'config.yaml'
if config_path.exists():
    with open(config_path, 'r') as f:
        project_config = yaml.safe_load(f)
    # Determine backend type from config file or environment variable, default to sqlite
    BACKEND_TYPE = os.getenv("TEST_BACKEND_TYPE", 
                             project_config.get('internal_services', {}).get('backend', {}).get('type', 'sqlite'))
    logger.info(f"Detected backend type from config: {BACKEND_TYPE}")
    
    # Use the project's internal_services configuration
    TEST_CONFIG = {
        'general': project_config.get('general', {}),
        'internal_services': project_config.get('internal_services', {}),
        'auth': project_config.get('auth', {})
    }

    # Resolve all environment variables in the config
    TEST_CONFIG = resolve_env_variables(TEST_CONFIG)
    logger.info("Resolved environment variables in test configuration")
    
    # Override backend type for tests
    TEST_CONFIG['internal_services']['backend']['type'] = BACKEND_TYPE
    
    # Use test database path for SQLite
    if BACKEND_TYPE == 'sqlite':
        TEST_CONFIG['internal_services']['backend']['sqlite'] = {
            'database_path': 'orbit_test.db'  # Use separate test database
        }
    
    # Override MongoDB collections for testing
    if BACKEND_TYPE == 'mongodb':
        if 'mongodb' not in TEST_CONFIG['internal_services']:
            TEST_CONFIG['internal_services']['mongodb'] = {}
        TEST_CONFIG['internal_services']['mongodb']['users_collection'] = 'test_users'
        TEST_CONFIG['internal_services']['mongodb']['sessions_collection'] = 'test_sessions'
else:
    # Fallback configuration if config.yaml is not found
    # First set BACKEND_TYPE for fallback mode
    BACKEND_TYPE = os.getenv("TEST_BACKEND_TYPE", "sqlite")

    TEST_CONFIG = {
        'general': {},
        'internal_services': {
            'backend': {
                'type': BACKEND_TYPE,
                'sqlite': {
                    'database_path': 'orbit_test.db'
                }
            },
            'mongodb': {
                'host': os.getenv("INTERNAL_SERVICES_MONGODB_HOST"),
                'port': int(os.getenv("INTERNAL_SERVICES_MONGODB_PORT", 27017)),
                'database': os.getenv("INTERNAL_SERVICES_MONGODB_DATABASE", "orbit_test"),
                'username': os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME"),
                'password': os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD"),
                'users_collection': 'test_users',
                'sessions_collection': 'test_sessions'
            }
        },
        'auth': {
            'session_duration_hours': 1,
            'default_admin_username': 'admin',
            'default_admin_password': 'admin123',
            'pbkdf2_iterations': 600000
        }
    }

# Validate required environment variables only for MongoDB
if BACKEND_TYPE == 'mongodb':
    required_vars = ["INTERNAL_SERVICES_MONGODB_HOST", "INTERNAL_SERVICES_MONGODB_USERNAME", 
                     "INTERNAL_SERVICES_MONGODB_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please check your .env file and ensure all required MongoDB variables are set")
        sys.exit(1)

@pytest_asyncio.fixture(scope="function")
async def database_service():
    """Fixture for a database service instance (works with both SQLite and MongoDB)."""
    config = TEST_CONFIG
    backend_type = config['internal_services']['backend']['type']

    # Clean up SQLite singleton cache and test database BEFORE creating the service
    if backend_type == 'sqlite':
        from services.sqlite_service import SQLiteService
        # Clear the singleton cache to ensure a fresh instance
        SQLiteService.clear_cache()

        test_db_path = config['internal_services']['backend']['sqlite']['database_path']
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
            logger.info(f"Removed existing SQLite test database before initialization: {test_db_path}")

    database = create_database_service(config)
    await database.initialize()

    logger.info(f"Testing with backend: {backend_type.upper()}")

    if backend_type == 'mongodb':
        logger.info(f"  MongoDB host: {config['internal_services']['mongodb']['host']}:{config['internal_services']['mongodb']['port']}")
        logger.info(f"  Database: {config['internal_services']['mongodb']['database']}")
    elif backend_type == 'sqlite':
        logger.info(f"  SQLite database: {config['internal_services']['backend']['sqlite']['database_path']}")

    yield database

    # Clean up after test
    if backend_type == 'sqlite':
        database.close()
        test_db_path = config['internal_services']['backend']['sqlite']['database_path']
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
            logger.info(f"Cleaned up SQLite test database: {test_db_path}")
        # Clear cache again after closing
        from services.sqlite_service import SQLiteService
        SQLiteService.clear_cache()
    else:
        database.close()

@pytest_asyncio.fixture(scope="function")
async def auth_service(database_service):
    """Pytest fixture for initializing the AuthService and cleaning up."""
    config = TEST_CONFIG
    backend_type = config['internal_services']['backend']['type']

    # Get collection names based on backend
    if backend_type == 'mongodb':
        users_collection_name = config.get('internal_services', {}).get('mongodb', {}).get('users_collection', 'test_users')
        sessions_collection_name = config.get('internal_services', {}).get('mongodb', {}).get('sessions_collection', 'test_sessions')

        # Clean up MongoDB collections before starting
        if hasattr(database_service, 'database'):
            await database_service.database.drop_collection(users_collection_name)
            await database_service.database.drop_collection(sessions_collection_name)

    # Pass as database_service (renamed parameter for backend abstraction)
    service = AuthService(config, database_service=database_service)
    await service.initialize()

    yield service

    logger.info("\n=== Cleaning up all test data ===")
    # Clean up based on backend type
    if backend_type == 'mongodb' and hasattr(database_service, 'database'):
        await database_service.database.drop_collection(users_collection_name)
        await database_service.database.drop_collection(sessions_collection_name)

    await service.close()
    logger.info("✓ All test data cleaned up")

@pytest_asyncio.fixture
async def new_user(auth_service: AuthService):
    """Creates a new user for a test and cleans it up afterward."""
    unique_username = f"testuser_{time.time_ns()}"
    password = 'testpass123'
    new_user_id = await auth_service.create_user(unique_username, password, 'user')
    assert new_user_id is not None
    
    user_data = {"id": new_user_id, "username": unique_username, "password": password}
    
    yield user_data
    
    # Cleanup the created user
    await auth_service.delete_user(new_user_id)

# --- Test Cases ---

async def test_default_admin_login(auth_service: AuthService):
    """Test 1: Login with default admin credentials"""
    logger.info("\n=== Test: Login with default admin ===")
    success, token, user_info = await auth_service.authenticate_user('admin', 'admin123')
    assert success, "Default admin login should succeed"
    assert token is not None, "Should receive a token"
    assert user_info['username'] == 'admin', "Username should be admin"
    assert user_info['role'] == 'admin', "Role should be admin"

async def test_validate_token(auth_service: AuthService):
    """Test 2: Validate the token"""
    logger.info("\n=== Test: Validate token ===")
    success, token, _ = await auth_service.authenticate_user('admin', 'admin123')
    assert success
    is_valid, validated_user = await auth_service.validate_token(token)
    assert is_valid, "Token should be valid"
    assert validated_user['username'] == 'admin', "Should get correct user info"

async def test_invalid_login(auth_service: AuthService):
    """Test 3: Invalid login"""
    logger.info("\n=== Test: Invalid login ===")
    success, bad_token, _ = await auth_service.authenticate_user('admin', 'wrongpassword')
    assert not success, "Login with wrong password should fail"
    assert bad_token is None, "Should not receive a token"

async def test_create_new_user(new_user):
    """Test 4: Create a new user"""
    logger.info("\n=== Test: Create new user ===")
    assert new_user['id'] is not None, "Should create user successfully"

async def test_create_user_with_default_role(auth_service: AuthService):
    """Test 4.5: Create a user with default role (should be 'user')"""
    logger.info("\n=== Test: Create user with default role ===")
    default_username = f"defaultuser_{time.time_ns()}"
    default_user_id = await auth_service.create_user(default_username, 'testpass123')
    assert default_user_id is not None, "Should create user with default role successfully"
    
    success, _, default_user_info = await auth_service.authenticate_user(default_username, 'testpass123')
    assert success, "Default user login should succeed"
    assert default_user_info['role'] == 'user', "Default role should be 'user'"
    
    # Cleanup
    await auth_service.delete_user(default_user_id)

async def test_login_with_new_user(auth_service: AuthService, new_user):
    """Test 5: Login with new user"""
    logger.info("\n=== Test: Login with new user ===")
    success, new_token, new_user_info = await auth_service.authenticate_user(new_user['username'], new_user['password'])
    assert success, "New user login should succeed"
    assert new_token is not None, "Should receive a token"
    assert new_user_info['id'] == new_user['id']

async def test_change_password(auth_service: AuthService, new_user):
    """Test 6: Change password"""
    logger.info("\n=== Test: Change password ===")
    success = await auth_service.change_password(new_user['id'], new_user['password'], 'newpass456')
    assert success, "Password change should succeed"
    
    # Verify old password no longer works
    success, _, _ = await auth_service.authenticate_user(new_user['username'], new_user['password'])
    assert not success, "Old password should not work"
    
    # Verify new password works
    success, _, _ = await auth_service.authenticate_user(new_user['username'], 'newpass456')
    assert success, "New password should work"

async def test_list_users(auth_service: AuthService, new_user):
    """Test 7: List users"""
    logger.info("\n=== Test: List users ===")
    users = await auth_service.list_users()
    assert len(users) >= 2, "Should have at least admin and new_user"
    usernames = [u['username'] for u in users]
    assert 'admin' in usernames
    assert new_user['username'] in usernames

async def test_deactivate_and_reactivate_user(auth_service: AuthService, new_user):
    """Test 8 & 8.5: Deactivate and reactivate user"""
    logger.info("\n=== Test: Deactivate user ===")
    deactivate_success = await auth_service.update_user_status(new_user['id'], False)
    assert deactivate_success, "Should deactivate user successfully"
    
    # Verify deactivated user cannot login
    login_fail, _, _ = await auth_service.authenticate_user(new_user['username'], new_user['password'])
    assert not login_fail, "Deactivated user should not be able to login"
    
    logger.info("\n=== Test: Reactivate user ===")
    reactivate_success = await auth_service.update_user_status(new_user['id'], True)
    assert reactivate_success, "Should reactivate user successfully"
    
    # Verify reactivated user can login
    login_success, _, _ = await auth_service.authenticate_user(new_user['username'], new_user['password'])
    assert login_success, "Reactivated user should be able to login"

async def test_logout(auth_service: AuthService):
    """Test 9: Logout"""
    logger.info("\n=== Test: Logout ===")
    success, token, _ = await auth_service.authenticate_user('admin', 'admin123')
    assert success
    
    logout_success = await auth_service.logout(token)
    assert logout_success, "Logout should succeed"
    
    # Verify token is no longer valid
    is_valid, _ = await auth_service.validate_token(token)
    assert not is_valid, "Token should be invalid after logout"

async def test_invalid_objectid_handling(auth_service: AuthService):
    """Test 10: Exception handling with invalid ObjectId"""
    logger.info("\n=== Test: Exception handling with invalid ObjectId ===")
    # Test change_password with invalid ObjectId
    success_change = await auth_service.change_password("invalid_object_id", "oldpass", "newpass")
    assert not success_change, "change_password should fail with invalid ObjectId"
    
    # Test update_user_status with invalid ObjectId
    success_update = await auth_service.update_user_status("invalid_object_id", True)
    assert not success_update, "update_user_status should fail with invalid ObjectId"
    
    # Test delete_user with invalid ObjectId
    success_delete = await auth_service.delete_user("invalid_object_id")
    assert not success_delete, "delete_user should fail with invalid ObjectId"

async def test_create_existing_user(auth_service: AuthService, new_user):
    """Test 11: Attempt to create a user that already exists"""
    logger.info("\n=== Test: Attempt to create existing user ===")
    existing_user_id = await auth_service.create_user(new_user['username'], 'newpass123')
    assert existing_user_id is None, "Should not create user with existing username"

async def test_reset_user_password(auth_service: AuthService, new_user):
    """Test 12: Reset user password (as admin)"""
    logger.info("\n=== Test: Reset user password ===")
    success = await auth_service.reset_user_password(new_user['id'], 'resetpassword789')
    assert success, "Password reset should succeed"
    
    # Verify new password works
    success, _, _ = await auth_service.authenticate_user(new_user['username'], 'resetpassword789')
    assert success, "Reset password should work"

async def test_delete_default_admin_fails(auth_service: AuthService):
    """Test 13: Attempt to delete default admin user"""
    logger.info("\n=== Test: Attempt to delete default admin user ===")
    users = await auth_service.list_users()
    admin_user_id = next((user['id'] for user in users if user['username'] == 'admin'), None)
    assert admin_user_id is not None, "Could not find admin user"
    success = await auth_service.delete_user(admin_user_id)
    assert not success, "Should not be able to delete default admin user"

async def test_delete_user(auth_service: AuthService, new_user):
    """Test 14: Delete user"""
    logger.info("\n=== Test: Delete user ===")
    # new_user fixture will delete the user, but we want to test the function explicitly
    # So we create another user to delete
    username = f"user_to_delete_{time.time_ns()}"
    user_id = await auth_service.create_user(username, "password")
    assert user_id is not None

    success = await auth_service.delete_user(user_id)
    assert success, "Should delete user successfully"
    
    # Verify deleted user cannot login
    success_login, _, _ = await auth_service.authenticate_user(username, "password")
    assert not success_login, "Deleted user should not be able to login"

async def test_login_non_existent_user(auth_service: AuthService):
    """Test 15: Login with non-existent user"""
    logger.info("\n=== Test: Login with non-existent user ===")
    success, _, _ = await auth_service.authenticate_user('nonexistentuser', 'somepassword')
    assert not success, "Login with non-existent user should fail"

async def test_get_user_by_id(auth_service: AuthService, new_user):
    """Test 16: Get user by ID with full details"""
    logger.info("\n=== Test: Get user by ID ===")
    
    # Test getting existing user
    user = await auth_service.get_user_by_id(new_user['id'])
    assert user is not None, "Should get user successfully"
    assert user['id'] == new_user['id'], "User ID should match"
    assert user['username'] == new_user['username'], "Username should match"
    assert user['role'] == 'user', "Role should be 'user'"
    assert user['active'] is True, "User should be active"
    assert 'created_at' in user, "Should include created_at timestamp"
    assert 'last_login' in user, "Should include last_login timestamp"
    
    # Test getting non-existent user
    non_existent_user = await auth_service.get_user_by_id("507f1f77bcf86cd799439011")
    assert non_existent_user is None, "Should return None for non-existent user"
    
    # Test with invalid ObjectId
    invalid_user = await auth_service.get_user_by_id("invalid_object_id")
    assert invalid_user is None, "Should return None for invalid ObjectId"

async def test_get_user_by_username(auth_service: AuthService, new_user):
    """Test 16a: Get user by username with efficient database lookup"""
    logger.info("\n=== Test: Get user by username ===")
    
    # Test getting existing user by username
    user = await auth_service.get_user_by_username(new_user['username'])
    assert user is not None, "Should get user successfully"
    assert user['id'] == new_user['id'], "User ID should match"
    assert user['username'] == new_user['username'], "Username should match"
    assert user['role'] == 'user', "Role should be 'user'"
    assert user['active'] is True, "User should be active"
    assert 'created_at' in user, "Should include created_at timestamp"
    assert 'last_login' in user, "Should include last_login timestamp"
    
    # Test getting non-existent user by username
    non_existent_user = await auth_service.get_user_by_username("nonexistent_username")
    assert non_existent_user is None, "Should return None for non-existent username"
    
    # Test with empty username
    empty_user = await auth_service.get_user_by_username("")
    assert empty_user is None, "Should return None for empty username"

async def test_get_user_by_id_invalid_objectid(auth_service: AuthService):
    """Test 17: Get user by ID with invalid ObjectId"""
    logger.info("\n=== Test: Get user by ID with invalid ObjectId ===")
    
    # Test with various invalid ObjectId formats
    invalid_ids = [
        "invalid_object_id",
        "123",
        "not_a_valid_id",
        "",
        "507f1f77bcf86cd79943901"  # Too short
    ]
    
    for invalid_id in invalid_ids:
        user = await auth_service.get_user_by_id(invalid_id)
        assert user is None, f"Should return None for invalid ID: {invalid_id}"

def test_auth_service():
    """Run all authentication service tests"""
    logger.info("Starting Authentication Service tests...")
    
    # Run all test functions
    test_functions = [
        test_default_admin_login,
        test_validate_token,
        test_invalid_login,
        test_create_new_user,
        test_create_user_with_default_role,
        test_login_with_new_user,
        test_change_password,
        test_list_users,
        test_deactivate_and_reactivate_user,
        test_logout,
        test_invalid_objectid_handling,
        test_create_existing_user,
        test_reset_user_password,
        test_delete_default_admin_fails,
        test_delete_user,
        test_login_non_existent_user,
        test_get_user_by_id,
        test_get_user_by_username,
        test_get_user_by_id_invalid_objectid
    ]
    
    # Note: This is a placeholder. In practice, you would use pytest to run these tests
    logger.info(f"Found {len(test_functions)} test functions")
    logger.info("To run tests, use: pytest server/tests/test_auth_service.py -v")

if __name__ == "__main__":
    asyncio.run(test_auth_service())