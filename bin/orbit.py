#!/usr/bin/env python3
"""
ORBIT Control CLI
================================

A command-line tool to manage the ORBIT server.
Provides server control, API key management, system prompt management, and authentication.

This tool combines server management with API administration features.

Server Control Commands:
    orbit start [--config CONFIG_PATH] [--host HOST] [--port PORT] [--reload]
    orbit stop
    orbit restart [--config CONFIG_PATH] [--host HOST] [--port PORT]
    orbit status

Authentication Commands:
    orbit login [--username USERNAME] [--password PASSWORD]  # Will prompt if not provided, token stored in ~/.orbit/.env
    orbit logout                                             # Clears token from ~/.orbit/.env
    orbit register --username USERNAME --password PASSWORD [--role ROLE]
    orbit me
    orbit change-password                                    # Interactive password change

User Management Commands:
    orbit user list
    orbit user config
    orbit user debug
    orbit auth-status
    # For full user management: python server/tests/debug_auth.py

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
    # Authentication
    orbit login --username admin --password secret123  # Or just 'orbit login' to be prompted
    orbit me
    orbit change-password                               # Change your password (interactive)
    orbit register --username newuser --password pass123 --role user
    orbit logout

    # User Management
    orbit user list                       List all users
    orbit user config                     Check auth configuration
    orbit user reset-password --username admin --password newpass
    orbit user reset-password --user-id 507f1f77bcf86cd799439011 --password newpass
    orbit user delete --user-id 507f1f77bcf86cd799439011  Delete a user
    orbit user deactivate --username user1  Deactivate a user
    orbit user activate --username user1   Activate a user
    orbit user debug                      Run debug_auth.py script
    orbit auth-status                     Check authentication status
    # For full user management: python server/tests/debug_auth.py

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

import os
import sys
import signal
import argparse
import psutil
import subprocess
import time
import json
import requests
import getpass
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
            self.log_file.parent.chmod(0o700)
            
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
        
        # Try to load token and server URL from persistent storage first
        self._load_token_from_file()
        
        # Get server URL from args, persistent storage, or environment
        self.server_url = server_url or os.environ.get('API_SERVER_URL', 'http://localhost:3000')
        self.server_url = self.server_url.rstrip('/')
        
        # Set admin auth token if available in environment (fallback)
        if not hasattr(self, 'admin_token') or not self.admin_token:
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
    
    def _save_token_to_file(self, token: str) -> None:
        """Save token to ~/.orbit/.env file for persistence"""
        orbit_dir = Path.home() / ".orbit"
        orbit_dir.mkdir(exist_ok=True, mode=0o700)
        
        env_file = orbit_dir / ".env"
        with open(env_file, 'w') as f:
            f.write(f'API_ADMIN_TOKEN={token}\n')
            f.write(f'API_SERVER_URL={self.server_url}\n')
        
        # Set secure permissions on the file
        env_file.chmod(0o600)
    
    def _load_token_from_file(self) -> Optional[str]:
        """Load token from ~/.orbit/.env file"""
        env_file = Path.home() / ".orbit" / ".env"
        if env_file.exists():
            # Use override=True to ensure personal token takes precedence
            dotenv.load_dotenv(env_file, override=True)
            self.admin_token = os.environ.get('API_ADMIN_TOKEN')
            # Also update server URL if not already set
            if not hasattr(self, 'server_url'):
                self.server_url = os.environ.get('API_SERVER_URL', 'http://localhost:3000')
            return self.admin_token
        return None
    
    def _clear_token_file(self) -> None:
        """Clear the token from ~/.orbit/.env file"""
        env_file = Path.home() / ".orbit" / ".env"
        if env_file.exists():
            env_file.unlink()
    
    def _ensure_authenticated(self) -> None:
        """Ensure user is authenticated before proceeding"""
        if not self.admin_token:
            raise RuntimeError("Authentication required. Please run 'orbit login' first.")
    
    # Authentication methods
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate a user and return a bearer token
        
        Args:
            username: The username
            password: The password
            
        Returns:
            Dictionary containing the login response with token and user info
        """
        url = f"{self.server_url}/auth/login"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "username": username,
            "password": password
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            
            # Update the admin token if login successful
            if "token" in result:
                self.admin_token = result["token"]
                # Save to environment variable for future use (session)
                os.environ["API_ADMIN_TOKEN"] = self.admin_token
                # Save to persistent file storage
                self._save_token_to_file(self.admin_token)
            
            return result
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Login failed: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Login failed: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def logout(self) -> Dict[str, Any]:
        """
        Logout the current user by invalidating their token
        
        Returns:
            Dictionary containing the logout response
        """
        if not self.admin_token:
            return {"message": "Not logged in"}
        
        url = f"{self.server_url}/auth/logout"
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = requests.post(url, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            # Clear the admin token
            self.admin_token = None
            if "API_ADMIN_TOKEN" in os.environ:
                del os.environ["API_ADMIN_TOKEN"]
            # Clear the persistent token file
            self._clear_token_file()
            
            return result
        except requests.exceptions.RequestException as e:
            # Clear token anyway even if server logout fails
            self.admin_token = None
            if "API_ADMIN_TOKEN" in os.environ:
                del os.environ["API_ADMIN_TOKEN"]
            # Clear the persistent token file
            self._clear_token_file()
            
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Logout failed: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Logout failed: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def register_user(self, username: str, password: str, role: str = "user") -> Dict[str, Any]:
        """
        Register a new user (admin only)
        
        Args:
            username: The username for the new user
            password: The password for the new user
            role: The role for the new user (default: "user")
            
        Returns:
            Dictionary containing the registration response
        """
        self._ensure_authenticated()
        
        url = f"{self.server_url}/auth/register"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        data = {
            "username": username,
            "password": password,
            "role": role
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Registration failed: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Registration failed: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def get_current_user(self) -> Dict[str, Any]:
        """
        Get information about the currently authenticated user
        
        Returns:
            Dictionary containing the current user information
        """
        self._ensure_authenticated()
        
        url = f"{self.server_url}/auth/me"
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                error_msg = f"Failed to get current user: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Failed to get current user: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    # User Management utilities (from debug_auth.py)
    def check_config_password(self) -> Dict[str, Any]:
        """
        Check what password the server is configured to use
        
        Returns:
            Dictionary containing configuration information
        """
        # This endpoint doesn't exist, so we'll return a message
        return {
            "message": "Auth configuration endpoint not available",
            "note": "Use debug_auth.py script for detailed configuration inspection"
        }
    
    def list_users(self) -> List[Dict[str, Any]]:
        """
        List all users in the system
        
        Returns:
            List of dictionaries containing user information
        """
        self._ensure_authenticated()
        
        # Try to get users through the auth service
        url = f"{self.server_url}/auth/users"
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 404:
                    raise RuntimeError("User management endpoint not found. Check if the server is running and authentication is enabled.")
                elif e.response.status_code == 500:
                    raise RuntimeError(f"Server error while listing users: {e.response.text}")
                elif e.response.status_code == 403:
                    raise RuntimeError("Admin privileges required to list users.")
                error_msg = f"Failed to list users: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Failed to list users: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def reset_user_password(self, user_id: str, new_password: str) -> Dict[str, Any]:
        """
        Reset a user's password (admin only)
        
        Args:
            user_id: The user ID whose password to reset
            new_password: The new password
            
        Returns:
            Dictionary containing the result of the operation
        """
        self._ensure_authenticated()
        
        url = f"{self.server_url}/auth/reset-password"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        data = {
            "user_id": user_id,
            "new_password": new_password
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 403:
                    raise RuntimeError("Admin privileges required to reset user passwords.")
                elif e.response.status_code == 404:
                    raise RuntimeError("User not found or password reset failed.")
                elif e.response.status_code == 400:
                    raise RuntimeError("Use change-password to change your own password.")
                error_msg = f"Failed to reset password: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Failed to reset password: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def find_user_id_by_username(self, username: str) -> str:
        """
        Find a user's ID by their username
        
        Args:
            username: The username to search for
            
        Returns:
            The user ID if found
            
        Raises:
            RuntimeError: If user is not found
        """
        self._ensure_authenticated()
        
        # Get all users and find the one with matching username
        users = self.list_users()
        for user in users:
            if user.get('username') == username:
                user_id = user.get('_id') or user.get('id')
                if user_id:
                    return user_id
        
        raise RuntimeError(f"User with username '{username}' not found")
    
    def delete_user(self, user_id: str) -> Dict[str, Any]:
        """
        Delete a user
        
        Args:
            user_id: The user ID to delete
            
        Returns:
            Dictionary containing the result of the operation
        """
        self._ensure_authenticated()
        
        url = f"{self.server_url}/auth/users/{user_id}"
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = requests.delete(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 404:
                    raise RuntimeError("User not found or could not be deleted.")
                elif e.response.status_code == 403:
                    raise RuntimeError("Admin privileges required to delete users.")
                elif e.response.status_code == 400:
                    raise RuntimeError("Cannot delete your own account or invalid request.")
                error_msg = f"Failed to delete user: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Failed to delete user: {str(e)}"
            raise RuntimeError(error_msg) from e
    
    def deactivate_user(self, username: str) -> Dict[str, Any]:
        """
        Deactivate a user
        
        Args:
            username: The username to deactivate
            
        Returns:
            Dictionary containing the result of the operation
        """
        return {
            "message": "User deactivation endpoint not available",
            "note": "Use debug_auth.py script for user management",
            "username": username
        }
    
    def activate_user(self, username: str) -> Dict[str, Any]:
        """
        Activate a user
        
        Args:
            username: The username to activate
            
        Returns:
            Dictionary containing the result of the operation
        """
        return {
            "message": "User activation endpoint not available",
            "note": "Use debug_auth.py script for user management",
            "username": username
        }
    
    def check_auth_status(self) -> Dict[str, Any]:
        """
        Check authentication status and token validity
        
        Returns:
            Dictionary containing authentication status
        """
        if not self.admin_token:
            return {
                "authenticated": False,
                "message": "No authentication token found"
            }
        
        try:
            # Try to get current user info to validate token
            user_info = self.get_current_user()
            return {
                "authenticated": True,
                "token": f"{self.admin_token[:8]}...",
                "user": user_info,
                "message": "Token is valid"
            }
        except Exception as e:
            return {
                "authenticated": False,
                "token": f"{self.admin_token[:8]}...",
                "error": str(e),
                "message": "Token is invalid or expired"
            }
    
    def change_password(self, current_password: str, new_password: str) -> Dict[str, Any]:
        """
        Change the current user's password
        
        Args:
            current_password: The current password
            new_password: The new password
            
        Returns:
            Dictionary containing the result of the operation
        """
        self._ensure_authenticated()
        
        url = f"{self.server_url}/auth/change-password"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        data = {
            "current_password": current_password,
            "new_password": new_password
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 400:
                    raise RuntimeError("Current password is incorrect or password change failed.")
                error_msg = f"Failed to change password: {e.response.status_code} {e.response.text}"
            else:
                error_msg = f"Failed to change password: {str(e)}"
            raise RuntimeError(error_msg) from e
    
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
        self._ensure_authenticated()
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
        self._ensure_authenticated()
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
        self._ensure_authenticated()
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
        self._ensure_authenticated()
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
        self._ensure_authenticated()
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
        self._ensure_authenticated()
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
        self._ensure_authenticated()
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
        self._ensure_authenticated()
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
        self._ensure_authenticated()
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
        self._ensure_authenticated()
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
        self._ensure_authenticated()
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
  # Authentication
  orbit login --username admin --password secret123  # Or just 'orbit login' to be prompted
  orbit me
  orbit change-password                               # Change your password (interactive)
  orbit register --username newuser --password pass123 --role user
  orbit logout
  
  # User Management
  orbit user list                       List all users
  orbit user config                     Check auth configuration
  orbit user reset-password --username admin --password newpass
  orbit user reset-password --user-id 507f1f77bcf86cd799439011 --password newpass
  orbit user delete --user-id 507f1f77bcf86cd799439011  Delete a user
  orbit user deactivate --username user1  Deactivate a user
  orbit user activate --username user1   Activate a user
  orbit user debug                      Run debug_auth.py script
  orbit auth-status                     Check authentication status
  # For full user management: python server/tests/debug_auth.py
  
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
        
        # Authentication commands
        self._add_auth_commands(subparsers)
        
        # API key management commands
        self._add_key_commands(subparsers)
        
        # System prompt management commands
        self._add_prompt_commands(subparsers)
        
        # User management commands
        self._add_user_commands(subparsers)
        
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
    
    def _add_auth_commands(self, subparsers):
        """Add authentication commands to the subparsers."""
        # Login command
        login_parser = subparsers.add_parser('login', help='Login to the server')
        login_parser.add_argument('--username', '-u', help='Username (will prompt if not provided)')
        login_parser.add_argument('--password', '-p', help='Password (will prompt if not provided)')
        
        # Logout command
        logout_parser = subparsers.add_parser('logout', help='Logout from the server')
        
        # Register command
        register_parser = subparsers.add_parser('register', help='Register a new user (admin only)')
        register_parser.add_argument('--username', '-u', required=True, help='Username for the new user')
        register_parser.add_argument('--password', '-p', required=True, help='Password for the new user')
        register_parser.add_argument('--role', '-r', default='user', help='Role for the new user (default: user)')
        
        # Me command
        me_parser = subparsers.add_parser('me', help='Get current user information')
        
        # Auth status command
        auth_status_parser = subparsers.add_parser('auth-status', help='Check authentication status')
        
        # Change password command
        change_password_parser = subparsers.add_parser('change-password', help='Change your password')
        change_password_parser.add_argument('--current-password', help='Current password (will prompt if not provided)')
        change_password_parser.add_argument('--new-password', help='New password (will prompt if not provided)')
    
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
    
    def _add_user_commands(self, subparsers):
        """Add user management commands to the subparsers."""
        user_parser = subparsers.add_parser('user', help='User management')
        user_subparsers = user_parser.add_subparsers(dest='user_command', help='User command to execute')
        
        # List users command
        list_parser = user_subparsers.add_parser('list', help='List all users')
        
        # Check config command
        config_parser = user_subparsers.add_parser('config', help='Check authentication configuration')
        
        # Reset password command
        reset_parser = user_subparsers.add_parser('reset-password', help='Reset a user password (admin only)')
        reset_group = reset_parser.add_mutually_exclusive_group(required=True)
        reset_group.add_argument('--user-id', help='User ID to reset password for')
        reset_group.add_argument('--username', help='Username to reset password for')
        reset_parser.add_argument('--password', required=True, help='New password')
        
        # Delete user command
        delete_parser = user_subparsers.add_parser('delete', help='Delete a user')
        delete_parser.add_argument('--user-id', required=True, help='User ID to delete')
        
        # Deactivate user command
        deactivate_parser = user_subparsers.add_parser('deactivate', help='Deactivate a user')
        deactivate_parser.add_argument('--username', required=True, help='Username to deactivate')
        
        # Activate user command
        activate_parser = user_subparsers.add_parser('activate', help='Activate a user')
        activate_parser.add_argument('--username', required=True, help='Username to activate')
        
        # Debug auth command
        debug_parser = user_subparsers.add_parser('debug', help='Run debug_auth.py script for user management')
    
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
        
        # Handle authentication commands
        elif args.command == 'login':
            api_manager = self.get_api_manager(args.server_url)
            try:
                # Prompt for username if not provided
                username = args.username
                if not username:
                    username = input("Username: ")
                    if not username:
                        print("Username is required.", file=sys.stderr)
                        return 1
                
                # Prompt for password if not provided
                password = args.password
                if not password:
                    password = getpass.getpass("Password: ")
                    if not password:
                        print("Password is required.", file=sys.stderr)
                        return 1
                
                result = api_manager.login(username, password)
                print(json.dumps(result, indent=2))
                print("\nLogin successful.")
                return 0
            except Exception as e:
                print(f"Login failed: {str(e)}", file=sys.stderr)
                return 1
        
        elif args.command == 'logout':
            api_manager = self.get_api_manager(args.server_url)
            try:
                result = api_manager.logout()
                print(json.dumps(result, indent=2))
                print("\nLogout successful.")
                return 0
            except Exception as e:
                error_msg = str(e)
                # Handle case where token is already invalid (e.g., after password change)
                if "401" in error_msg and ("Invalid" in error_msg or "expired" in error_msg):
                    print("Already logged out (token was invalid or expired).")
                    # Clear the token file anyway
                    api_manager._clear_token_file()
                    return 0
                else:
                    print(f"Logout failed: {error_msg}", file=sys.stderr)
                    return 1
        
        elif args.command == 'register':
            api_manager = self.get_api_manager(args.server_url)
            try:
                result = api_manager.register_user(args.username, args.password, args.role)
                print(json.dumps(result, indent=2))
                print("\nUser registered successfully.")
                return 0
            except Exception as e:
                print(f"Registration failed: {str(e)}", file=sys.stderr)
                return 1
        
        elif args.command == 'me':
            api_manager = self.get_api_manager(args.server_url)
            try:
                result = api_manager.get_current_user()
                print(json.dumps(result, indent=2))
                return 0
            except Exception as e:
                print(f"Failed to get user info: {str(e)}", file=sys.stderr)
                return 1
        
        elif args.command == 'auth-status':
            api_manager = self.get_api_manager(args.server_url)
            try:
                result = api_manager.check_auth_status()
                print(json.dumps(result, indent=2))
                return 0 if result['authenticated'] else 1
            except Exception as e:
                print(f"Failed to check authentication status: {str(e)}", file=sys.stderr)
                return 1
        
        elif args.command == 'change-password':
            api_manager = self.get_api_manager(args.server_url)
            try:
                # Prompt for current password if not provided
                current_password = args.current_password
                if not current_password:
                    current_password = getpass.getpass("Enter current password: ")
                    if not current_password:
                        print("Current password is required.", file=sys.stderr)
                        return 1
                
                # Prompt for new password if not provided
                new_password = args.new_password
                if not new_password:
                    new_password = getpass.getpass("Enter new password: ")
                    if not new_password:
                        print("New password is required.", file=sys.stderr)
                        return 1
                    
                    # Confirm new password
                    confirm_password = getpass.getpass("Confirm new password: ")
                    if new_password != confirm_password:
                        print("New passwords do not match.", file=sys.stderr)
                        return 1
                
                result = api_manager.change_password(current_password, new_password)
                print(json.dumps(result, indent=2))
                print("\nPassword changed successfully!")
                print("Note: All sessions have been invalidated for security.")
                print("You will need to login again with your new password.")
                # Clear the local token since it's now invalid
                api_manager._clear_token_file()
                return 0
            except Exception as e:
                print(f"Failed to change password: {str(e)}", file=sys.stderr)
                return 1
        
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
        
        # Handle user commands
        elif args.command == 'user':
            api_manager = self.get_api_manager(args.server_url)
            
            if args.user_command == 'list':
                result = api_manager.list_users()
                print(json.dumps(result, indent=2))
                print(f"\nFound {len(result)} users.")
                return 0
            
            elif args.user_command == 'config':
                result = api_manager.check_config_password()
                print(json.dumps(result, indent=2))
                return 0
            
            elif args.user_command == 'reset-password':
                try:
                    # Determine user ID from either --user-id or --username
                    user_id = args.user_id
                    if args.username:
                        user_id = api_manager.find_user_id_by_username(args.username)
                    
                    result = api_manager.reset_user_password(user_id, args.password)
                    print(json.dumps(result, indent=2))
                    print("\nUser password reset successfully.")
                    return 0
                except Exception as e:
                    print(f"Failed to reset user password: {str(e)}", file=sys.stderr)
                    return 1
            
            elif args.user_command == 'delete':
                try:
                    result = api_manager.delete_user(args.user_id)
                    print(json.dumps(result, indent=2))
                    print("\nUser deleted successfully.")
                    return 0
                except Exception as e:
                    print(f"Failed to delete user: {str(e)}", file=sys.stderr)
                    return 1
            
            elif args.user_command == 'deactivate':
                result = api_manager.deactivate_user(args.username)
                print(json.dumps(result, indent=2))
                print("\nUser deactivated successfully.")
                return 0
            
            elif args.user_command == 'activate':
                result = api_manager.activate_user(args.username)
                print(json.dumps(result, indent=2))
                print("\nUser activated successfully.")
                return 0
            
            elif args.user_command == 'debug':
                # Run the debug_auth.py script
                debug_script_path = self.server_controller.project_root / "server" / "tests" / "debug_auth.py"
                if debug_script_path.exists():
                    print("Running debug_auth.py script for user management...")
                    print("This script provides detailed user management capabilities.")
                    print(f"Script location: {debug_script_path}")
                    print("\nTo run manually:")
                    print(f"cd {self.server_controller.project_root}/server/tests")
                    print("python debug_auth.py")
                    return 0
                else:
                    print(f"Debug script not found at: {debug_script_path}")
                    return 1
        
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