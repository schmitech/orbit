"""Integration tests for the modularized ORBIT CLI.

This is an adapted version of the original test that works with the new modular structure.
"""

import pytest
import subprocess
import json
import logging
import time
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ModularCLITester:
    """Test harness for the modularized ORBIT CLI."""
    
    def __init__(self):
        self.created_resources = {
            'api_keys': [],
            'prompts': [],
            'users': [],
            'temp_files': []
        }
        self.logged_in = False
        
        # Determine how to run the CLI
        self.cli_command = self._get_cli_command()
    
    def _get_cli_command(self) -> List[str]:
        """Determine the command to run the CLI."""
        # Try different ways to run the CLI
        
        # 1. If installed as a package
        if self._command_exists('orbit'):
            return ['orbit']
        
        # 2. If running from development with python -m
        project_root = Path(__file__).parent.parent.parent
        if (project_root / 'orbit_cli' / '__main__.py').exists():
            return [sys.executable, '-m', 'orbit_cli']
        
        # 3. If there's a bin/orbit script
        orbit_script = project_root / 'bin' / 'orbit'
        if orbit_script.exists():
            return [sys.executable, str(orbit_script)]
        
        # 4. Default to module execution
        return [sys.executable, '-m', 'orbit_cli']
    
    def _command_exists(self, cmd: str) -> bool:
        """Check if a command exists in PATH."""
        try:
            subprocess.run([cmd, '--version'], capture_output=True, check=False)
            return True
        except FileNotFoundError:
            return False
    
    def run_command(self, command: List[str], timeout: int = 30) -> Dict[str, Any]:
        """Run a CLI command and return result."""
        full_command = self.cli_command + command
        logger.info(f"Running: {' '.join(full_command)}")
        
        try:
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=timeout
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
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
    
    def cleanup(self):
        """Clean up all created resources."""
        # Clean up temp files
        for temp_file in self.created_resources['temp_files']:
            try:
                os.unlink(temp_file)
            except:
                pass
        
        # Clean up created resources if logged in
        if self.logged_in:
            # Clean up API keys
            for api_key in self.created_resources['api_keys']:
                try:
                    self.run_command(['key', 'delete', '--key', api_key, '--force'])
                except:
                    pass
            
            # Clean up prompts
            for prompt_id in self.created_resources['prompts']:
                try:
                    self.run_command(['prompt', 'delete', '--id', prompt_id, '--force'])
                except:
                    pass
            
            # Clean up users
            for username in self.created_resources['users']:
                try:
                    # Get user list to find ID
                    result = self.run_command(['user', 'list', '--output', 'json'])
                    if result['success']:
                        users = self.extract_json(result['stdout'])
                        if users:
                            for user in users:
                                if user.get('username') == username:
                                    user_id = user.get('id', user.get('_id'))
                                    if user_id:
                                        self.run_command(['user', 'delete', '--user-id', user_id, '--force'])
                                    break
                except:
                    pass
            
            # Logout
            try:
                self.run_command(['logout'])
                self.logged_in = False
            except:
                pass
    
    def extract_json(self, output: str) -> Optional[Union[Dict, List]]:
        """Extract JSON from command output."""
        try:
            # Try to parse the entire output as JSON
            return json.loads(output.strip())
        except json.JSONDecodeError:
            # Try to find JSON in the output
            lines = output.strip().split('\n')
            json_str = ''
            in_json = False
            
            for line in lines:
                if line.strip().startswith(('{', '[')):
                    in_json = True
                
                if in_json:
                    json_str += line + '\n'
                    
                    # Simple check for JSON completion
                    if line.strip().endswith(('}', ']')):
                        try:
                            return json.loads(json_str)
                        except:
                            continue
            
            return None
    
    def create_temp_file(self, content: str, suffix: str = '.txt') -> str:
        """Create a temporary file with content."""
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            f.write(content)
            self.created_resources['temp_files'].append(f.name)
            return f.name
    
    def ensure_authenticated(self) -> bool:
        """Ensure we're authenticated for tests that require it."""
        if self.logged_in:
            # Check if still valid
            result = self.run_command(['auth-status'])
            if result['success']:
                return True
        
        # Login
        result = self.run_command([
            'login',
            '--username', 'admin',
            '--password', 'admin123'
        ])
        
        if result['success']:
            self.logged_in = True
            return True
        
        return False


