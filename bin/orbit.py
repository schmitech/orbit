#!/usr/bin/env python3
"""
ORBIT Control CLI
================================

A command-line tool to manage the ORBIT server.
Provides server control, API key management, system prompt management, and authentication.

This tool combines server management with API administration features.

Global Options:
    --version                    Show version information
    --server-url URL            Server URL (default: from config or localhost:3000)
    --config PATH               Path to configuration file
    -v, --verbose               Enable verbose output
    --output {table,json}       Output format (default: table)
    --no-color                  Disable colored output
    --log-file PATH             Path to log file

Server Control Commands:
    orbit start [--config CONFIG_PATH] [--host HOST] [--port PORT] [--reload] [--delete-logs]
    orbit stop [--timeout SECONDS] [--delete-logs] [--force]
    orbit restart [--config CONFIG_PATH] [--host HOST] [--port PORT] [--delete-logs]
    orbit status [--watch] [--interval SECONDS]

Authentication Commands:
    orbit login [--username USERNAME] [--password PASSWORD] [--no-save]  # Will prompt if not provided, token stored securely in system keychain
    orbit logout [--all]                                                # Clears token from system keychain
    orbit register --username USERNAME [--password PASSWORD] [--role ROLE]
    orbit me
    orbit auth-status

User Management Commands:
    orbit user list [--role {user,admin}] [--active-only]
    orbit user reset-password --user-id ID [--password PASSWORD]
    orbit user reset-password --username USERNAME [--password PASSWORD]
    orbit user change-password [--current-password PASSWORD] [--new-password PASSWORD]  # Interactive password change
    orbit user deactivate --user-id ID [--force]
    orbit user activate --user-id ID [--force]
    orbit user delete --user-id ID [--force]

API Key Management Commands:
    orbit key create --collection COLLECTION --name NAME [--notes NOTES] [--prompt-id ID] [--prompt-name NAME] [--prompt-file FILE]
    orbit key list [--active-only] [--collection COLLECTION]
    orbit key status --key KEY
    orbit key test --key KEY
    orbit key deactivate --key KEY
    orbit key delete --key KEY [--force]

System Prompt Management Commands:
    orbit prompt create --name NAME --file FILE [--version VERSION]
    orbit prompt list [--name-filter FILTER]
    orbit prompt get --id ID [--save FILE]
    orbit prompt update --id ID --file FILE [--version VERSION]
    orbit prompt delete --id ID [--force]
    orbit prompt associate --key KEY --prompt-id PROMPT_ID

Configuration Management Commands:
    orbit config show [--key KEY]
    orbit config set KEY VALUE
    orbit config reset [--force]

Examples:
    # Authentication
    orbit login --username admin --password secret123  # Or just 'orbit login' to be prompted
    orbit me
    orbit register --username newuser --password pass123 --role user
    orbit logout
    orbit auth-status                                   # Check authentication status

    # User Management
    orbit user list                                     # List all users
    orbit user list --role admin                        # List only admin users
    orbit user list --active-only                       # List only active users
    orbit user reset-password --username admin --password newpass
    orbit user reset-password --user-id 507f1f77bcf86cd799439011 --password newpass
    orbit user change-password                          # Change your password (interactive)
    orbit user deactivate --user-id 507f1f77bcf86cd799439011  # Deactivate a user
    orbit user activate --user-id 507f1f77bcf86cd799439011   # Activate a user
    orbit user delete --user-id 507f1f77bcf86cd799439011  # Delete a user
    orbit user delete --user-id 507f1f77bcf86cd799439011 --force  # Skip confirmation
    # For debugging authentication issues: python server/tests/debug_auth.py

    # Server Management
    orbit start                                         # Start the server
    orbit start --reload                                # Start with auto-reload
    orbit start --host 0.0.0.0 --port 8080             # Start on specific host/port
    orbit stop                                          # Stop the server
    orbit stop --force                                  # Force stop without graceful shutdown
    orbit stop --delete-logs                            # Stop and delete logs
    orbit restart                                       # Restart the server
    orbit status                                        # Check server status
    orbit status --watch                                # Continuously monitor status
    orbit status --watch --interval 10                  # Monitor with custom interval

    # API Key Management
    orbit key create --collection docs --name "Customer Support"
    orbit key create --collection legal --name "Legal Team" --prompt-file legal.txt --prompt-name "Legal Assistant"
    orbit key list                                      # List all API keys
    orbit key list --active-only                        # List only active keys
    orbit key list --collection docs                    # List keys for specific collection
    orbit key test --key api_abcd1234                   # Test an API key
    orbit key status --key api_abcd1234                 # Get detailed status
    orbit key deactivate --key api_abcd1234             # Deactivate an API key
    orbit key delete --key api_abcd1234                 # Delete an API key
    orbit key delete --key api_abcd1234 --force         # Delete without confirmation

    # System Prompt Management
    orbit prompt create --name "Support" --file support.txt
    orbit prompt list                                   # List all prompts
    orbit prompt list --name-filter "Support"           # Filter prompts by name
    orbit prompt get --id 612a4b3c...                   # Get a specific prompt
    orbit prompt get --id 612a4b3c... --save prompt.txt # Get and save to file
    orbit prompt update --id 612a4b3c... --file updated.txt
    orbit prompt delete --id 612a4b3c...                # Delete a prompt
    orbit prompt delete --id 612a4b3c... --force        # Delete without confirmation
    orbit prompt associate --key api_123 --prompt-id 612a4b3c...

    # Configuration Management
    orbit config show                                   # Show all configuration
    orbit config show --key server.default_url          # Show specific setting
    orbit config set server.timeout 60                  # Set configuration value
    orbit config reset                                  # Reset to defaults
    orbit config reset --force                          # Reset without confirmation

    # Output Formatting
    orbit key list --output json                        # Output as JSON
    orbit status --output table                         # Output as table (default)
    orbit login --no-color                              # Disable colored output
    orbit start --verbose                               # Enable verbose logging
    orbit status --log-file /tmp/orbit.log              # Log to specific file

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
import getpass  # noqa
from pathlib import Path
from typing import Optional, Dict, Any, List
import dotenv
import logging
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, Confirm
from rich.logging import RichHandler

# Secure credential storage
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# Initialize rich console
console = Console()

# Version information
__version__ = "1.1.4"
__author__ = "Remsy Schmilinsky"

# Global configuration
DEFAULT_CONFIG_DIR = Path.home() / ".orbit"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_ENV_FILE = DEFAULT_CONFIG_DIR / ".env"  # Kept for backward compatibility
DEFAULT_LOG_DIR = DEFAULT_CONFIG_DIR / "logs"

# Keyring configuration
KEYRING_SERVICE = "orbit-cli"
KEYRING_TOKEN_KEY = "auth-token"
KEYRING_SERVER_KEY = "server-url"

# Logging configuration
def setup_logging(verbose: bool = False, log_file: Optional[Path] = None) -> logging.Logger:
    """Set up enterprise-grade logging with rich formatting."""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create logger
    logger = logging.getLogger("orbit")
    logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Console handler with rich formatting
    console_handler = RichHandler(
        console=console,
        show_time=False,
        show_path=False,
        markup=True
    )
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

# Exceptions for better error handling
class OrbitError(Exception):
    """Base exception for ORBIT CLI errors."""
    pass

class ServerError(OrbitError):
    """Server-related errors."""
    pass

class AuthenticationError(OrbitError):
    """Authentication-related errors."""
    pass

class ConfigurationError(OrbitError):
    """Configuration-related errors."""
    pass

class NetworkError(OrbitError):
    """Network-related errors."""
    pass

# Configuration Manager
class ConfigManager:
    """Manages CLI configuration with enterprise-grade features."""
    
    def __init__(self, config_dir: Path = DEFAULT_CONFIG_DIR):
        self.config_dir = config_dir
        self.config_file = config_dir / "config.json"
        self.ensure_config_dir()
    
    def ensure_config_dir(self) -> None:
        """Ensure configuration directory exists with proper permissions."""
        self.config_dir.mkdir(exist_ok=True, mode=0o700)
        DEFAULT_LOG_DIR.mkdir(exist_ok=True, mode=0o700)
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if not self.config_file.exists():
            return self.get_default_config()
        
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid configuration file: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}")
    
    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            self.config_file.chmod(0o600)
        except Exception as e:
            raise ConfigurationError(f"Failed to save configuration: {e}")
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "server": {
                "default_url": "http://localhost:3000",
                "timeout": 30,
                "retry_attempts": 3
            },
            "auth": {
                "use_keyring": KEYRING_AVAILABLE,
                "fallback_token_file": str(DEFAULT_ENV_FILE),
                "session_duration_hours": 12
            },
            "output": {
                "format": "table",  # table, json, yaml
                "color": True,
                "verbose": False
            },
            "history": {
                "enabled": True,
                "max_entries": 1000
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key."""
        config = self.load_config()
        keys = key.split('.')
        value = config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value by dot-notation key."""
        config = self.load_config()
        keys = key.split('.')
        target = config
        
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        target[keys[-1]] = value
        self.save_config(config)

# Enhanced output formatting
class OutputFormatter:
    """Handles output formatting for different formats and contexts."""
    
    def __init__(self, format: str = "table", color: bool = True):
        self.format = format
        self.color = color
    
    def success(self, message: str) -> None:
        """Display success message."""
        if self.color:
            console.print(f"[green]✓[/green] {message}")
        else:
            print(f"✓ {message}")
    
    def error(self, message: str) -> None:
        """Display error message."""
        if self.color:
            console.print(f"[red]✗[/red] {message}")
        else:
            print(f"✗ {message}")
    
    def warning(self, message: str) -> None:
        """Display warning message."""
        if self.color:
            console.print(f"[yellow]⚠[/yellow] {message}")
        else:
            print(f"⚠ {message}")
    
    def info(self, message: str) -> None:
        """Display info message."""
        if self.color:
            console.print(f"[blue]ℹ[/blue] {message}")
        else:
            print(f"ℹ {message}")
    
    def format_table(self, data: List[Dict[str, Any]], headers: List[str]) -> None:
        """Format data as a rich table."""
        table = Table(show_header=True, header_style="bold magenta")
        
        for header in headers:
            table.add_column(header)
        
        for row in data:
            table.add_row(*[str(row.get(h, "")) for h in headers])
        
        console.print(table)
    
    def format_json(self, data: Any) -> None:
        """Format data as JSON."""
        print(json.dumps(data, indent=2))
    
    def format_output(self, data: Any, headers: Optional[List[str]] = None) -> None:
        """Format output based on configured format."""
        if self.format == "json":
            self.format_json(data)
        elif self.format == "table" and isinstance(data, list) and headers:
            self.format_table(data, headers)
        else:
            # Default to JSON for complex data
            self.format_json(data)

# Enhanced Server Controller with better error handling
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
        self.formatter = OutputFormatter()
    
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
        except (ValueError, IOError) as e:
            logger.debug(f"Failed to read PID file: {e}")
            return None
    
    def _write_pid(self, pid: int) -> None:
        """
        Write the PID to the PID file.
        
        Args:
            pid: The process ID to write
        """
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(pid))
            logger.debug(f"Wrote PID {pid} to {self.pid_file}")
        except IOError as e:
            raise ServerError(f"Failed to write PID file: {e}")
    
    def _remove_pid_file(self) -> None:
        """Remove the PID file if it exists."""
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
                logger.debug(f"Removed PID file {self.pid_file}")
            except IOError as e:
                logger.warning(f"Failed to remove PID file: {e}")
    
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
        except psutil.AccessDenied:
            logger.warning(f"Access denied when checking process {pid}")
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
            self.formatter.warning(f"Server is already running with PID {pid}")
            return False
        
        # Clean up stale PID file
        self._remove_pid_file()
        
        # Delete logs if requested
        if delete_logs and self.log_file.parent.exists():
            import shutil
            try:
                shutil.rmtree(self.log_file.parent)
                self.formatter.info("Logs folder deleted")
            except Exception as e:
                logger.warning(f"Failed to delete logs: {e}")
        
        # Build the command to start the server
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
                    logger.debug(f"Using config file: {config}")
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
        
        logger.debug(f"Starting server with command: {' '.join(cmd)}")
        
        # Start the server process with progress indicator
        try:
            # Ensure logs directory exists
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self.log_file.parent.chmod(0o700)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                task = progress.add_task("Starting server...", total=None)
                
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
                        progress.update(task, completed=True)
                        self.formatter.success(f"Server started successfully with PID {process.pid}")
                        self.formatter.info(f"Logs are being written to {self.log_file}")
                        return True
                    else:
                        progress.update(task, completed=True)
                        self.formatter.error("Server failed to start. Check the logs for details.")
                        self._remove_pid_file()
                        return False
                        
        except Exception as e:
            self.formatter.error(f"Error starting server: {e}")
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
            self.formatter.warning("No PID file found. Server may not be running.")
            return False
        
        if not self._is_process_running(pid):
            self.formatter.info(f"Server with PID {pid} is not running. Cleaning up PID file.")
            self._remove_pid_file()
            return True
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task(f"Stopping server with PID {pid}...", total=None)
            
            try:
                # Send SIGTERM for graceful shutdown
                os.kill(pid, signal.SIGTERM)
                
                # Wait for the process to terminate
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if not self._is_process_running(pid):
                        progress.update(task, completed=True)
                        self.formatter.success("Server stopped successfully")
                        self._remove_pid_file()
                        
                        # Delete logs if requested
                        if delete_logs and self.log_file.parent.exists():
                            import shutil
                            shutil.rmtree(self.log_file.parent)
                            self.formatter.info("Logs folder deleted")
                        
                        return True
                    time.sleep(0.5)
                
                # If still running, force kill
                self.formatter.warning(f"Server did not stop gracefully. Force killing PID {pid}...")
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
                
                if not self._is_process_running(pid):
                    progress.update(task, completed=True)
                    self.formatter.success("Server force stopped")
                    self._remove_pid_file()
                    return True
                else:
                    progress.update(task, completed=True)
                    self.formatter.error("Failed to stop server")
                    return False
                    
            except ProcessLookupError:
                progress.update(task, completed=True)
                self.formatter.info("Server process not found. Cleaning up PID file.")
                self._remove_pid_file()
                return True
            except Exception as e:
                progress.update(task, completed=True)
                self.formatter.error(f"Error stopping server: {e}")
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
        self.formatter.info("Restarting server...")
        
        # Stop the server if it's running
        if self._read_pid():
            if not self.stop(delete_logs=delete_logs):
                self.formatter.error("Failed to stop server for restart")
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
            uptime_seconds = time.time() - process.create_time()
            uptime_str = self._format_uptime(uptime_seconds)
            
            return {
                "status": "running",
                "pid": pid,
                "uptime": uptime_str,
                "uptime_seconds": uptime_seconds,
                "memory_mb": round(process.memory_info().rss / 1024 / 1024, 2),
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
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        
        return " ".join(parts) if parts else "< 1m"


# Enhanced API Manager with better error handling and retry logic
class ApiManager:
    """Manager class for API keys and system prompts via the server API endpoints"""
    
    def __init__(self, server_url: str = None, config_manager: ConfigManager = None):
        """
        Initialize the API Manager
        
        Args:
            server_url: The URL of the server, e.g., 'http://localhost:3000'
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager or ConfigManager()
        self.formatter = OutputFormatter()
        
        # Load environment variables from .env file if it exists
        dotenv.load_dotenv()
        
        # Try to load token and server URL from persistent storage first
        self._load_token_secure()
        
        # Get server URL from args, persistent storage, or environment
        default_url = self.config_manager.get('server.default_url', 'http://localhost:3000')
        self.server_url = server_url or os.environ.get('API_SERVER_URL', default_url)
        self.server_url = self.server_url.rstrip('/')
        
        # Set admin auth token if available in environment (fallback)
        if not hasattr(self, 'admin_token') or not self.admin_token:
            self.admin_token = os.environ.get('API_ADMIN_TOKEN')
        
        # Retry configuration
        self.retry_attempts = self.config_manager.get('server.retry_attempts', 3)
        self.timeout = self.config_manager.get('server.timeout', 30)
    
    def _make_request(self, method: str, url: str, headers: Dict[str, str] = None, 
                     json_data: Dict[str, Any] = None, retry: bool = True) -> requests.Response:
        """
        Make an HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            headers: Request headers
            json_data: JSON data for POST/PUT requests
            retry: Whether to retry on failure
            
        Returns:
            Response object
            
        Raises:
            NetworkError: On network failures
        """
        headers = headers or {}
        attempts = self.retry_attempts if retry else 1
        
        for attempt in range(attempts):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    json=json_data,
                    timeout=self.timeout
                )
                return response
            except requests.exceptions.ConnectionError as e:
                if attempt < attempts - 1:
                    logger.debug(f"Connection error (attempt {attempt + 1}/{attempts}): {e}")
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise NetworkError(f"Failed to connect to server at {self.server_url}")
            except requests.exceptions.Timeout:
                if attempt < attempts - 1:
                    logger.debug(f"Request timeout (attempt {attempt + 1}/{attempts})")
                    time.sleep(2 ** attempt)
                else:
                    raise NetworkError(f"Request timed out after {self.timeout} seconds")
            except Exception as e:
                raise NetworkError(f"Unexpected error: {e}")
    
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
        except FileNotFoundError:
            raise OrbitError(f"File not found: {file_path}")
        except Exception as e:
            raise OrbitError(f"Error reading file {file_path}: {str(e)}")
    
    def _save_token_secure(self, token: str) -> None:
        """Save token securely using system keychain/credential manager"""
        if KEYRING_AVAILABLE:
            try:
                # Store token in system keychain
                keyring.set_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY, token)
                # Also store server URL for consistency
                keyring.set_password(KEYRING_SERVICE, KEYRING_SERVER_KEY, self.server_url)
                logger.debug("Saved authentication token to system keychain")
                
                # Clean up old plain text file if it exists
                if DEFAULT_ENV_FILE.exists():
                    try:
                        DEFAULT_ENV_FILE.unlink()
                        logger.debug("Removed legacy plain text token file")
                    except Exception as e:
                        logger.warning(f"Failed to remove legacy token file: {e}")
                
                return
            except Exception as e:
                logger.warning(f"Failed to save token to keychain: {e}")
                logger.info("Falling back to encrypted file storage")
        
        # Fallback to file-based storage (with improved security)
        self._save_token_to_file_fallback(token)
    
    def _save_token_to_file_fallback(self, token: str) -> None:
        """Fallback: Save token to file with improved security measures"""
        DEFAULT_ENV_FILE.parent.mkdir(exist_ok=True, mode=0o700)
        
        # Basic obfuscation - not encryption but better than plain text
        import base64
        obfuscated_token = base64.b64encode(token.encode()).decode()
        obfuscated_url = base64.b64encode(self.server_url.encode()).decode()
        
        with open(DEFAULT_ENV_FILE, 'w') as f:
            f.write(f'# ORBIT CLI Configuration - Token is base64 encoded\n')
            f.write(f'# For security, consider installing the keyring library: pip install keyring\n')
            f.write(f'API_ADMIN_TOKEN_B64={obfuscated_token}\n')
            f.write(f'API_SERVER_URL_B64={obfuscated_url}\n')
        
        # Set secure permissions on the file
        DEFAULT_ENV_FILE.chmod(0o600)
        logger.debug("Saved authentication token to secure file storage")
        if not KEYRING_AVAILABLE:
            logger.warning("For enhanced security, install keyring: pip install keyring")
    
    def _load_token_secure(self) -> Optional[str]:
        """Load token securely from system keychain or fallback storage"""
        if KEYRING_AVAILABLE:
            try:
                # Try to load from system keychain first
                token = keyring.get_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
                if token:
                    self.admin_token = token
                    # Also load server URL if available
                    stored_url = keyring.get_password(KEYRING_SERVICE, KEYRING_SERVER_KEY)
                    if stored_url and not hasattr(self, 'server_url'):
                        self.server_url = stored_url
                    logger.debug("Loaded authentication token from system keychain")
                    return self.admin_token
            except Exception as e:
                logger.debug(f"Failed to load token from keychain: {e}")
        
        # Fallback to file-based storage
        return self._load_token_from_file_fallback()
    
    def _load_token_from_file_fallback(self) -> Optional[str]:
        """Fallback: Load token from file storage"""
        if DEFAULT_ENV_FILE.exists():
            try:
                # Try new format first (base64 encoded)
                dotenv.load_dotenv(DEFAULT_ENV_FILE, override=True)
                
                # Check for base64 encoded token (new format)
                encoded_token = os.environ.get('API_ADMIN_TOKEN_B64')
                encoded_url = os.environ.get('API_SERVER_URL_B64')
                
                if encoded_token:
                    import base64
                    try:
                        self.admin_token = base64.b64decode(encoded_token.encode()).decode()
                        if encoded_url and not hasattr(self, 'server_url'):
                            self.server_url = base64.b64decode(encoded_url.encode()).decode()
                        logger.debug("Loaded authentication token from secure file storage")
                        return self.admin_token
                    except Exception as e:
                        logger.warning(f"Failed to decode token: {e}")
                
                # Fallback to old plain text format for backward compatibility
                plain_token = os.environ.get('API_ADMIN_TOKEN')
                if plain_token:
                    self.admin_token = plain_token
                    plain_url = os.environ.get('API_SERVER_URL')
                    if plain_url and not hasattr(self, 'server_url'):
                        self.server_url = plain_url
                    logger.warning("Loaded legacy plain text token - consider running 'orbit login' again for enhanced security")
                    return self.admin_token
                    
            except Exception as e:
                logger.error(f"Failed to load token from file: {e}")
                
        return None
    
    def _clear_token_secure(self) -> None:
        """Clear token from secure storage"""
        if KEYRING_AVAILABLE:
            try:
                # Clear from system keychain
                keyring.delete_password(KEYRING_SERVICE, KEYRING_TOKEN_KEY)
                keyring.delete_password(KEYRING_SERVICE, KEYRING_SERVER_KEY)
                logger.debug("Cleared authentication token from system keychain")
            except keyring.errors.PasswordDeleteError:
                logger.debug("No token found in keychain to clear")
            except Exception as e:
                logger.warning(f"Failed to clear token from keychain: {e}")
        
        # Also clear file-based storage
        if DEFAULT_ENV_FILE.exists():
            try:
                DEFAULT_ENV_FILE.unlink()
                logger.debug("Cleared authentication token from file storage")
            except Exception as e:
                logger.warning(f"Failed to clear token file: {e}")
    
    def _ensure_authenticated(self) -> None:
        """Ensure user is authenticated before proceeding"""
        if not self.admin_token:
            raise AuthenticationError("Authentication required. Please run 'orbit login' first.")
    
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
            response = self._make_request("POST", url, headers=headers, json_data=data)
            response.raise_for_status()
            result = response.json()
            
            # Update the admin token if login successful
            if "token" in result:
                self.admin_token = result["token"]
                # Save to environment variable for future use (session)
                os.environ["API_ADMIN_TOKEN"] = self.admin_token
                # Save to persistent secure storage
                self._save_token_secure(self.admin_token)
            
            return result
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid username or password")
            elif e.response.status_code == 403:
                raise AuthenticationError("Access denied")
            else:
                raise AuthenticationError(f"Login failed: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise AuthenticationError(f"Login failed: {str(e)}")
    
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
            response = self._make_request("POST", url, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            # Clear the admin token
            self.admin_token = None
            if "API_ADMIN_TOKEN" in os.environ:
                del os.environ["API_ADMIN_TOKEN"]
            # Clear the persistent secure storage
            self._clear_token_secure()
            
            return result
        except Exception as e:
            # Clear token anyway even if server logout fails
            self.admin_token = None
            if "API_ADMIN_TOKEN" in os.environ:
                del os.environ["API_ADMIN_TOKEN"]
            # Clear the persistent secure storage
            self._clear_token_secure()
            
            logger.debug(f"Logout error (token cleared anyway): {e}")
            return {"message": "Logged out locally"}
    
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
            response = self._make_request("POST", url, headers=headers, json_data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                raise AuthenticationError("Admin privileges required to register users")
            elif e.response.status_code == 409:
                raise OrbitError("User already exists")
            else:
                raise OrbitError(f"Registration failed: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Registration failed: {str(e)}")
    
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
            response = self._make_request("GET", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid or expired token")
            else:
                raise OrbitError(f"Failed to get current user: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Failed to get current user: {str(e)}")
    
    def check_auth_status(self) -> Dict[str, Any]:
        """
        Check authentication status
        
        Returns:
            Dictionary containing authentication status
        """
        if not self.admin_token:
            return {
                "authenticated": False,
                "message": "Not authenticated"
            }
        
        try:
            # Try to get current user info to verify token
            user_info = self.get_current_user()
            return {
                "authenticated": True,
                "user": user_info,
                "message": "Authenticated"
            }
        except AuthenticationError:
            return {
                "authenticated": False,
                "message": "Token invalid or expired"
            }
        except Exception as e:
            return {
                "authenticated": False,
                "error": str(e),
                "message": "Authentication status unknown"
            }
    
    # User Management utilities
    def list_users(self, role: Optional[str] = None, active_only: bool = False, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all users in the system with optional server-side filtering
        
        Args:
            role: Optional role filter (user, admin)
            active_only: If True, only return active users
            limit: Maximum number of users to return (default: 100, max: 1000)
            offset: Number of users to skip for pagination (default: 0)
            
        Returns:
            List of dictionaries containing user information
        """
        self._ensure_authenticated()
        
        # Build query parameters
        params = {}
        if role:
            params['role'] = role
        if active_only:
            params['active_only'] = 'true'
        if limit != 100:
            params['limit'] = str(limit)
        if offset != 0:
            params['offset'] = str(offset)
        
        url = f"{self.server_url}/auth/users"
        if params:
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            url = f"{url}?{query_string}"
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = self._make_request("GET", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise OrbitError("User management endpoint not found. Check if the server is running and authentication is enabled.")
            elif e.response.status_code == 403:
                raise AuthenticationError("Admin privileges required to list users.")
            else:
                raise OrbitError(f"Failed to list users: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Failed to list users: {str(e)}")
    
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
            response = self._make_request("POST", url, headers=headers, json_data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                raise AuthenticationError("Admin privileges required to reset user passwords.")
            elif e.response.status_code == 404:
                raise OrbitError("User not found.")
            elif e.response.status_code == 400:
                raise OrbitError("Use change-password to change your own password.")
            else:
                raise OrbitError(f"Failed to reset password: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Failed to reset password: {str(e)}")
    
    def find_user_id_by_username(self, username: str) -> str:
        """
        Find a user's ID by their username
        
        Args:
            username: The username to search for
            
        Returns:
            The user ID if found
            
        Raises:
            OrbitError: If user is not found
        """
        self._ensure_authenticated()
        
        # Get all users and find the one with matching username
        users = self.list_users()
        for user in users:
            if user.get('username') == username:
                user_id = user.get('_id') or user.get('id')
                if user_id:
                    return user_id
        
        raise OrbitError(f"User with username '{username}' not found")
    
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
            response = self._make_request("DELETE", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise OrbitError("User not found.")
            elif e.response.status_code == 403:
                raise AuthenticationError("Admin privileges required to delete users.")
            elif e.response.status_code == 400:
                raise OrbitError("Cannot delete your own account.")
            else:
                raise OrbitError(f"Failed to delete user: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Failed to delete user: {str(e)}")
    
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
            response = self._make_request("POST", url, headers=headers, json_data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                raise OrbitError("Current password is incorrect.")
            else:
                raise OrbitError(f"Failed to change password: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Failed to change password: {str(e)}")
    
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
                    raise OrbitError("Failed to get prompt ID from created prompt")
        
        # Now create the API key
        url = f"{self.server_url}/admin/api-keys"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        data = {
            "collection_name": collection_name,
            "client_name": client_name
        }
        
        if notes:
            data["notes"] = notes
        
        try:
            # First create the API key
            response = self._make_request("POST", url, headers=headers, json_data=data)
            response.raise_for_status()
            api_key_result = response.json()
            
            # If we have a prompt ID, associate it with the API key
            if prompt_id:
                api_key = api_key_result.get("api_key")
                if not api_key:
                    raise OrbitError("Failed to get API key from creation response")
                
                association_result = self.associate_prompt_with_api_key(api_key, prompt_id)
                api_key_result["system_prompt_id"] = prompt_id
            
            return api_key_result
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error creating API key: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error creating API key: {str(e)}")
    
    def list_api_keys(self, collection: Optional[str] = None, active_only: bool = False, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all API keys with optional server-side filtering
        
        Args:
            collection: Optional collection name filter
            active_only: If True, only return active keys
            limit: Maximum number of keys to return (default: 100, max: 1000)
            offset: Number of keys to skip for pagination (default: 0)
            
        Returns:
            List of dictionaries containing API key details
        """
        self._ensure_authenticated()
        
        # Build query parameters
        params = {}
        if collection:
            params['collection'] = collection
        if active_only:
            params['active_only'] = 'true'
        if limit != 100:
            params['limit'] = str(limit)
        if offset != 0:
            params['offset'] = str(offset)
        
        url = f"{self.server_url}/admin/api-keys"
        if params:
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            url = f"{url}?{query_string}"
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = self._make_request("GET", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error listing API keys: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error listing API keys: {str(e)}")
    
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
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        data = {
            "api_key": api_key
        }
        
        try:
            response = self._make_request("POST", url, headers=headers, json_data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error deactivating API key: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error deactivating API key: {str(e)}")
    
    def deactivate_user(self, user_id: str) -> Dict[str, Any]:
        """
        Deactivate a user
        
        Args:
            user_id: The user ID to deactivate
            
        Returns:
            Dictionary containing the result of the operation
        """
        self._ensure_authenticated()
        url = f"{self.server_url}/auth/users/{user_id}/deactivate"
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = self._make_request("POST", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise OrbitError("User not found.")
            elif e.response.status_code == 403:
                raise AuthenticationError("Admin privileges required to deactivate users.")
            elif e.response.status_code == 400:
                raise OrbitError("Cannot deactivate your own account.")
            else:
                raise OrbitError(f"Failed to deactivate user: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Failed to deactivate user: {str(e)}")
    
    def activate_user(self, user_id: str) -> Dict[str, Any]:
        """
        Activate a user
        
        Args:
            user_id: The user ID to activate
            
        Returns:
            Dictionary containing the result of the operation
        """
        self._ensure_authenticated()
        url = f"{self.server_url}/auth/users/{user_id}/activate"
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = self._make_request("POST", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise OrbitError("User not found.")
            elif e.response.status_code == 403:
                raise AuthenticationError("Admin privileges required to activate users.")
            else:
                raise OrbitError(f"Failed to activate user: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Failed to activate user: {str(e)}")
    
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
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = self._make_request("DELETE", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error deleting API key: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error deleting API key: {str(e)}")
    
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
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = self._make_request("GET", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error checking API key status: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error checking API key status: {str(e)}")
    
    def test_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Test an API key by making a simple health check request
        
        Args:
            api_key: The API key to test
            
        Returns:
            Dictionary containing the health check response or error details
        """
        # First check if the API key looks valid (basic format check)
        if not api_key or len(api_key) < 10:
            return {
                "status": "error",
                "error": "API key format is invalid"
            }
        
        url = f"{self.server_url}/health"
        
        headers = {
            "X-API-Key": api_key
        }
        
        try:
            response = self._make_request("GET", url, headers=headers, retry=False)
            
            # Check for 401 Unauthorized which would indicate an invalid or deactivated key
            if response.status_code == 401:
                return {
                    "status": "error",
                    "error": "API key is invalid or deactivated",
                    "details": response.json() if response.headers.get('content-type') == 'application/json' else response.text
                }
            elif response.status_code == 403:
                return {
                    "status": "error",
                    "error": "API key is valid but access forbidden",
                    "details": response.json() if response.headers.get('content-type') == 'application/json' else response.text
                }
            
            response.raise_for_status()
            
            # If health endpoint doesn't validate API keys, try a different endpoint
            if response.status_code == 200:
                # Try to get API key status to verify it's valid
                try:
                    status_response = self.get_api_key_status(api_key)
                    return {
                        "status": "success",
                        "message": "API key is valid and active",
                        "server_response": response.json() if response.headers.get('content-type') == 'application/json' else response.text
                    }
                except:
                    # If we can't get status, assume key is invalid
                    return {
                        "status": "error", 
                        "error": "API key is invalid or deactivated"
                    }
            
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return {
                    "status": "error",
                    "error": "API key is invalid or deactivated",
                    "details": e.response.json() if e.response.headers.get('content-type') == 'application/json' else e.response.text
                }
            elif e.response.status_code == 403:
                return {
                    "status": "error",
                    "error": "API key is valid but access forbidden",
                    "details": e.response.json() if e.response.headers.get('content-type') == 'application/json' else e.response.text
                }
            raise OrbitError(f"API key test failed: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"API key test failed: {str(e)}")
    
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
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        data = {
            "name": name,
            "prompt": prompt_text,
            "version": version
        }
        
        try:
            response = self._make_request("POST", url, headers=headers, json_data=data)
            response.raise_for_status()
            result = response.json()
            return result
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error creating prompt: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error creating prompt: {str(e)}")
    
    def list_prompts(self, name_filter: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all system prompts with optional server-side filtering
        
        Args:
            name_filter: Optional name filter (case-insensitive partial match)
            limit: Maximum number of prompts to return (default: 100, max: 1000)
            offset: Number of prompts to skip for pagination (default: 0)
            
        Returns:
            List of dictionaries containing prompt details
        """
        self._ensure_authenticated()
        
        # Build query parameters
        params = {}
        if name_filter:
            params['name_filter'] = name_filter
        if limit != 100:
            params['limit'] = str(limit)
        if offset != 0:
            params['offset'] = str(offset)
        
        url = f"{self.server_url}/admin/prompts"
        if params:
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            url = f"{url}?{query_string}"
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = self._make_request("GET", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error listing prompts: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error listing prompts: {str(e)}")
    
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
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = self._make_request("GET", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error getting prompt: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error getting prompt: {str(e)}")
    
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
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        data = {
            "prompt": prompt_text
        }
        
        if version:
            data["version"] = version
        
        try:
            response = self._make_request("PUT", url, headers=headers, json_data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error updating prompt: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error updating prompt: {str(e)}")
    
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
        
        headers = {
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        try:
            response = self._make_request("DELETE", url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error deleting prompt: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error deleting prompt: {str(e)}")
    
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
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.admin_token}"
        }
        
        data = {
            "prompt_id": prompt_id
        }
        
        try:
            response = self._make_request("POST", url, headers=headers, json_data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise OrbitError(f"Error associating prompt with API key: {e.response.status_code} {e.response.text}")
        except NetworkError:
            raise
        except Exception as e:
            raise OrbitError(f"Error associating prompt with API key: {str(e)}")


# Main CLI class that ties everything together
class OrbitCLI:
    """Main CLI class for ORBIT command-line interface."""
    
    def __init__(self):
        """Initialize the ORBIT CLI."""
        self.config_manager = ConfigManager()
        self.server_controller = ServerController()
        self.api_manager = None  # Will be initialized when needed
        self.formatter = OutputFormatter()
        
    def get_api_manager(self, server_url: Optional[str] = None) -> ApiManager:
        """Get or create the API manager instance."""
        if self.api_manager is None:
            self.api_manager = ApiManager(server_url, self.config_manager)
        return self.api_manager
    
    def create_parser(self) -> argparse.ArgumentParser:
        """Create the argument parser for the CLI."""
        parser = argparse.ArgumentParser(
            prog='orbit',
            description='ORBIT Control CLI - Enterprise-grade Open Inference Server management',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
For more information about a specific command, use:
  orbit <command> --help

Configuration files are stored in ~/.orbit/
Authentication tokens are stored securely in ~/.orbit/.env

Report issues at: https://github.com/schmitech/orbit/issues
"""
        )
        
        # Global arguments
        parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
        parser.add_argument('--server-url', help='Server URL (default: from config or localhost:3000)')
        parser.add_argument('--config', help='Path to configuration file')
        parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
        parser.add_argument('--output', choices=['table', 'json'], help='Output format')
        parser.add_argument('--no-color', action='store_true', help='Disable colored output')
        parser.add_argument('--log-file', help='Path to log file')
        
        # Create subparsers for different command groups
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
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
        
        # Configuration commands
        self._add_config_commands(subparsers)
        
        return parser
    
    def _add_server_commands(self, subparsers):
        """Add server control commands to the subparsers."""
        # Start command
        start_parser = subparsers.add_parser(
            'start', 
            help='Start the ORBIT server',
            description='Start the ORBIT server with optional configuration'
        )
        start_parser.add_argument('--config', type=str, help='Path to server configuration file')
        start_parser.add_argument('--host', type=str, help='Host to bind to (e.g., 0.0.0.0)')
        start_parser.add_argument('--port', type=int, help='Port to bind to (e.g., 3000)')
        start_parser.add_argument('--reload', action='store_true', help='Enable auto-reload for development')
        start_parser.add_argument('--delete-logs', action='store_true', help='Delete logs folder before starting')
        
        # Stop command
        stop_parser = subparsers.add_parser(
            'stop', 
            help='Stop the ORBIT server',
            description='Stop the running ORBIT server gracefully'
        )
        stop_parser.add_argument('--timeout', type=int, default=30, help='Timeout for graceful shutdown (seconds)')
        stop_parser.add_argument('--delete-logs', action='store_true', help='Delete logs folder after stopping')
        stop_parser.add_argument('--force', action='store_true', help='Force stop without graceful shutdown')
        
        # Restart command
        restart_parser = subparsers.add_parser(
            'restart', 
            help='Restart the ORBIT server',
            description='Restart the ORBIT server with optional new configuration'
        )
        restart_parser.add_argument('--config', type=str, help='Path to server configuration file')
        restart_parser.add_argument('--host', type=str, help='Host to bind to')
        restart_parser.add_argument('--port', type=int, help='Port to bind to')
        restart_parser.add_argument('--delete-logs', action='store_true', help='Delete logs folder during restart')
        
        # Status command
        status_parser = subparsers.add_parser(
            'status', 
            help='Check ORBIT server status',
            description='Display current status of the ORBIT server'
        )
        status_parser.add_argument('--watch', action='store_true', help='Continuously monitor status')
        status_parser.add_argument('--interval', type=int, default=5, help='Watch interval in seconds')
    
    def _add_auth_commands(self, subparsers):
        """Add authentication commands to the subparsers."""
        # Login command
        login_parser = subparsers.add_parser(
            'login', 
            help='Login to the ORBIT server',
            description='Authenticate with the ORBIT server and save credentials'
        )
        login_parser.add_argument('--username', '-u', help='Username (will prompt if not provided)')
        login_parser.add_argument('--password', '-p', help='Password (will prompt if not provided)')
        login_parser.add_argument('--no-save', action='store_true', help='Do not save credentials')
        
        # Logout command
        logout_parser = subparsers.add_parser(
            'logout', 
            help='Logout from the ORBIT server',
            description='Logout and clear saved credentials'
        )
        logout_parser.add_argument('--all', action='store_true', help='Logout from all sessions')
        
        # Register command
        register_parser = subparsers.add_parser(
            'register', 
            help='Register a new user (admin only)',
            description='Register a new user account (requires admin privileges)'
        )
        register_parser.add_argument('--username', '-u', required=True, help='Username for the new user')
        register_parser.add_argument('--password', '-p', help='Password (will prompt if not provided)')
        register_parser.add_argument('--role', '-r', default='user', choices=['user', 'admin'], help='User role')
        register_parser.add_argument('--email', help='Email address for the user')
        
        # Me command
        me_parser = subparsers.add_parser(
            'me', 
            help='Show current user information',
            description='Display information about the currently authenticated user'
        )
        
        # Auth status command
        auth_status_parser = subparsers.add_parser(
            'auth-status', 
            help='Check authentication status',
            description='Check if you are authenticated and token validity'
        )
        

    
    def _add_key_commands(self, subparsers):
        """Add API key management commands to the subparsers."""
        key_parser = subparsers.add_parser(
            'key', 
            help='Manage API keys',
            description='Create, list, and manage API keys'
        )
        key_subparsers = key_parser.add_subparsers(dest='key_command', help='API key operations')
        
        # Create key command
        create_parser = key_subparsers.add_parser(
            'create', 
            help='Create a new API key',
            description='Create a new API key with optional system prompt'
        )
        create_parser.add_argument('--collection', required=True, help='Collection name to associate with the key')
        create_parser.add_argument('--name', required=True, help='Client name for identification')
        create_parser.add_argument('--notes', help='Optional notes about this API key')
        create_parser.add_argument('--prompt-id', help='Existing system prompt ID to associate')
        create_parser.add_argument('--prompt-name', help='Name for a new system prompt')
        create_parser.add_argument('--prompt-file', help='Path to file containing system prompt')
        
        # List keys command
        list_parser = key_subparsers.add_parser(
            'list', 
            help='List all API keys',
            description='Display all API keys with their details and optional filtering'
        )
        list_parser.add_argument('--active-only', action='store_true', help='Show only active keys')
        list_parser.add_argument('--collection', help='Filter by collection name')
        list_parser.add_argument('--limit', type=int, default=100, help='Maximum number of keys to return (default: 100, max: 1000)')
        list_parser.add_argument('--offset', type=int, default=0, help='Number of keys to skip for pagination (default: 0)')
        list_parser.add_argument('--output', choices=['table', 'json'], help='Output format')
        list_parser.add_argument('--no-color', action='store_true', help='Disable colored output')
        
        # Test key command
        test_parser = key_subparsers.add_parser(
            'test', 
            help='Test an API key',
            description='Test if an API key is valid and active'
        )
        test_parser.add_argument('--key', required=True, help='API key to test')
        
        # Status command
        status_parser = key_subparsers.add_parser(
            'status', 
            help='Get API key status',
            description='Get detailed status of an API key'
        )
        status_parser.add_argument('--key', required=True, help='API key to check')
        
        # Deactivate command
        deactivate_parser = key_subparsers.add_parser(
            'deactivate', 
            help='Deactivate an API key',
            description='Temporarily deactivate an API key'
        )
        deactivate_parser.add_argument('--key', required=True, help='API key to deactivate')
        
        # Delete command
        delete_parser = key_subparsers.add_parser(
            'delete', 
            help='Delete an API key',
            description='Permanently delete an API key'
        )
        delete_parser.add_argument('--key', required=True, help='API key to delete')
        delete_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    
    def _add_prompt_commands(self, subparsers):
        """Add system prompt management commands to the subparsers."""
        prompt_parser = subparsers.add_parser(
            'prompt', 
            help='Manage system prompts',
            description='Create, list, and manage system prompts'
        )
        prompt_subparsers = prompt_parser.add_subparsers(dest='prompt_command', help='System prompt operations')
        
        # Create prompt command
        create_parser = prompt_subparsers.add_parser(
            'create', 
            help='Create a new system prompt',
            description='Create a new system prompt from a file'
        )
        create_parser.add_argument('--name', required=True, help='Unique name for the prompt')
        create_parser.add_argument('--file', required=True, help='Path to file containing prompt text')
        create_parser.add_argument('--version', default='1.0', help='Version string (default: 1.0)')
        
        # List prompts command
        list_parser = prompt_subparsers.add_parser(
            'list', 
            help='List all system prompts',
            description='Display all system prompts'
        )
        list_parser.add_argument('--name-filter', help='Filter by prompt name')
        list_parser.add_argument('--limit', type=int, default=100, help='Maximum number of prompts to return (default: 100, max: 1000)')
        list_parser.add_argument('--offset', type=int, default=0, help='Number of prompts to skip for pagination (default: 0)')
        list_parser.add_argument('--output', choices=['table', 'json'], help='Output format')
        list_parser.add_argument('--no-color', action='store_true', help='Disable colored output')
        
        # Get prompt command
        get_parser = prompt_subparsers.add_parser(
            'get', 
            help='Get a system prompt',
            description='Display a specific system prompt'
        )
        get_parser.add_argument('--id', required=True, help='Prompt ID')
        get_parser.add_argument('--save', help='Save prompt to file')
        
        # Update prompt command
        update_parser = prompt_subparsers.add_parser(
            'update', 
            help='Update a system prompt',
            description='Update an existing system prompt'
        )
        update_parser.add_argument('--id', required=True, help='Prompt ID to update')
        update_parser.add_argument('--file', required=True, help='Path to file with updated prompt text')
        update_parser.add_argument('--version', help='New version string')
        
        # Delete prompt command
        delete_parser = prompt_subparsers.add_parser(
            'delete', 
            help='Delete a system prompt',
            description='Delete a system prompt'
        )
        delete_parser.add_argument('--id', required=True, help='Prompt ID to delete')
        delete_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
        
        # Associate prompt with API key command
        associate_parser = prompt_subparsers.add_parser(
            'associate', 
            help='Associate prompt with API key',
            description='Link a system prompt to an API key'
        )
        associate_parser.add_argument('--key', required=True, help='API key')
        associate_parser.add_argument('--prompt-id', required=True, help='Prompt ID to associate')
    
    def _add_user_commands(self, subparsers):
        """Add user management commands to the subparsers."""
        user_parser = subparsers.add_parser(
            'user', 
            help='Manage users (admin only)',
            description='User management operations (requires admin privileges)'
        )
        user_subparsers = user_parser.add_subparsers(dest='user_command', help='User management operations')
        
        # List users command
        list_parser = user_subparsers.add_parser(
            'list', 
            help='List all users',
            description='Display all user accounts with optional filtering and pagination'
        )
        list_parser.add_argument('--role', choices=['user', 'admin'], help='Filter by role')
        list_parser.add_argument('--active-only', action='store_true', help='Show only active users')
        list_parser.add_argument('--limit', type=int, default=100, help='Maximum number of users to return (default: 100, max: 1000)')
        list_parser.add_argument('--offset', type=int, default=0, help='Number of users to skip for pagination (default: 0)')
        list_parser.add_argument('--output', choices=['table', 'json'], help='Output format')
        list_parser.add_argument('--no-color', action='store_true', help='Disable colored output')
        
        # Reset password command
        reset_parser = user_subparsers.add_parser(
            'reset-password', 
            help='Reset user password',
            description='Reset a user\'s password (admin only)'
        )
        reset_group = reset_parser.add_mutually_exclusive_group(required=True)
        reset_group.add_argument('--user-id', help='User ID')
        reset_group.add_argument('--username', help='Username')
        reset_parser.add_argument('--password', help='New password (will generate if not provided)')
        
        # Delete user command
        delete_parser = user_subparsers.add_parser(
            'delete', 
            help='Delete a user',
            description='Delete a user account'
        )
        delete_parser.add_argument('--user-id', required=True, help='User ID to delete')
        delete_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
        
        # Deactivate user command
        deactivate_parser = user_subparsers.add_parser(
            'deactivate', 
            help='Deactivate a user',
            description='Deactivate a user account (prevents login)'
        )
        deactivate_parser.add_argument('--user-id', required=True, help='User ID to deactivate')
        deactivate_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
        
        # Activate user command
        activate_parser = user_subparsers.add_parser(
            'activate', 
            help='Activate a user',
            description='Activate a previously deactivated user account'
        )
        activate_parser.add_argument('--user-id', required=True, help='User ID to activate')
        activate_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
        
        # Change password command
        change_password_parser = user_subparsers.add_parser(
            'change-password', 
            help='Change your password',
            description='Change your account password'
        )
        change_password_parser.add_argument('--current-password', help='Current password (will prompt if not provided)')
        change_password_parser.add_argument('--new-password', help='New password (will prompt if not provided)')
        

    
    def _add_config_commands(self, subparsers):
        """Add configuration commands to the subparsers."""
        config_parser = subparsers.add_parser(
            'config', 
            help='Manage CLI configuration',
            description='View and modify CLI configuration'
        )
        config_subparsers = config_parser.add_subparsers(dest='config_command', help='Configuration operations')
        
        # Show config command
        show_parser = config_subparsers.add_parser(
            'show', 
            help='Show configuration',
            description='Display current configuration'
        )
        show_parser.add_argument('--key', help='Show specific configuration key')
        
        # Set config command
        set_parser = config_subparsers.add_parser(
            'set', 
            help='Set configuration value',
            description='Set a configuration value'
        )
        set_parser.add_argument('key', help='Configuration key (dot notation)')
        set_parser.add_argument('value', help='Configuration value')
        
        # Reset config command
        reset_parser = config_subparsers.add_parser(
            'reset', 
            help='Reset configuration',
            description='Reset configuration to defaults'
        )
        reset_parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    
    def execute(self, args):
        """Execute the parsed command."""
        try:
            # Set up logging based on arguments
            log_file = Path(args.log_file) if args.log_file else None
            global logger
            logger = setup_logging(args.verbose, log_file)
            
            # Configure output formatter - check for subcommand-specific args first
            output_format = getattr(args, 'output', None) or self.config_manager.get('output.format', 'table')
            use_color = not getattr(args, 'no_color', False) and self.config_manager.get('output.color', True)
            self.formatter = OutputFormatter(format=output_format, color=use_color)
            
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
                if args.force:
                    timeout = 1
                else:
                    timeout = args.timeout
                success = self.server_controller.stop(timeout=timeout, delete_logs=args.delete_logs)
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
                if args.watch:
                    try:
                        while True:
                            console.clear()
                            status = self.server_controller.status()
                            self._display_status(status)
                            time.sleep(args.interval)
                    except KeyboardInterrupt:
                        self.formatter.info("Status monitoring stopped")
                        return 0
                else:
                    status = self.server_controller.status()
                    self._display_status(status)
                    return 0 if status['status'] == 'running' else 1
            
            # Handle authentication commands
            elif args.command == 'login':
                api_manager = self.get_api_manager(args.server_url)
                
                # Check if already authenticated
                auth_status = api_manager.check_auth_status()
                if auth_status.get('authenticated'):
                    current_user = auth_status.get('user', {})
                    username = current_user.get('username', 'unknown')
                    self.formatter.warning(f"Already logged in as {username}")
                    self.formatter.info("Please logout first if you want to login with a different account")
                    return 0
                
                # Prompt for username if not provided
                username = args.username
                if not username:
                    username = Prompt.ask("Username")
                    if not username:
                        self.formatter.error("Username is required")
                        return 1
                
                # Prompt for password if not provided
                password = args.password
                if not password:
                    password = getpass.getpass("Password: ")
                    if not password:
                        self.formatter.error("Password is required")
                        return 1
                
                result = api_manager.login(username, password)
                if args.output == 'json':
                    self.formatter.format_json(result)
                else:
                    self.formatter.success(f"Logged in as {result.get('username', username)}")
                    if not args.no_save:
                        if KEYRING_AVAILABLE:
                            self.formatter.info("Credentials securely stored in system keychain")
                        else:
                            self.formatter.info("Credentials saved to secure file storage")
                            self.formatter.warning("For enhanced security, consider installing keyring: pip install keyring")
                return 0
            
            elif args.command == 'logout':
                api_manager = self.get_api_manager(args.server_url)
                result = api_manager.logout()
                if getattr(args, 'output', None) == 'json':
                    self.formatter.format_json(result)
                else:
                    if result.get("message", "").lower().startswith("logout successful"):
                        self.formatter.success("Logged out successfully")
                    else:
                        self.formatter.info(result.get("message", "Logged out"))
                return 0
            
            elif args.command == 'register':
                api_manager = self.get_api_manager(args.server_url)
                
                password = args.password
                if not password:
                    password = getpass.getpass("Password for new user: ")
                    confirm = getpass.getpass("Confirm password: ")
                    if password != confirm:
                        self.formatter.error("Passwords do not match")
                        return 1
                
                result = api_manager.register_user(args.username, password, args.role)
                if args.output == 'json':
                    self.formatter.format_json(result)
                else:
                    self.formatter.success(f"User '{args.username}' registered successfully")
                return 0
            
            elif args.command == 'me':
                api_manager = self.get_api_manager(args.server_url)
                result = api_manager.get_current_user()
                if args.output == 'json':
                    self.formatter.format_json(result)
                else:
                    self._display_user_info(result)
                return 0
            
            elif args.command == 'auth-status':
                api_manager = self.get_api_manager(args.server_url)
                result = api_manager.check_auth_status()
                
                # Add security information
                result['security'] = {
                    'keyring_available': KEYRING_AVAILABLE,
                    'secure_storage': KEYRING_AVAILABLE,
                    'storage_method': 'system_keychain' if KEYRING_AVAILABLE else 'file_fallback'
                }
                
                if getattr(args, 'output', None) == 'json':
                    self.formatter.format_json(result)
                else:
                    if result['authenticated']:
                        console.print("authenticated")
                        if 'user' in result:
                            self._display_user_info(result['user'])
                    else:
                        console.print("not authenticated")
                        if 'error' in result:
                            self.formatter.error(f"Error: {result['error']}")
                    
                    # Display security status
                    console.print()
                    console.print("[bold]Security Status:[/bold]")
                    if KEYRING_AVAILABLE:
                        console.print("✓ Secure credential storage enabled (system keychain)")
                    else:
                        console.print("⚠ Using fallback file storage")
                        console.print("  For enhanced security, install keyring: pip install keyring")
                return 0 if result['authenticated'] else 1
            

            
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
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("API key created successfully")
                        console.print(f"[bold]API Key:[/bold] {result.get('api_key', 'N/A')}")
                        console.print(f"[bold]Client:[/bold] {result.get('client_name', 'N/A')}")
                        console.print(f"[bold]Collection:[/bold] {result.get('collection', result.get('collection_name', 'N/A'))}")
                        if result.get('system_prompt_id'):
                            console.print(f"[bold]Prompt ID:[/bold] {result['system_prompt_id']}")
                    return 0
                
                elif args.key_command == 'list':
                    result = api_manager.list_api_keys(
                        collection=args.collection,
                        active_only=args.active_only,
                        limit=args.limit,
                        offset=args.offset
                    )
                    if getattr(args, 'output', None) == 'json':
                        self.formatter.format_json(result)
                    else:
                        if result:
                            headers = ['API Key', 'Client', 'Collection', 'Active', 'Created']
                            data = []
                            for key in result:
                                created_at = key.get('created_at', 'N/A')
                                if isinstance(created_at, (int, float)):
                                    # Convert timestamp to date string
                                    from datetime import datetime
                                    created_at = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d')
                                elif isinstance(created_at, str):
                                    created_at = created_at[:10]
                                
                                data.append({
                                    'API Key': key.get('api_key', 'N/A')[:20] + '...',
                                    'Client': key.get('client_name', 'N/A'),
                                    'Collection': key.get('collection', key.get('collection_name', 'N/A')),
                                    'Active': '✓' if key.get('active', True) else '✗',
                                    'Created': created_at
                                })
                            self.formatter.format_table(data, headers)
                            console.print(f"Found {len(result)} api keys")
                        else:
                            console.print("No api keys found")
                    return 0
                
                elif args.key_command == 'test':
                    result = api_manager.test_api_key(args.key)
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        if result.get('status') == 'error':
                            self.formatter.error(f"API key test failed: {result.get('error', 'Unknown error')}")
                            return 1
                        else:
                            self.formatter.success("API key is valid and active")
                            if 'server_version' in result:
                                console.print(f"Server version: {result['server_version']}")
                    return 0 if result.get('status') != 'error' else 1
                
                elif args.key_command == 'status':
                    result = api_manager.get_api_key_status(args.key)
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        self._display_api_key_status(result)
                    return 0
                
                elif args.key_command == 'deactivate':
                    result = api_manager.deactivate_api_key(args.key)
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("API key deactivated successfully")
                    return 0
                
                elif args.key_command == 'delete':
                    if not args.force:
                        if not Confirm.ask(f"Are you sure you want to delete API key {args.key[:20]}...?"):
                            self.formatter.info("Operation cancelled")
                            return 0
                    
                    result = api_manager.delete_api_key(args.key)
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("API key deleted successfully")
                    return 0
            
            # Handle system prompt commands
            elif args.command == 'prompt':
                api_manager = self.get_api_manager(args.server_url)
                
                if args.prompt_command == 'create':
                    prompt_text = api_manager._read_file_content(args.file)
                    result = api_manager.create_prompt(args.name, prompt_text, args.version)
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("System prompt created successfully")
                        console.print(f"[bold]ID:[/bold] {result.get('_id') or result.get('id', 'N/A')}")
                        console.print(f"[bold]Name:[/bold] {result.get('name', 'N/A')}")
                        console.print(f"[bold]Version:[/bold] {result.get('version', 'N/A')}")
                    return 0
                
                elif args.prompt_command == 'list':
                    result = api_manager.list_prompts(
                        name_filter=args.name_filter,
                        limit=args.limit,
                        offset=args.offset
                    )
                    if getattr(args, 'output', None) == 'json':
                        self.formatter.format_json(result)
                    else:
                        if result:
                            headers = ['ID', 'Name', 'Version', 'Created', 'Updated']
                            data = []
                            for prompt in result:
                                created_at = prompt.get('created_at', 'N/A')
                                updated_at = prompt.get('updated_at', 'N/A')
                                
                                if isinstance(created_at, (int, float)):
                                    from datetime import datetime
                                    created_at = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d')
                                elif isinstance(created_at, str):
                                    created_at = created_at[:10]
                                
                                if isinstance(updated_at, (int, float)):
                                    from datetime import datetime
                                    updated_at = datetime.fromtimestamp(updated_at).strftime('%Y-%m-%d')
                                elif isinstance(updated_at, str):
                                    updated_at = updated_at[:10]
                                
                                data.append({
                                    'ID': (prompt.get('_id') or prompt.get('id', 'N/A'))[:12] + '...',
                                    'Name': prompt.get('name', 'N/A'),
                                    'Version': prompt.get('version', 'N/A'),
                                    'Created': created_at,
                                    'Updated': updated_at
                                })
                            self.formatter.format_table(data, headers)
                            console.print(f"Found {len(result)} prompts")
                        else:
                            console.print("No prompts found")
                    return 0
                
                elif args.prompt_command == 'get':
                    result = api_manager.get_prompt(args.id)
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        self._display_prompt_details(result)
                        
                        if args.save:
                            with open(args.save, 'w') as f:
                                f.write(result.get('prompt', ''))
                            self.formatter.success(f"Prompt saved to {args.save}")
                    return 0
                
                elif args.prompt_command == 'update':
                    prompt_text = api_manager._read_file_content(args.file)
                    result = api_manager.update_prompt(args.id, prompt_text, args.version)
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("System prompt updated successfully")
                    return 0
                
                elif args.prompt_command == 'delete':
                    if not args.force:
                        if not Confirm.ask(f"Are you sure you want to delete prompt {args.id[:12]}...?"):
                            self.formatter.info("Operation cancelled")
                            return 0
                    
                    result = api_manager.delete_prompt(args.id)
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("System prompt deleted successfully")
                    return 0
                
                elif args.prompt_command == 'associate':
                    result = api_manager.associate_prompt_with_api_key(args.key, args.prompt_id)
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("System prompt associated with API key successfully")
                    return 0
            
            # Handle user commands
            elif args.command == 'user':
                api_manager = self.get_api_manager(args.server_url)
                
                if args.user_command == 'list':
                    result = api_manager.list_users(
                        role=args.role,
                        active_only=args.active_only,
                        limit=args.limit,
                        offset=args.offset
                    )
                    if getattr(args, 'output', None) == 'json':
                        self.formatter.format_json(result)
                    else:
                        if result:
                            headers = ['ID', 'Username', 'Role', 'Active', 'Created']
                            data = []
                            for user in result:
                                created_at = user.get('created_at', 'N/A')
                                if isinstance(created_at, (int, float)):
                                    from datetime import datetime
                                    created_at = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d')
                                elif isinstance(created_at, str):
                                    created_at = created_at[:10]
                                
                                data.append({
                                    'ID': (user.get('_id') or user.get('id', 'N/A'))[:12] + '...',
                                    'Username': user.get('username', 'N/A'),
                                    'Role': user.get('role', 'N/A'),
                                    'Active': '✓' if user.get('active', True) else '✗',
                                    'Created': created_at
                                })
                            self.formatter.format_table(data, headers)
                            console.print(f"Found {len(result)} users")
                        else:
                            console.print("No users found")
                    return 0
                
                elif args.user_command == 'reset-password':
                    # Determine user ID from either --user-id or --username
                    user_id = args.user_id
                    if args.username:
                        user_id = api_manager.find_user_id_by_username(args.username)
                    
                    password = args.password
                    if not password:
                        # Generate a random password
                        import secrets
                        import string
                        alphabet = string.ascii_letters + string.digits
                        password = ''.join(secrets.choice(alphabet) for i in range(16))
                        console.print(f"[bold]Generated password:[/bold] {password}")
                    
                    result = api_manager.reset_user_password(user_id, password)
                    if args.output == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("User password reset successfully")
                    return 0
                
                elif args.user_command == 'delete':
                    if not args.force:
                        if not Confirm.ask(f"Are you sure you want to delete user {args.user_id[:12]}...?"):
                            self.formatter.info("Operation cancelled")
                            return 0
                    
                    result = api_manager.delete_user(args.user_id)
                    if getattr(args, 'output', None) == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("User deleted successfully")
                    return 0
                
                elif args.user_command == 'deactivate':
                    if not args.force:
                        if not Confirm.ask(f"Are you sure you want to deactivate user {args.user_id[:12]}...?"):
                            self.formatter.info("Operation cancelled")
                            return 0
                    
                    result = api_manager.deactivate_user(args.user_id)
                    if getattr(args, 'output', None) == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("User deactivated successfully")
                    return 0
                
                elif args.user_command == 'activate':
                    if not args.force:
                        if not Confirm.ask(f"Are you sure you want to activate user {args.user_id[:12]}...?"):
                            self.formatter.info("Operation cancelled")
                            return 0
                    
                    result = api_manager.activate_user(args.user_id)
                    if getattr(args, 'output', None) == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("User activated successfully")
                    return 0
                
                elif args.user_command == 'change-password':
                    # Prompt for current password if not provided
                    current_password = args.current_password
                    if not current_password:
                        current_password = getpass.getpass("Current password: ")
                    
                    # Prompt for new password if not provided
                    new_password = args.new_password
                    if not new_password:
                        new_password = getpass.getpass("New password: ")
                        confirm = getpass.getpass("Confirm new password: ")
                        if new_password != confirm:
                            self.formatter.error("New passwords do not match")
                            return 1
                    
                    result = api_manager.change_password(current_password, new_password)
                    if getattr(args, 'output', None) == 'json':
                        self.formatter.format_json(result)
                    else:
                        self.formatter.success("Password changed successfully")
                        self.formatter.warning("All sessions have been invalidated. Please login again.")
                    # Clear the local token since it's now invalid
                    api_manager._clear_token_secure()
                    return 0
                

            
            # Handle configuration commands
            elif args.command == 'config':
                if args.config_command == 'show':
                    if args.key:
                        value = self.config_manager.get(args.key)
                        if value is not None:
                            if args.output == 'json':
                                self.formatter.format_json({args.key: value})
                            else:
                                console.print(f"{args.key}: {value}")
                        else:
                            self.formatter.error(f"Configuration key '{args.key}' not found")
                            return 1
                    else:
                        config = self.config_manager.load_config()
                        if args.output == 'json':
                            self.formatter.format_json(config)
                        else:
                            self._display_config(config)
                    return 0
                
                elif args.config_command == 'set':
                    # Try to parse value as JSON first
                    try:
                        value = json.loads(args.value)
                    except json.JSONDecodeError:
                        # If not JSON, treat as string
                        value = args.value
                    
                    self.config_manager.set(args.key, value)
                    self.formatter.success(f"Configuration updated: {args.key} = {value}")
                    return 0
                
                elif args.config_command == 'reset':
                    if not args.force:
                        if not Confirm.ask("Are you sure you want to reset configuration to defaults?"):
                            self.formatter.info("Operation cancelled")
                            return 0
                    
                    default_config = self.config_manager.get_default_config()
                    self.config_manager.save_config(default_config)
                    self.formatter.success("Configuration reset to defaults")
                    return 0
            
            return 1
            
        except OrbitError as e:
            self.formatter.error(str(e))
            logger.debug(f"OrbitError: {e}", exc_info=True)
            return 1
        except KeyboardInterrupt:
            self.formatter.warning("\nOperation cancelled by user")
            return 130
        except Exception as e:
            self.formatter.error(f"Unexpected error: {str(e)}")
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return 1
    
    def _display_status(self, status: Dict[str, Any]) -> None:
        """Display server status in a formatted way."""
        if status['status'] == 'running':
            self.formatter.success(status['message'])
            console.print(f"[bold]PID:[/bold] {status['pid']}")
            console.print(f"[bold]Uptime:[/bold] {status['uptime']}")
            console.print(f"[bold]Memory:[/bold] {status['memory_mb']} MB")
            console.print(f"[bold]CPU:[/bold] {status['cpu_percent']}%")
        elif status['status'] == 'stopped':
            self.formatter.warning(status['message'])
        else:
            self.formatter.error(status['message'])
            if 'error' in status:
                console.print(f"[bold]Error:[/bold] {status['error']}")
    
    def _display_user_info(self, user: Dict[str, Any]) -> None:
        """Display user information in a formatted way."""
        console.print(f"[bold]Username:[/bold] {user.get('username', 'N/A')}")
        console.print(f"[bold]Role:[/bold] {user.get('role', 'N/A')}")
        console.print(f"[bold]ID:[/bold] {user.get('_id') or user.get('id', 'N/A')}")
        if 'created_at' in user:
            console.print(f"[bold]Created:[/bold] {user['created_at']}")
        if 'last_login' in user:
            console.print(f"[bold]Last Login:[/bold] {user['last_login']}")
    
    def _display_api_key_status(self, status: Dict[str, Any]) -> None:
        """Display API key status in a formatted way."""
        if status.get('active'):
            self.formatter.success("API key is active")
        else:
            self.formatter.warning("API key is inactive")
        
        console.print(f"[bold]Client:[/bold] {status.get('client_name', 'N/A')}")
        console.print(f"[bold]Collection:[/bold] {status.get('collection', status.get('collection_name', 'N/A'))}")
        if 'created_at' in status:
            console.print(f"[bold]Created:[/bold] {status['created_at']}")
        if 'last_used' in status:
            console.print(f"[bold]Last Used:[/bold] {status['last_used']}")
        if 'system_prompt_id' in status:
            console.print(f"[bold]System Prompt:[/bold] {status['system_prompt_id']}")
    
    def _display_prompt_details(self, prompt: Dict[str, Any]) -> None:
        """Display prompt details in a formatted way."""
        console.print(f"[bold]ID:[/bold] {prompt.get('_id') or prompt.get('id', 'N/A')}")
        console.print(f"[bold]Name:[/bold] {prompt.get('name', 'N/A')}")
        console.print(f"[bold]Version:[/bold] {prompt.get('version', 'N/A')}")
        if 'created_at' in prompt:
            console.print(f"[bold]Created:[/bold] {prompt['created_at']}")
        if 'updated_at' in prompt:
            console.print(f"[bold]Updated:[/bold] {prompt['updated_at']}")
        console.print("\n[bold]Prompt Text:[/bold]")
        console.print("─" * 60)
        console.print(prompt.get('prompt', 'N/A'))
        console.print("─" * 60)
    
    def _display_config(self, config: Dict[str, Any], prefix: str = "") -> None:
        """Display configuration in a tree format."""
        for key, value in config.items():
            if isinstance(value, dict):
                console.print(f"{prefix}[bold]{key}:[/bold]")
                self._display_config(value, prefix + "  ")
            else:
                console.print(f"{prefix}{key}: {value}")


def main():
    """Main entry point for the ORBIT CLI."""
    cli = OrbitCLI()
    parser = cli.create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    exit_code = cli.execute(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()