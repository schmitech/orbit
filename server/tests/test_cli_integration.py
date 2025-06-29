"""
Test CLI Integration
===================

This script tests the orbit.py CLI tool functionality.
Tests server control, API key management, and prompt management commands.

Prerequisites:
1. MongoDB must be available and configured
2. orbit.py CLI must be accessible
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
            # Check if it's a known error (service not available)
            if "503" in result["stderr"] or "not available" in result["stderr"]:
                logger.info("✓ API key list not available (inference-only mode)")
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
            # Check if it's a known error (service not available)
            if "503" in result["stderr"] or "not available" in result["stderr"]:
                logger.info("✓ System prompt list not available (inference-only mode)")
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
async def test_cli_api_key_operations():
    """Test CLI API key operations"""
    with CLITester() as tester:
        assert tester.test_api_key_list(), "CLI API key list test failed"
        assert tester.test_api_key_create(), "CLI API key create test failed"
        assert tester.test_api_key_test(), "CLI API key test failed"


@pytest.mark.asyncio
async def test_cli_prompt_operations():
    """Test CLI prompt operations"""
    with CLITester() as tester:
        assert tester.test_prompt_list(), "CLI prompt list test failed"
        assert tester.test_prompt_create(), "CLI prompt create test failed"


@pytest.mark.asyncio
async def test_cli_integrated_operations():
    """Test CLI integrated operations"""
    with CLITester() as tester:
        assert tester.test_api_key_with_prompt(), "CLI API key with prompt test failed"


# Main function for standalone execution
def main():
    """Main test function for standalone execution"""
    with CLITester() as tester:
        logger.info("Testing orbit.py CLI functionality")
        logger.info("=" * 50)
        
        tests = [
            ("CLI Help", tester.test_cli_help),
            ("Server Status", tester.test_server_status),
            ("API Key List", tester.test_api_key_list),
            ("API Key Create", tester.test_api_key_create),
            ("System Prompt List", tester.test_prompt_list),
            ("System Prompt Create", tester.test_prompt_create),
            ("API Key with Prompt", tester.test_api_key_with_prompt),
            ("API Key Test", tester.test_api_key_test)
        ]
        
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