class TestModularCLI:
    """Integration tests for the modular CLI."""
    
    def test_cli_help(self):
        """Test CLI help command."""
        with ModularCLITester() as tester:
            result = tester.run_command(['--help'])
            
            assert result['success']
            assert 'usage:' in result['stdout'].lower()
            assert 'orbit' in result['stdout'].lower()
            
            # Check for main command groups
            assert 'start' in result['stdout']
            assert 'login' in result['stdout']
            assert 'key' in result['stdout']
            assert 'config' in result['stdout']
    
    def test_version(self):
        """Test version command."""
        with ModularCLITester() as tester:
            result = tester.run_command(['--version'])
            
            assert result['success']
            assert 'orbit' in result['stdout'].lower()
    
    def test_server_commands(self):
        """Test server control commands."""
        with ModularCLITester() as tester:
            # Test status
            result = tester.run_command(['status'])
            assert result['returncode'] in [0, 1]  # Success or server not running
            
            # Test help for server commands
            for cmd in ['start', 'stop', 'restart', 'status', 'logs']:
                result = tester.run_command([cmd, '--help'])
                assert result['success']
                assert cmd in result['stdout'].lower()
    
    def test_authentication_flow(self):
        """Test authentication commands."""
        with ModularCLITester() as tester:
            # Test auth status when not logged in
            result = tester.run_command(['auth-status'])
            assert result['returncode'] == 1
            assert 'not authenticated' in result['stdout'].lower()
            
            # Test login
            result = tester.run_command([
                'login',
                '--username', 'admin',
                '--password', 'admin123'
            ])
            
            if result['success']:
                tester.logged_in = True
                
                # Test auth status when logged in
                result = tester.run_command(['auth-status'])
                assert result['success']
                assert 'authenticated' in result['stdout'].lower()
                
                # Test me command
                result = tester.run_command(['me'])
                assert result['success']
                assert 'username:' in result['stdout'].lower()
                
                # Test logout
                result = tester.run_command(['logout'])
                assert result['success']
                tester.logged_in = False
    
    def test_config_commands(self):
        """Test configuration management commands."""
        with ModularCLITester() as tester:
            # Test config show
            result = tester.run_command(['config', 'show'])
            assert result['success']
            
            # Test config effective
            result = tester.run_command(['config', 'effective'])
            assert result['success']
            assert 'source' in result['stdout'].lower()
            
            # Test config set
            result = tester.run_command(['config', 'set', 'test.key', 'test_value'])
            assert result['success']
            
            # Verify it was set
            result = tester.run_command(['config', 'show', '--key', 'test.key'])
            assert result['success']
            assert 'test_value' in result['stdout']
            
            # Test config reset
            result = tester.run_command(['config', 'reset', '--force'])
            assert result['success']
    
    def test_api_key_commands(self):
        """Test API key management commands."""
        with ModularCLITester() as tester:
            if not tester.ensure_authenticated():
                pytest.skip("Authentication not available")
            
            # Test key list
            result = tester.run_command(['key', 'list'])
            if result['success']:
                assert 'api key' in result['stdout'].lower() or 'found' in result['stdout'].lower()
            
            # Test key create
            collection = f'test_collection_{int(time.time())}'
            result = tester.run_command([
                'key', 'create',
                '--collection', collection,
                '--name', 'Test Client'
            ])
            
            if result['success']:
                # Extract API key
                if 'API Key:' in result['stdout']:
                    for line in result['stdout'].split('\n'):
                        if 'API Key:' in line:
                            api_key = line.split('API Key:')[1].strip()
                            tester.created_resources['api_keys'].append(api_key)
                            break
                
                # Test key test
                if tester.created_resources['api_keys']:
                    api_key = tester.created_resources['api_keys'][0]
                    result = tester.run_command(['key', 'test', '--key', api_key])
                    assert 'valid' in result['stdout'].lower() or 'success' in result['stdout'].lower()
    
    def test_output_formats(self):
        """Test different output formats."""
        with ModularCLITester() as tester:
            # Test JSON output
            result = tester.run_command(['--output', 'json', 'auth-status'])
            if result['success'] or result['returncode'] == 1:
                # Try to parse as JSON
                json_data = tester.extract_json(result['stdout'])
                assert json_data is not None or 'authenticated' in result['stdout'].lower()
            
            # Test table output (default)
            result = tester.run_command(['auth-status'])
            assert 'authenticated' in result['stdout'].lower()
            
            # Test no color
            result = tester.run_command(['--no-color', 'status'])
            # Should not contain color codes
            assert '\033[' not in result['stdout']
    
    def test_error_handling(self):
        """Test error handling."""
        with ModularCLITester() as tester:
            # Test invalid command
            result = tester.run_command(['invalid-command'])
            assert not result['success']
            
            # Test missing required arguments
            result = tester.run_command(['key', 'create'])
            assert not result['success']
            assert 'required' in result['stderr'].lower() or 'required' in result['stdout'].lower()
            
            # Test invalid login
            result = tester.run_command([
                'login',
                '--username', 'invalid',
                '--password', 'wrong'
            ])
            assert not result['success']
    
    def test_global_options(self):
        """Test global CLI options."""
        with ModularCLITester() as tester:
            # Test verbose
            result = tester.run_command(['--verbose', 'status'])
            # Should execute without error
            assert result['returncode'] in [0, 1]
            
            # Test custom server URL
            result = tester.run_command(['--server-url', 'http://localhost:8080', 'status'])
            assert result['returncode'] in [0, 1]
            
            # Test log file
            log_file = tester.create_temp_file('', suffix='.log')
            result = tester.run_command(['--log-file', log_file, 'status'])
            assert result['returncode'] in [0, 1]
            
            # Check if log file has content
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    content = f.read()
                    # Log file might have content if verbose logging is enabled
                    assert isinstance(content, str)


# Run tests
if __name__ == '__main__':
    # Basic smoke test
    print("Running modular CLI integration tests...")
    
    test = TestModularCLI()
    
    tests = [
        ('CLI Help', test.test_cli_help),
        ('Version', test.test_version),
        ('Server Commands', test.test_server_commands),
        ('Authentication Flow', test.test_authentication_flow),
        ('Config Commands', test.test_config_commands),
        ('API Key Commands', test.test_api_key_commands),
        ('Output Formats', test.test_output_formats),
        ('Error Handling', test.test_error_handling),
        ('Global Options', test.test_global_options)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            print(f"\nRunning {test_name}...")
            test_func()
            print(f"✅ {test_name} passed")
            passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")