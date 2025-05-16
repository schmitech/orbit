#!/usr/bin/env python3
"""
ORBIT Control CLI
================================

A command-line tool to manage the ORBIT server.
Provides server control, API key management, and system prompt management.

This tool combines server management with API administration features.

Server Control Commands:
    orbit start [--config CONFIG_PATH] [--host HOST] [--port PORT] [--reload]
    orbit stop
    orbit restart [--config CONFIG_PATH] [--host HOST] [--port PORT]
    orbit status

API Key Management Commands:
    orbit key create --collection COLLECTION --name NAME [--notes NOTES]
    orbit key list
    orbit key status --key KEY
    orbit key test --key KEY
    orbit key deactivate --key KEY
    orbit key delete --key KEY

System Prompt Management Commands:
    orbit prompt create --name NAME --file FILE [--version VERSION]
    orbit prompt list
    orbit prompt get --id ID
    orbit prompt update --id ID --file FILE [--version VERSION]
    orbit prompt delete --id ID
    orbit prompt associate --key KEY --prompt-id PROMPT_ID

Integrated Commands (API Key + Prompt):
    orbit key create --collection COLLECTION --name NAME --prompt-file FILE --prompt-name NAME
    orbit key create --collection COLLECTION --name NAME --prompt-id ID

Examples:
    # Start the server
    orbit start --config config.yaml --port 3000

    # Create API key with a new prompt
    orbit key create --collection city --name "City Assistant" \
      --prompt-file prompts/examples/city/city-assistant-normal-prompt.txt \
      --prompt-name "Municipal Assistant Prompt"

    # Create API key with an existing prompt
    orbit key create --collection legal --name "Legal Team" --prompt-id 612a4b3c78e9f25d3e1f42a7

    # List all API keys
    orbit key list

    # Test an API key
    orbit key test --key orbit_abcd1234

    # Create a standalone prompt
    orbit prompt create --name "Support Assistant" \
      --file prompts/support.txt --version "1.0"

    # Associate an existing prompt with an API key
    orbit prompt associate --key orbit_abcd1234 --prompt-id 612a4b3c78e9f25d3e1f42a7

    # Get server status
    orbit status

    # Stop the server
    orbit stop
"""

import os
import sys
import signal
import argparse
import psutil
import subprocess
import time
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List
import dotenv


