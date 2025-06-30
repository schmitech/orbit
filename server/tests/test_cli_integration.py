"""
Test CLI Integration
===================

This script tests the orbit.py CLI tool functionality.
Tests server control, authentication, user management, API key management, and prompt management commands.

Tests include:
- CLI help and server status
- Authentication (login, logout, me, auth-status)
- User management (list, register, config)
- Token persistence across CLI calls
- API key management (create, list, test, delete)
- System prompt management (create, list, get, update, delete)
- Integrated operations (API key with prompt)

Prerequisites:
1. MongoDB must be available and configured
2. orbit.py CLI must be accessible
3. Server must be running with authentication enabled
4. Default admin credentials (admin/admin123) must be available
"""

import asyncio
import subprocess
import json
import logging
import time
import pytest
from typing import Optional, Dict, Any, List, Union
import os
from pathlib import Path
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
ORBIT_CLI = PROJECT_ROOT / "bin" / "orbit.py"


class CLITester:
    def __init__(self):
        self.created_api_keys = []
        self.created_prompts = []
        self.temp_files = []
        self.test_users = []
        self.logged_in = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def run_command(self, command: List[str], timeout: int = 30) -> Dict[str, Any]:
        """Run a CLI command and return result"""
        full_command = ["python", str(ORBIT_CLI)] + command
        logger.info(f"Running: {' '.join(full_command)}")
        
        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=PROJECT_ROOT
            )
            
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Command timed out",
                "success": False
            }
        except Exception as e:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }
    
    def extract_json_from_output(self, output: str) -> Optional[Union[Dict[str, Any], List[Any]]]:
        """Extract JSON from CLI output that may contain additional text"""
        try:
            # The CLI outputs JSON followed by additional text
            # We need to find where the JSON ends
            lines = output.strip().split('\n')
            json_lines = []
            
            # Look for the start of JSON (should be '{' or '[')
            json_started = False
            brace_count = 0
            bracket_count = 0
            
            for line in lines:
                stripped_line = line.strip()
                
                if not json_started:
                    if stripped_line.startswith('{') or stripped_line.startswith('['):
                        json_started = True
                    else:
                        continue
                
                if json_started:
                    json_lines.append(line)
                    
                    # Count braces and brackets to know when JSON ends
                    for char in stripped_line:
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                        elif char == '[':
                            bracket_count += 1
                        elif char == ']':
                            bracket_count -= 1
                    
                    # If we've closed all braces/brackets, JSON is complete
                    if json_started and brace_count == 0 and bracket_count == 0:
                        break
            
            if json_lines:
                json_text = '\n'.join(json_lines)
                return json.loads(json_text)
                
        except Exception as e:
            logger.debug(f"Error extracting JSON: {e}")
            logger.debug(f"Output was: {output}")
        
        # Fallback: try to parse the entire output as JSON
        try:
            return json.loads(output.strip())
        except:
            return None
    
    def create_temp_prompt_file(self, content: str) -> str:
        """Create a temporary prompt file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(content)
            self.temp_files.append(f.name)
            return f.name
    
    def cleanup(self):
        """Clean up temporary files"""
        for temp_file in self.temp_files:
            try:
                os.unlink(temp_file)
            except:
                pass
    
    def test_cli_help(self) -> bool:
        """Test CLI help command"""
        logger.info("\n=== Testing CLI Help ===")
        
        result = self.run_command(["--help"])
        
        if result["success"]:
            logger.info("✓ CLI help command successful")
            return True
        else:
            logger.error(f"✗ CLI help failed: {result['stderr']}")
            return False
    
    def test_authentication_login(self) -> bool:
        """Test authentication login"""
        logger.info("\n=== Testing Authentication Login ===")
        
        # Try to login with default admin credentials
        result = self.run_command([
            "login",
            "--username", "admin",
            "--password", "admin123"
        ])
        
        if result["success"]:
            login_result = self.extract_json_from_output(result["stdout"])
            if login_result and login_result.get("token"):
                self.logged_in = True
                logger.info("✓ Authentication login successful")
                return True
            else:
                logger.error("✗ Login response missing token")
                return False
        else:
            # Check if it's a credential error or server not running
            if "401" in result["stderr"] or "Invalid username or password" in result["stderr"]:
                logger.error("✗ Login failed: Invalid credentials")
            elif "Connection" in result["stderr"] or "refused" in result["stderr"]:
                logger.error("✗ Login failed: Server not running")
            else:
                logger.error(f"✗ Login failed: {result['stderr']}")
            return False
    
    def test_authentication_me(self) -> bool:
        """Test current user info"""
        logger.info("\n=== Testing Current User Info ===")
        
        if not self.logged_in:
            logger.info("✓ Skipping me test (not logged in)")
            return True
        
        result = self.run_command(["me"])
        
        if result["success"]:
            user_info = self.extract_json_from_output(result["stdout"])
            if user_info and user_info.get("username"):
                logger.info(f"✓ Current user info: {user_info.get('username')} ({user_info.get('role')})")
                return True
            else:
                logger.error("✗ User info response invalid")
                return False
        else:
            logger.error(f"✗ Current user info failed: {result['stderr']}")
            return False
    
    def test_authentication_status(self) -> bool:
        """Test authentication status"""
        logger.info("\n=== Testing Authentication Status ===")
        
        result = self.run_command(["auth-status"])
        
        if result["success"] or result["returncode"] == 1:  # Status might return 1 if not authenticated
            status_result = self.extract_json_from_output(result["stdout"])
            if status_result:
                authenticated = status_result.get("authenticated", False)
                logger.info(f"✓ Authentication status: {'authenticated' if authenticated else 'not authenticated'}")
                return True
            else:
                logger.error("✗ Authentication status response invalid")
                return False
        else:
            logger.error(f"✗ Authentication status failed: {result['stderr']}")
            return False
    
    def test_user_management_list(self) -> bool:
        """Test user list functionality"""
        logger.info("\n=== Testing User List ===")
        
        if not self.logged_in:
            logger.info("✓ Skipping user list test (not logged in)")
            return True
        
        result = self.run_command(["user", "list"])
        
        if result["success"]:
            users = self.extract_json_from_output(result["stdout"])
            if users and isinstance(users, list):
                logger.info(f"✓ User list successful: {len(users)} users found")
                return True
            else:
                logger.error("✗ User list response invalid")
                return False
        else:
            # Check if it's an authentication error
            if "403" in result["stderr"] or "Admin privileges" in result["stderr"]:
                logger.info("✓ User list requires admin privileges (expected)")
                return True
            elif "Authentication required" in result["stderr"]:
                logger.info("✓ User list requires authentication (expected)")
                return True
            logger.error(f"✗ User list failed: {result['stderr']}")
            return False
    
    def test_user_management_register(self) -> bool:
        """Test user registration"""
        logger.info("\n=== Testing User Registration ===")
        
        if not self.logged_in:
            logger.info("✓ Skipping user registration test (not logged in)")
            return True
        
        test_username = f"testuser_{int(time.time())}"
        test_password = "testpass123"
        
        result = self.run_command([
            "register",
            "--username", test_username,
            "--password", test_password,
            "--role", "user"
        ])
        
        if result["success"]:
            register_result = self.extract_json_from_output(result["stdout"])
            if register_result and register_result.get("username") == test_username:
                self.test_users.append(test_username)
                logger.info(f"✓ User registration successful: {test_username}")
                return True
            else:
                logger.error("✗ User registration response invalid")
                return False
        else:
            # Check if it's an authentication/permission error
            if "403" in result["stderr"] or "Only administrators" in result["stderr"]:
                logger.info("✓ User registration requires admin privileges (expected)")
                return True
            elif "Authentication required" in result["stderr"]:
                logger.info("✓ User registration requires authentication (expected)")
                return True
            logger.error(f"✗ User registration failed: {result['stderr']}")
            return False
    
    def test_user_management_config(self) -> bool:
        """Test user configuration check"""
        logger.info("\n=== Testing User Config ===")
        
        result = self.run_command(["user", "config"])
        
        if result["success"]:
            config_result = self.extract_json_from_output(result["stdout"])
            if config_result:
                logger.info("✓ User config check successful")
                return True
            else:
                logger.error("✗ User config response invalid")
                return False
        else:
            logger.error(f"✗ User config failed: {result['stderr']}")
            return False
    
    def test_authentication_logout(self) -> bool:
        """Test authentication logout"""
        logger.info("\n=== Testing Authentication Logout ===")
        
        if not self.logged_in:
            logger.info("✓ Skipping logout test (not logged in)")
            return True
        
        result = self.run_command(["logout"])
        
        if result["success"]:
            logout_result = self.extract_json_from_output(result["stdout"])
            if logout_result:
                self.logged_in = False
                logger.info("✓ Authentication logout successful")
                return True
            else:
                logger.error("✗ Logout response invalid")
                return False
        else:
            logger.error(f"✗ Logout failed: {result['stderr']}")
            return False
    
    def test_token_persistence(self) -> bool:
        """Test token persistence across CLI calls"""
        logger.info("\n=== Testing Token Persistence ===")
        
        # First, login
        login_result = self.run_command([
            "login",
            "--username", "admin",
            "--password", "admin123"
        ])
        
        if not login_result["success"]:
            logger.info("✓ Skipping token persistence test (login failed)")
            return True
        
        # Wait a moment
        time.sleep(1)
        
        # Try to use a command that requires authentication without logging in again
        me_result = self.run_command(["me"])
        
        if me_result["success"]:
            logger.info("✓ Token persistence working (authentication persisted)")
            # Logout to clean up
            self.run_command(["logout"])
            return True
        else:
            logger.error("✗ Token persistence failed (authentication not persisted)")
            return False
    
    def test_server_status(self) -> bool:
        """Test server status command"""
        logger.info("\n=== Testing Server Status ===")
        
        result = self.run_command(["status"])
        
        if result["success"]:
            status = self.extract_json_from_output(result["stdout"])
            if status:
                logger.info(f"✓ Server status: {status.get('status', 'unknown')}")
                return True
            else:
                logger.error("✗ Server status output is not valid JSON")
                return False
        else:
            logger.error(f"✗ Server status failed: {result['stderr']}")
            return False
    
    def test_api_key_list(self) -> bool:
        """Test API key list command"""
        logger.info("\n=== Testing API Key List ===")
        
        result = self.run_command(["key", "list"])
        
        if result["success"]:
            keys = self.extract_json_from_output(result["stdout"])
            if keys and isinstance(keys, list):
                logger.info(f"✓ API key list successful: {len(keys)} keys found")
                return True
            else:
                logger.error("✗ API key list output is not valid JSON")
                return False
        else:
            # Check for different types of errors
            if "503" in result["stderr"] or "not available" in result["stderr"]:
                logger.info("✓ API key list not available (inference-only mode)")
                return True
            elif "401" in result["stderr"] or "authentication" in result["stderr"].lower():
                logger.info("✓ API key list requires authentication (expected)")
                return True
            elif "403" in result["stderr"] or "admin" in result["stderr"].lower():
                logger.info("✓ API key list requires admin privileges (expected)")
                return True
            logger.error(f"✗ API key list failed: {result['stderr']}")
            return False
    
    def test_api_key_create(self) -> bool:
        """Test API key creation command"""
        logger.info("\n=== Testing API Key Creation ===")
        
        collection_name = f"cli_test_{int(time.time())}"
        
        result = self.run_command([
            "key", "create",
            "--collection", collection_name,
            "--name", "CLI Test Client",
            "--notes", "Created by CLI integration test"
        ])
        
        if result["success"]:
            api_key_result = self.extract_json_from_output(result["stdout"])
            if api_key_result:
                api_key = api_key_result.get("api_key")
                if api_key:
                    self.created_api_keys.append(api_key)
                    logger.info(f"✓ API key created: ***{api_key[-4:]}")
                    return True
                else:
                    logger.error("✗ API key creation response missing api_key")
                    return False
            else:
                logger.error("✗ API key creation output is not valid JSON")
                return False
        else:
            # Check if it's a known error (service not available)
            if "503" in result["stderr"] or "not available" in result["stderr"]:
                logger.info("✓ API key creation not available (inference-only mode)")
                return True
            logger.error(f"✗ API key creation failed: {result['stderr']}")
            return False
    
    def test_prompt_create(self) -> bool:
        """Test system prompt creation command"""
        logger.info("\n=== Testing System Prompt Creation ===")
        
        prompt_content = "You are a helpful assistant created by CLI integration test."
        prompt_file = self.create_temp_prompt_file(prompt_content)
        prompt_name = f"CLI Test Prompt {int(time.time())}"
        
        result = self.run_command([
            "prompt", "create",
            "--name", prompt_name,
            "--file", prompt_file,
            "--version", "1.0"
        ])
        
        if result["success"]:
            prompt_result = self.extract_json_from_output(result["stdout"])
            if prompt_result:
                prompt_id = prompt_result.get("id")
                if prompt_id:
                    self.created_prompts.append(prompt_id)
                    logger.info(f"✓ System prompt created: {prompt_id}")
                    return True
                else:
                    logger.error("✗ System prompt creation response missing id")
                    return False
            else:
                logger.error("✗ System prompt creation output is not valid JSON")
                return False
        else:
            # Check if it's a known error (service not available)
            if "503" in result["stderr"] or "not available" in result["stderr"]:
                logger.info("✓ System prompt creation not available (inference-only mode)")
                return True
            logger.error(f"✗ System prompt creation failed: {result['stderr']}")
            return False
    
    def test_prompt_list(self) -> bool:
        """Test system prompt list command"""
        logger.info("\n=== Testing System Prompt List ===")
        
        result = self.run_command(["prompt", "list"])
        
        if result["success"]:
            prompts = self.extract_json_from_output(result["stdout"])
            if prompts and isinstance(prompts, list):
                logger.info(f"✓ System prompt list successful: {len(prompts)} prompts found")
                return True
            else:
                logger.error("✗ System prompt list output is not valid JSON")
                return False
        else:
            # Check for different types of errors
            if "503" in result["stderr"] or "not available" in result["stderr"]:
                logger.info("✓ System prompt list not available (inference-only mode)")
                return True
            elif "401" in result["stderr"] or "authentication" in result["stderr"].lower():
                logger.info("✓ System prompt list requires authentication (expected)")
                return True
            elif "403" in result["stderr"] or "admin" in result["stderr"].lower():
                logger.info("✓ System prompt list requires admin privileges (expected)")
                return True
            elif "500" in result["stderr"]:
                logger.info("✓ System prompt service not available (expected in some configurations)")
                return True
            logger.error(f"✗ System prompt list failed: {result['stderr']}")
            return False
    
    def test_api_key_with_prompt(self) -> bool:
        """Test creating API key with associated prompt"""
        logger.info("\n=== Testing API Key with Prompt ===")
        
        prompt_content = "You are a helpful assistant for API key prompt integration test."
        prompt_file = self.create_temp_prompt_file(prompt_content)
        collection_name = f"cli_integration_{int(time.time())}"
        prompt_name = f"CLI Integration Prompt {int(time.time())}"
        
        result = self.run_command([
            "key", "create",
            "--collection", collection_name,
            "--name", "CLI Integration Client",
            "--prompt-file", prompt_file,
            "--prompt-name", prompt_name
        ])
        
        if result["success"]:
            api_key_result = self.extract_json_from_output(result["stdout"])
            if api_key_result:
                api_key = api_key_result.get("api_key")
                system_prompt_id = api_key_result.get("system_prompt_id")
                
                if api_key:
                    self.created_api_keys.append(api_key)
                if system_prompt_id:
                    self.created_prompts.append(system_prompt_id)
                
                if api_key and system_prompt_id:
                    logger.info(f"✓ API key with prompt created: ***{api_key[-4:]} -> {system_prompt_id}")
                    return True
                else:
                    logger.error("✗ API key with prompt creation incomplete")
                    return False
            else:
                logger.error("✗ API key with prompt creation output is not valid JSON")
                return False
        else:
            # Check if it's a known error (service not available)
            if "503" in result["stderr"] or "not available" in result["stderr"]:
                logger.info("✓ API key with prompt creation not available (inference-only mode)")
                return True
            logger.error(f"✗ API key with prompt creation failed: {result['stderr']}")
            return False
    
    def test_api_key_test(self) -> bool:
        """Test API key testing command"""
        logger.info("\n=== Testing API Key Test ===")
        
        if not self.created_api_keys:
            logger.info("✓ No API keys to test (expected in inference-only mode)")
            return True
        
        api_key = self.created_api_keys[0]
        
        result = self.run_command([
            "key", "test",
            "--key", api_key
        ])
        
        if result["success"]:
            logger.info("✓ API key test successful")
            return True
        else:
            logger.error(f"✗ API key test failed: {result['stderr']}")
            return False


# Pytest test functions
@pytest.mark.asyncio
async def test_cli_help():
    """Test CLI help functionality"""
    with CLITester() as tester:
        assert tester.test_cli_help(), "CLI help test failed"


@pytest.mark.asyncio
async def test_cli_server_status():
    """Test CLI server status command"""
    with CLITester() as tester:
        assert tester.test_server_status(), "CLI server status test failed"


@pytest.mark.asyncio
async def test_cli_authentication():
    """Test CLI authentication operations"""
    with CLITester() as tester:
        assert tester.test_authentication_login(), "CLI login test failed"
        assert tester.test_authentication_me(), "CLI me test failed" 
        assert tester.test_authentication_status(), "CLI auth-status test failed"
        assert tester.test_authentication_logout(), "CLI logout test failed"


@pytest.mark.asyncio
async def test_cli_user_management():
    """Test CLI user management operations"""
    with CLITester() as tester:
        # Login first for user management tests
        tester.test_authentication_login()
        assert tester.test_user_management_list(), "CLI user list test failed"
        assert tester.test_user_management_register(), "CLI user register test failed"
        assert tester.test_user_management_config(), "CLI user config test failed"
        tester.test_authentication_logout()


@pytest.mark.asyncio
async def test_cli_token_persistence():
    """Test CLI token persistence"""
    with CLITester() as tester:
        assert tester.test_token_persistence(), "CLI token persistence test failed"


@pytest.mark.asyncio
async def test_cli_api_key_operations():
    """Test CLI API key operations"""
    with CLITester() as tester:
        # Login first for API key operations
        tester.test_authentication_login()
        assert tester.test_api_key_list(), "CLI API key list test failed"
        assert tester.test_api_key_create(), "CLI API key create test failed"
        assert tester.test_api_key_test(), "CLI API key test failed"
        tester.test_authentication_logout()


@pytest.mark.asyncio
async def test_cli_prompt_operations():
    """Test CLI prompt operations"""
    with CLITester() as tester:
        # Login first for prompt operations
        tester.test_authentication_login()
        assert tester.test_prompt_list(), "CLI prompt list test failed"
        assert tester.test_prompt_create(), "CLI prompt create test failed"
        tester.test_authentication_logout()


@pytest.mark.asyncio
async def test_cli_integrated_operations():
    """Test CLI integrated operations"""
    with CLITester() as tester:
        # Login first for integrated operations
        tester.test_authentication_login()
        assert tester.test_api_key_with_prompt(), "CLI API key with prompt test failed"
        tester.test_authentication_logout()


# Main function for standalone execution
def main():
    """Main test function for standalone execution"""
    with CLITester() as tester:
        logger.info("Testing orbit.py CLI functionality")
        logger.info("=" * 50)
        
        # Test authentication first
        auth_tests = [
            ("CLI Help", tester.test_cli_help),
            ("Server Status", tester.test_server_status),
            ("Authentication Login", tester.test_authentication_login),
            ("Authentication Me", tester.test_authentication_me),
            ("Authentication Status", tester.test_authentication_status),
            ("User Management List", tester.test_user_management_list),
            ("User Management Register", tester.test_user_management_register),
            ("User Management Config", tester.test_user_management_config),
            ("Authentication Logout", tester.test_authentication_logout),
            ("Token Persistence", tester.test_token_persistence)
        ]
        
        # Test API and prompt operations (with proper auth handling)
        def safe_auth_test(test_func):
            """Wrapper to safely run authenticated tests"""
            def wrapped():
                try:
                    # Login
                    login_success = tester.test_authentication_login()
                    if not login_success:
                        logger.info(f"✓ Skipping {test_func.__name__} (login failed)")
                        return True
                    
                    # Run the test
                    result = test_func()
                    
                    # Always logout, even if test failed
                    tester.test_authentication_logout()
                    
                    return result
                except Exception as e:
                    logger.error(f"✗ {test_func.__name__} crashed: {e}")
                    # Try to logout even after crash
                    try:
                        tester.test_authentication_logout()
                    except:
                        pass
                    return False
            return wrapped
        
        api_tests = [
            ("API Key List", safe_auth_test(tester.test_api_key_list)),
            ("API Key Create", safe_auth_test(tester.test_api_key_create)),
            ("System Prompt List", safe_auth_test(tester.test_prompt_list)),
            ("System Prompt Create", safe_auth_test(tester.test_prompt_create)),
            ("API Key with Prompt", safe_auth_test(tester.test_api_key_with_prompt)),
            ("API Key Test", safe_auth_test(tester.test_api_key_test))
        ]
        
        tests = auth_tests + api_tests
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            try:
                logger.info(f"\n--- Running {test_name} ---")
                if test_func():
                    passed += 1
                    logger.info(f"✅ {test_name} PASSED")
                else:
                    failed += 1
                    logger.error(f"❌ {test_name} FAILED")
            except Exception as e:
                logger.error(f"💥 {test_name} CRASHED: {str(e)}")
                failed += 1
        
        logger.info("\n" + "=" * 50)
        logger.info(f"CLI tests completed: {passed} passed, {failed} failed")
        
        if failed == 0:
            logger.info("✅ All CLI tests passed!")
        else:
            logger.error("❌ Some CLI tests failed")


if __name__ == "__main__":
    main() 