# Server Controller for start/stop/restart/status
class ServerController:
    """Controller class for managing the Open Inference Server process."""
    
    def __init__(self, pid_file: str = "server.pid"):
        """
        Initialize the server controller.
        
        Args:
            pid_file: Path to the PID file for tracking the server process
        """
        # Get the directory where this script is located and find project root
        script_dir = Path(__file__).parent
        self.project_root = script_dir.parent
        
        self.pid_file = self.project_root / pid_file
        self.log_file = self.project_root / "logs" / "orbit.log"
    
    def _read_pid(self) -> Optional[int]:
        """
        Read the PID from the PID file.
        
        Returns:
            The PID if the file exists and is valid, None otherwise
        """
        if not self.pid_file.exists():
            return None
        
        try:
            with open(self.pid_file, 'r') as f:
                return int(f.read().strip())
        except (ValueError, IOError):
            return None
    
    def _write_pid(self, pid: int) -> None:
        """
        Write the PID to the PID file.
        
        Args:
            pid: The process ID to write
        """
        with open(self.pid_file, 'w') as f:
            f.write(str(pid))
    
    def _remove_pid_file(self) -> None:
        """Remove the PID file if it exists."""
        if self.pid_file.exists():
            self.pid_file.unlink()
    
    def _is_process_running(self, pid: int) -> bool:
        """
        Check if a process with the given PID is running.
        
        Args:
            pid: The process ID to check
            
        Returns:
            True if the process is running, False otherwise
        """
        try:
            process = psutil.Process(pid)
            # Check if this is actually our server process
            cmdline = ' '.join(process.cmdline())
            return 'server.py' in cmdline or 'main.py' in cmdline
        except psutil.NoSuchProcess:
            return False
    
    def start(self, config_path: Optional[str] = None, 
              host: Optional[str] = None, 
              port: Optional[int] = None,
              reload: bool = False,
              delete_logs: bool = False) -> bool:
        """
        Start the server if it's not already running.
        
        Args:
            config_path: Optional path to the configuration file
            host: Optional host to bind to
            port: Optional port to bind to
            reload: Whether to enable auto-reload for development
            delete_logs: Whether to delete the logs folder before starting
            
        Returns:
            True if the server was started successfully, False otherwise
        """
        # Check if server is already running
        pid = self._read_pid()
        if pid and self._is_process_running(pid):
            print(f"Server is already running with PID {pid}")
            return False
        
        # Clean up stale PID file
        self._remove_pid_file()
        
        # Delete logs if requested
        if delete_logs and self.log_file.parent.exists():
            import shutil
            shutil.rmtree(self.log_file.parent)
            print("Logs folder deleted.")
        
        # Build the command to start the server
        # Change to project root and run main.py from server directory
        os.chdir(self.project_root)
        cmd = ["python", "server/main.py"]
        
        if config_path:
            # Resolve config path relative to project root
            if not os.path.isabs(config_path):
                config_path = str(self.project_root / config_path)
            cmd.extend(["--config", config_path])
        else:
            # Try to find config file in common locations
            possible_configs = [
                self.project_root / "server" / "config.yaml",
                self.project_root / "config.yaml",
                self.project_root / "config" / "config.yaml"
            ]
            for config in possible_configs:
                if config.exists():
                    cmd.extend(["--config", str(config)])
                    break
        
        # Set environment variables if host/port specified
        env = os.environ.copy()
        if host:
            env["OIS_HOST"] = host
        if port:
            env["OIS_PORT"] = str(port)
        
        # Add reload flag if requested
        if reload:
            # For reload mode, we'll use uvicorn directly from server directory
            cmd = ["uvicorn", "server:app", "--reload"]
            if host:
                cmd.extend(["--host", host])
            if port:
                cmd.extend(["--port", str(port)])
            # Change to server directory for reload mode
            os.chdir(self.project_root / "server")
        
        print(f"Starting server with command: {' '.join(cmd)}")
        
        # Start the server process
        try:
            # Ensure logs directory exists
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Open log file for output
            with open(self.log_file, 'a') as log:
                if reload:
                    # For reload mode, run in foreground
                    process = subprocess.Popen(
                        cmd,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env=env
                    )
                else:
                    # For production mode, run in background
                    process = subprocess.Popen(
                        cmd,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env=env,
                        start_new_session=True  # Detach from current session
                    )
                
                # Write the PID
                self._write_pid(process.pid)
                
                # Wait a moment to check if the process started successfully
                time.sleep(2)
                
                if self._is_process_running(process.pid):
                    print(f"Server started successfully with PID {process.pid}")
                    print(f"Logs are being written to {self.log_file}")
                    return True
                else:
                    print("Server failed to start. Check the logs for details.")
                    self._remove_pid_file()
                    return False
                    
        except Exception as e:
            print(f"Error starting server: {e}")
            self._remove_pid_file()
            return False
    
    def stop(self, timeout: int = 30, delete_logs: bool = False) -> bool:
        """
        Stop the server if it's running.
        
        Args:
            timeout: Maximum time to wait for graceful shutdown (seconds)
            delete_logs: Whether to delete the logs folder after stopping
            
        Returns:
            True if the server was stopped successfully, False otherwise
        """
        pid = self._read_pid()
        if not pid:
            print("No PID file found. Server may not be running.")
            return False
        
        if not self._is_process_running(pid):
            print(f"Server with PID {pid} is not running. Cleaning up PID file.")
            self._remove_pid_file()
            return True
        
        print(f"Stopping server with PID {pid}...")
        
        try:
            # Send SIGTERM for graceful shutdown
            os.kill(pid, signal.SIGTERM)
            
            # Wait for the process to terminate
            start_time = time.time()
            while time.time() - start_time < timeout:
                if not self._is_process_running(pid):
                    print("Server stopped successfully.")
                    self._remove_pid_file()
                    
                    # Delete logs if requested
                    if delete_logs and self.log_file.parent.exists():
                        import shutil
                        shutil.rmtree(self.log_file.parent)
                        print("Logs folder deleted.")
                    
                    return True
                time.sleep(0.5)
            
            # If still running, force kill
            print(f"Server did not stop gracefully. Force killing PID {pid}...")
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)
            
            if not self._is_process_running(pid):
                print("Server force stopped.")
                self._remove_pid_file()
                return True
            else:
                print("Failed to stop server.")
                return False
                
        except ProcessLookupError:
            print("Server process not found. Cleaning up PID file.")
            self._remove_pid_file()
            return True
        except Exception as e:
            print(f"Error stopping server: {e}")
            return False
    
    def restart(self, config_path: Optional[str] = None,
                host: Optional[str] = None,
                port: Optional[int] = None,
                delete_logs: bool = False) -> bool:
        """
        Restart the server.
        
        Args:
            config_path: Optional path to the configuration file
            host: Optional host to bind to
            port: Optional port to bind to
            delete_logs: Whether to delete the logs folder during restart
            
        Returns:
            True if the server was restarted successfully, False otherwise
        """
        print("Restarting server...")
        
        # Stop the server if it's running
        if self._read_pid():
            if not self.stop(delete_logs=delete_logs):
                print("Failed to stop server for restart.")
                return False
            
            # Wait a moment before starting again
            time.sleep(2)
        
        # Start the server with new configuration
        return self.start(config_path=config_path, host=host, port=port, delete_logs=delete_logs)
    
    def status(self) -> Dict[str, Any]:
        """
        Get the status of the server.
        
        Returns:
            A dictionary containing status information
        """
        pid = self._read_pid()
        
        if not pid:
            return {
                "status": "stopped",
                "message": "Server is not running (no PID file found)"
            }
        
        if not self._is_process_running(pid):
            return {
                "status": "stopped",
                "pid": pid,
                "message": f"Server is not running (PID {pid} not found)"
            }
        
        try:
            process = psutil.Process(pid)
            return {
                "status": "running",
                "pid": pid,
                "uptime": time.time() - process.create_time(),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "cpu_percent": process.cpu_percent(),
                "message": f"Server is running with PID {pid}"
            }
        except Exception as e:
            return {
                "status": "unknown",
                "pid": pid,
                "error": str(e),
                "message": f"Error checking server status: {e}"
            }


# API Manager for key and prompt management
class ApiManager:
    """Manager class for API keys and system prompts via the server API endpoints"""
    
    def __init__(self, server_url: str = None):
        """
        Initialize the API Manager
        
        Args:
            server_url: The URL of the server, e.g., 'http://localhost:3000'
                        If None, tries to load from environment variable API_SERVER_URL
        """
        # Load environment variables from .env file if it exists
        dotenv.load_dotenv()
        
        # Get server URL from args or environment
        self.server_url = server_url or os.environ.get('API_SERVER_URL', 'http://localhost:3000')
        self.server_url = self.server_url.rstrip('/')
        
        # Set admin auth token if available in environment
        self.admin_token = os.environ.get('API_ADMIN_TOKEN')
    
    def _read_file_content(self, file_path: str) -> str:
        """
        Read content from a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            Content of the file as a string
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            raise RuntimeError(f"Error reading file {file_path}: {str(e)}") from e
    
    # API Key methods
    def create_api_key(
        self, 
        collection_name: str, 
        client_name: str, 
        notes: Optional[str] = None,
        prompt_id: Optional[str] = None,
        prompt_name: Optional[str] = None,
        prompt_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key for a client, optionally with an associated system prompt
        
        Args:
            collection_name: The name of the Chroma collection to associate with this key
            client_name: The name of the client
            notes: Optional notes about this API key
            prompt_id: Optional existing system prompt ID to associate
            prompt_name: Optional name for a new system prompt
            prompt_file: Optional path to a file containing a system prompt
            
        Returns:
            Dictionary containing the created API key details
        """
        # First handle prompt if needed
        if prompt_file and (prompt_name or prompt_id):
            prompt_text = self._read_file_content(prompt_file)
            
            if prompt_id:
                # Update an existing prompt
                prompt_result = self.update_prompt(prompt_id, prompt_text)
                prompt_id = prompt_result.get("id") or prompt_id
            elif prompt_name:
                # Create a new prompt
                prompt_result = self.create_prompt(prompt_name, prompt_text)
                prompt_id = prompt_result.get("id")
                if not prompt_id:
                    raise RuntimeError("Failed to get prompt ID from created prompt")
        
        # Now create the API key
        url = f"{self.server_url}/admin/api-keys"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        data = {
            "collection_name": collection_name,
            "client_name": client_name
        }
        
        if notes:
            data["notes"] = notes
        
        try:
            # First create the API key
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            api_key_result = response.json()
            
            # If we have a prompt ID, associate it with the API key
            if prompt_id:
                api_key = api_key_result.get("api_key")
                if not api_key:
                    raise RuntimeError("Failed to get API key from creation response")
                
                association_result = self.associate_prompt_with_api_key(api_key, prompt_id)
                api_key_result["system_prompt_id"] = prompt_id
            
            return api_key_result
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error creating API key: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error creating API key: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def list_api_keys(self) -> List[Dict[str, Any]]:
        """
        List all API keys
        
        Returns:
            List of dictionaries containing API key details
        """
        url = f"{self.server_url}/admin/api-keys"
        
        headers = {}
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error listing API keys: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error listing API keys: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def deactivate_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Deactivate an API key
        
        Args:
            api_key: The API key to deactivate
            
        Returns:
            Dictionary containing the result of the operation
        """
        url = f"{self.server_url}/admin/api-keys/deactivate"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        data = {
            "api_key": api_key
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error deactivating API key: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error deactivating API key: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def delete_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Delete an API key
        
        Args:
            api_key: The API key to delete
            
        Returns:
            Dictionary containing the result of the operation
        """
        url = f"{self.server_url}/admin/api-keys/{api_key}"
        
        headers = {}
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error deleting API key: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error deleting API key: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def get_api_key_status(self, api_key: str) -> Dict[str, Any]:
        """
        Get the status of an API key
        
        Args:
            api_key: The API key to check
            
        Returns:
            Dictionary containing the API key status
        """
        url = f"{self.server_url}/admin/api-keys/{api_key}/status"
        
        headers = {}
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error checking API key status: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error checking API key status: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def test_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Test an API key by making a simple health check request
        
        Args:
            api_key: The API key to test
            
        Returns:
            Dictionary containing the health check response or error details
        """
        url = f"{self.server_url}/health"
        
        headers = {
            "X-API-Key": api_key
        }
        
        try:
            response = requests.get(url, headers=headers)
            # Check for 401 Unauthorized which would indicate an invalid or deactivated key
            if response.status_code == 401:
                return {
                    "status": "error",
                    "error": "API key is invalid or deactivated",
                    "details": response.json() if response.headers.get('content-type') == 'application/json' else response.text
                }
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 401:
                    return {
                        "status": "error",
                        "error": "API key is invalid or deactivated",
                        "details": e.response.json() if e.response.headers.get('content-type') == 'application/json' else e.response.text
                    }
                error_msg = f"API key test failed: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"API key test failed: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    # System Prompt methods
    def create_prompt(self, name: str, prompt_text: str, version: str = "1.0") -> Dict[str, Any]:
        """
        Create a new system prompt
        
        Args:
            name: A unique name for the prompt
            prompt_text: The prompt text
            version: Version string for the prompt
            
        Returns:
            Dictionary containing the created prompt details
        """
        url = f"{self.server_url}/admin/prompts"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        data = {
            "name": name,
            "prompt": prompt_text,
            "version": version
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            return result
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error creating prompt: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error creating prompt: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def list_prompts(self) -> List[Dict[str, Any]]:
        """
        List all system prompts
        
        Returns:
            List of dictionaries containing prompt details
        """
        url = f"{self.server_url}/admin/prompts"
        
        headers = {}
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error listing prompts: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error listing prompts: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def get_prompt(self, prompt_id: str) -> Dict[str, Any]:
        """
        Get a system prompt by its ID
        
        Args:
            prompt_id: The ID of the prompt
            
        Returns:
            Dictionary containing the prompt details
        """
        url = f"{self.server_url}/admin/prompts/{prompt_id}"
        
        headers = {}
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error getting prompt: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error getting prompt: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def update_prompt(self, prompt_id: str, prompt_text: str, version: Optional[str] = None) -> Dict[str, Any]:
        """
        Update an existing system prompt
        
        Args:
            prompt_id: The ID of the prompt to update
            prompt_text: The new prompt text
            version: Optional new version string
            
        Returns:
            Dictionary containing the updated prompt details
        """
        url = f"{self.server_url}/admin/prompts/{prompt_id}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        data = {
            "prompt": prompt_text
        }
        
        if version:
            data["version"] = version
        
        try:
            response = requests.put(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error updating prompt: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error updating prompt: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def delete_prompt(self, prompt_id: str) -> Dict[str, Any]:
        """
        Delete a system prompt
        
        Args:
            prompt_id: The ID of the prompt to delete
            
        Returns:
            Dictionary containing the result of the operation
        """
        url = f"{self.server_url}/admin/prompts/{prompt_id}"
        
        headers = {}
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        try:
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error deleting prompt: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error deleting prompt: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def associate_prompt_with_api_key(self, api_key: str, prompt_id: str) -> Dict[str, Any]:
        """
        Associate a system prompt with an API key
        
        Args:
            api_key: The API key
            prompt_id: The ID of the prompt to associate
            
        Returns:
            Dictionary containing the result of the operation
        """
        url = f"{self.server_url}/admin/api-keys/{api_key}/prompt"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add admin token if available
        if self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        
        data = {
            "prompt_id": prompt_id
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Error associating prompt with API key: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Error associating prompt with API key: {str(e)}"
            raise RuntimeError(error_msg) from e


# Main CLI class that ties everything together
class OrbitCLI:
    """Main CLI class for ORBIT command-line interface."""
    
    def __init__(self):
        """Initialize the ORBIT CLI."""
        self.server_controller = ServerController()
        self.api_manager = None  # Will be initialized when needed
        
    def get_api_manager(self, server_url: Optional[str] = None) -> ApiManager:
        """Get or create the API manager instance."""
        if self.api_manager is None:
            self.api_manager = ApiManager(server_url)
        return self.api_manager
    
    def create_parser(self) -> argparse.ArgumentParser:
        """Create the argument parser for the CLI."""
        parser = argparse.ArgumentParser(
            description='ORBIT Control CLI - Manage Open Inference Server',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Server Management
  orbit start                           Start the server
  orbit stop                            Stop the server
  orbit restart                         Restart the server
  orbit status                          Check server status
  
  # API Key Management
  orbit key create --collection docs --name "Customer Support"
  orbit key list                        List all API keys
  orbit key test --key api_abcd1234     Test an API key
  orbit key delete --key api_abcd1234   Delete an API key
  
  # System Prompt Management
  orbit prompt create --name "Support" --file support.txt
  orbit prompt list                     List all prompts
  orbit prompt get --id 612a4b3c...     Get a specific prompt
  orbit prompt delete --id 612a4b3c...  Delete a prompt
  
  # Combined Operations
  orbit key create --collection legal --name "Legal Team" \\
    --prompt-file legal_prompt.txt --prompt-name "Legal Assistant"
"""
        )
        
        # Global arguments
        parser.add_argument('--server-url', help='Server URL (default: from environment or localhost:3000)')
        
        # Create subparsers for different commands
        subparsers = parser.add_subparsers(dest='command', help='Command to execute')
        
        # Server control commands
        self._add_server_commands(subparsers)
        
        # API key management commands
        self._add_key_commands(subparsers)
        
        # System prompt management commands
        self._add_prompt_commands(subparsers)
        
        return parser
    
    def _add_server_commands(self, subparsers):
        """Add server control commands to the subparsers."""
        # Start command
        start_parser = subparsers.add_parser('start', help='Start the server')
        start_parser.add_argument('--config', type=str, help='Path to configuration file')
        start_parser.add_argument('--host', type=str, help='Host to bind to')
        start_parser.add_argument('--port', type=int, help='Port to bind to')
        start_parser.add_argument('--reload', action='store_true', help='Enable auto-reload for development')
        start_parser.add_argument('--delete-logs', action='store_true', help='Delete logs folder before starting')
        
        # Stop command
        stop_parser = subparsers.add_parser('stop', help='Stop the server')
        stop_parser.add_argument('--timeout', type=int, default=30, help='Timeout for graceful shutdown (seconds)')
        stop_parser.add_argument('--delete-logs', action='store_true', help='Delete logs folder after stopping')
        
        # Restart command
        restart_parser = subparsers.add_parser('restart', help='Restart the server')
        restart_parser.add_argument('--config', type=str, help='Path to configuration file')
        restart_parser.add_argument('--host', type=str, help='Host to bind to')
        restart_parser.add_argument('--port', type=int, help='Port to bind to')
        restart_parser.add_argument('--delete-logs', action='store_true', help='Delete logs folder during restart')
        
        # Status command
        status_parser = subparsers.add_parser('status', help='Check server status')
    
    def _add_key_commands(self, subparsers):
        """Add API key management commands to the subparsers."""
        key_parser = subparsers.add_parser('key', help='API key management')
        key_subparsers = key_parser.add_subparsers(dest='key_command', help='Key command to execute')
        
        # Create key command
        create_parser = key_subparsers.add_parser('create', help='Create a new API key')
        create_parser.add_argument('--collection', required=True, help='Collection name to associate with the key')
        create_parser.add_argument('--name', required=True, help='Client name')
        create_parser.add_argument('--notes', help='Optional notes about this API key')
        create_parser.add_argument('--prompt-id', help='Existing system prompt ID to associate with the key')
        create_parser.add_argument('--prompt-name', help='Name for a new system prompt')
        create_parser.add_argument('--prompt-file', help='Path to a file containing a system prompt')
        
        # List keys command
        list_parser = key_subparsers.add_parser('list', help='List all API keys')
        
        # Test key command
        test_parser = key_subparsers.add_parser('test', help='Test an API key')
        test_parser.add_argument('--key', required=True, help='API key to test')
        
        # Status command
        status_parser = key_subparsers.add_parser('status', help='Get the status of an API key')
        status_parser.add_argument('--key', required=True, help='API key to check')
        
        # Deactivate command
        deactivate_parser = key_subparsers.add_parser('deactivate', help='Deactivate an API key')
        deactivate_parser.add_argument('--key', required=True, help='API key to deactivate')
        
        # Delete command
        delete_parser = key_subparsers.add_parser('delete', help='Delete an API key')
        delete_parser.add_argument('--key', required=True, help='API key to delete')
    
    def _add_prompt_commands(self, subparsers):
        """Add system prompt management commands to the subparsers."""
        prompt_parser = subparsers.add_parser('prompt', help='System prompt management')
        prompt_subparsers = prompt_parser.add_subparsers(dest='prompt_command', help='Prompt command to execute')
        
        # Create prompt command
        create_parser = prompt_subparsers.add_parser('create', help='Create a new system prompt')
        create_parser.add_argument('--name', required=True, help='Unique name for the prompt')
        create_parser.add_argument('--file', required=True, help='Path to a file containing the prompt text')
        create_parser.add_argument('--version', default='1.0', help='Version string (default: 1.0)')
        
        # List prompts command
        list_parser = prompt_subparsers.add_parser('list', help='List all system prompts')
        
        # Get prompt command
        get_parser = prompt_subparsers.add_parser('get', help='Get a system prompt by ID')
        get_parser.add_argument('--id', required=True, help='Prompt ID')
        
        # Update prompt command
        update_parser = prompt_subparsers.add_parser('update', help='Update an existing system prompt')
        update_parser.add_argument('--id', required=True, help='Prompt ID to update')
        update_parser.add_argument('--file', required=True, help='Path to a file containing the updated prompt text')
        update_parser.add_argument('--version', help='New version string')
        
        # Delete prompt command
        delete_parser = prompt_subparsers.add_parser('delete', help='Delete a system prompt')
        delete_parser.add_argument('--id', required=True, help='Prompt ID to delete')
        
        # Associate prompt with API key command
        associate_parser = prompt_subparsers.add_parser('associate', help='Associate a system prompt with an API key')
        associate_parser.add_argument('--key', required=True, help='API key')
        associate_parser.add_argument('--prompt-id', required=True, help='Prompt ID to associate')
    
    def execute(self, args):
        """Execute the parsed command."""
        # Handle server control commands
        if args.command == 'start':
            success = self.server_controller.start(
                config_path=args.config,
                host=args.host,
                port=args.port,
                reload=args.reload,
                delete_logs=args.delete_logs
            )
            return 0 if success else 1
        
        elif args.command == 'stop':
            success = self.server_controller.stop(timeout=args.timeout, delete_logs=args.delete_logs)
            return 0 if success else 1
        
        elif args.command == 'restart':
            success = self.server_controller.restart(
                config_path=args.config,
                host=args.host,
                port=args.port,
                delete_logs=args.delete_logs
            )
            return 0 if success else 1
        
        elif args.command == 'status':
            status = self.server_controller.status()
            print(json.dumps(status, indent=2))
            return 0 if status['status'] == 'running' else 1
        
        # Handle API key commands
        elif args.command == 'key':
            api_manager = self.get_api_manager(args.server_url)
            
            if args.key_command == 'create':
                result = api_manager.create_api_key(
                    args.collection,
                    args.name,
                    args.notes,
                    args.prompt_id,
                    args.prompt_name,
                    args.prompt_file
                )
                print(json.dumps(result, indent=2))
                print("\nAPI key created successfully.")
                return 0
            
            elif args.key_command == 'list':
                result = api_manager.list_api_keys()
                print(json.dumps(result, indent=2))
                print(f"\nFound {len(result)} API keys.")
                return 0
            
            elif args.key_command == 'test':
                result = api_manager.test_api_key(args.key)
                print(json.dumps(result, indent=2))
                if result.get('status') == 'error':
                    print("\nAPI key test failed.")
                    return 1
                else:
                    print("\nAPI key test completed successfully.")
                    return 0
            
            elif args.key_command == 'status':
                result = api_manager.get_api_key_status(args.key)
                print(json.dumps(result, indent=2))
                if result.get("active"):
                    print("\nAPI key is active.")
                else:
                    print("\nAPI key is inactive.")
                return 0
            
            elif args.key_command == 'deactivate':
                result = api_manager.deactivate_api_key(args.key)
                print(json.dumps(result, indent=2))
                print("\nAPI key deactivated successfully.")
                return 0
            
            elif args.key_command == 'delete':
                result = api_manager.delete_api_key(args.key)
                print(json.dumps(result, indent=2))
                print("\nAPI key deleted successfully.")
                return 0
        
        # Handle system prompt commands
        elif args.command == 'prompt':
            api_manager = self.get_api_manager(args.server_url)
            
            if args.prompt_command == 'create':
                prompt_text = api_manager._read_file_content(args.file)
                result = api_manager.create_prompt(args.name, prompt_text, args.version)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt created successfully.")
                return 0
            
            elif args.prompt_command == 'list':
                result = api_manager.list_prompts()
                print(json.dumps(result, indent=2))
                print(f"\nFound {len(result)} system prompts.")
                return 0
            
            elif args.prompt_command == 'get':
                result = api_manager.get_prompt(args.id)
                print(json.dumps(result, indent=2))
                return 0
            
            elif args.prompt_command == 'update':
                prompt_text = api_manager._read_file_content(args.file)
                result = api_manager.update_prompt(args.id, prompt_text, args.version)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt updated successfully.")
                return 0
            
            elif args.prompt_command == 'delete':
                result = api_manager.delete_prompt(args.id)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt deleted successfully.")
                return 0
            
            elif args.prompt_command == 'associate':
                result = api_manager.associate_prompt_with_api_key(args.key, args.prompt_id)
                print(json.dumps(result, indent=2))
                print("\nSystem prompt associated with API key successfully.")
                return 0
        
        return 1


def main():
    """Main entry point for the ORBIT CLI."""
    cli = OrbitCLI()
    parser = cli.create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        exit_code = cli.execute(args)
        sys.exit(exit_code)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()